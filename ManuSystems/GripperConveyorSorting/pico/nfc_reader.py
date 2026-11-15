import asyncio
import errno
import time
from machine import I2C, Pin

from part_uid_dict import get_part_id


I2C_READ_ATTEMPTS = 3
I2C_READ_RETRY_MS = 10
I2C_FREQUENCY = 100_000
I2C_TIMEOUT_US = 50_000


def _sleep_ms_sync(duration_ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(duration_ms)
    else:
        time.sleep(duration_ms / 1000)


def _sleep_us(duration_us):
    if hasattr(time, "sleep_us"):
        time.sleep_us(duration_us)
    else:
        time.sleep(duration_us / 1_000_000)


def _ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(new, old):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(new, old)
    return new - old


async def _sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


def uid_to_hex(uid):
    return "".join("{:02X}".format(byte) for byte in uid)


class PN532Error(Exception):
    pass


class PN532Timeout(PN532Error):
    pass


class PN532_I2C:
    ADDRESS = 0x24
    HOST_TO_PN532 = 0xD4
    PN532_TO_HOST = 0xD5
    ACK = b"\x00\x00\xFF\x00\xFF\x00"

    def __init__(self, i2c, address=ADDRESS, debug=False):
        self.i2c = i2c
        self.address = address
        self.debug = debug
        self._async_lock = None

    def _is_ready(self):
        status = self.i2c.readfrom(self.address, 1)
        return bool(status) and status[0] == 0x01

    def _read_data(self, length):
        for attempt in range(I2C_READ_ATTEMPTS):
            try:
                return self.i2c.readfrom(self.address, length)
            except OSError as error:
                if (not error.args or error.args[0] != errno.ETIMEDOUT
                        or attempt == I2C_READ_ATTEMPTS - 1):
                    raise
                print("PN532 I2C read timed out; retry", attempt + 1)
                _sleep_ms_sync(I2C_READ_RETRY_MS)

    async def _read_data_async(self, length):
        for attempt in range(I2C_READ_ATTEMPTS):
            try:
                return self.i2c.readfrom(self.address, length)
            except OSError as error:
                if (not error.args or error.args[0] != errno.ETIMEDOUT
                        or attempt == I2C_READ_ATTEMPTS - 1):
                    raise
                # Retry this read while holding the command lock. Resending a
                # whole command could confuse its pending ACK/response.
                print("PN532 I2C read timed out; retry", attempt + 1)
                await _sleep_ms(I2C_READ_RETRY_MS)

    def _wait_ready(self, timeout_ms):
        started = _ticks_ms()
        last_error = None
        while _ticks_diff(_ticks_ms(), started) < timeout_ms:
            try:
                ready = self._is_ready()
            except OSError as error:
                last_error = error
            else:
                last_error = None
                if ready:
                    return
            remaining = timeout_ms - _ticks_diff(_ticks_ms(), started)
            if remaining > 0:
                _sleep_ms_sync(min(10, remaining))
        if last_error is not None:
            raise last_error
        raise PN532Timeout("PN532 response timed out")

    async def _wait_ready_async(self, timeout_ms):
        started = _ticks_ms()
        last_error = None
        while _ticks_diff(_ticks_ms(), started) < timeout_ms:
            try:
                ready = self._is_ready()
            except OSError as error:
                last_error = error
            else:
                last_error = None
                if ready:
                    return
            remaining = timeout_ms - _ticks_diff(_ticks_ms(), started)
            if remaining > 0:
                # The servo and telemetry tasks keep running during NFC waits.
                await _sleep_ms(min(10, remaining))
        if last_error is not None:
            raise last_error
        raise PN532Timeout("PN532 response timed out")

    def _write_frame(self, payload):
        length = len(payload)
        frame = bytearray((0x00, 0x00, 0xFF, length, (-length) & 0xFF))
        frame.extend(payload)
        frame.extend(((-sum(payload)) & 0xFF, 0x00))
        self.i2c.writeto(self.address, frame)

        if self.debug:
            print("PN532 TX:", frame)

    def _check_ack(self, response):
        if len(response) != 7 or response[0] != 0x01 or response[1:] != self.ACK:
            raise PN532Error("Invalid PN532 acknowledgement")

    def _read_ack(self, timeout_ms):
        try:
            self._wait_ready(timeout_ms)
        except PN532Timeout:
            raise PN532Error("PN532 did not acknowledge the command")
        self._check_ack(self._read_data(7))

    async def _read_ack_async(self, timeout_ms):
        try:
            await self._wait_ready_async(timeout_ms)
        except PN532Timeout:
            raise PN532Error("PN532 did not acknowledge the command")
        self._check_ack(await self._read_data_async(7))

    def _parse_frame(self, raw):
        # The first byte is the I2C readiness status. A normal frame has five
        # header bytes, payload, checksum and postamble; do not index short reads.
        if len(raw) < 8:
            raise PN532Error("PN532 returned a short frame")
        if raw[0] != 0x01:
            raise PN532Error("PN532 response was not ready")
        frame = raw[1:]
        if frame[:3] != b"\x00\x00\xFF":
            raise PN532Error("Invalid PN532 response preamble")
        length = frame[3]
        if ((length + frame[4]) & 0xFF) != 0:
            raise PN532Error("Invalid PN532 response length checksum")
        if len(frame) < length + 7:
            raise PN532Error("PN532 returned an incomplete frame")
        payload = frame[5:5 + length]
        checksum = frame[5 + length]
        if ((sum(payload) + checksum) & 0xFF) != 0:
            raise PN532Error("Invalid PN532 response checksum")
        if frame[6 + length] != 0:
            raise PN532Error("Invalid PN532 response postamble")
        if self.debug:
            print("PN532 RX:", payload)
        return payload

    def _read_frame(self, timeout_ms):
        self._wait_ready(timeout_ms)
        return self._parse_frame(self._read_data(65))

    async def _read_frame_async(self, timeout_ms):
        await self._wait_ready_async(timeout_ms)
        return self._parse_frame(await self._read_data_async(65))

    def _command_response(self, command, response):
        if len(response) < 2:
            raise PN532Error("PN532 returned a short response")
        if response[0] != self.PN532_TO_HOST or response[1] != command + 1:
            raise PN532Error("PN532 returned an unexpected response")
        return response[2:]

    def call(self, command, parameters=b"", timeout_ms=1000):
        # Synchronous calls remain available for startup and standalone tests.
        payload = bytes((self.HOST_TO_PN532, command)) + parameters
        self._write_frame(payload)
        self._read_ack(timeout_ms)
        return self._command_response(command, self._read_frame(timeout_ms))

    async def call_async(self, command, parameters=b"", timeout_ms=1000):
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        # ACK and response belong to one command; parallel readers must not
        # interleave their I2C transactions.
        async with self._async_lock:
            payload = bytes((self.HOST_TO_PN532, command)) + parameters
            self._write_frame(payload)
            await self._read_ack_async(timeout_ms)
            response = await self._read_frame_async(timeout_ms)
            return self._command_response(command, response)

    def firmware_version(self):
        response = self.call(0x02)
        if len(response) < 4:
            raise PN532Error("PN532 firmware response was incomplete")
        return tuple(response[:4])

    def sam_configuration(self):
        self.call(0x14, b"\x01\x14\x01")

    def _target_uid(self, response):
        if not response or response[0] == 0:
            return None
        if len(response) < 6:
            raise PN532Error("PN532 target response was incomplete")
        uid_length = response[5]
        uid = response[6:6 + uid_length]
        if not uid_length or len(uid) != uid_length:
            raise PN532Error("PN532 UID was incomplete")
        return uid

    def read_passive_target(self, timeout=0.5):
        timeout_ms = max(1, int(timeout * 1000))
        try:
            response = self.call(0x4A, b"\x01\x00", timeout_ms=timeout_ms)
        except PN532Timeout:
            return None
        return self._target_uid(response)

    async def read_passive_target_async(self, timeout=0.5):
        timeout_ms = max(1, int(timeout * 1000))
        try:
            response = await self.call_async(0x4A, b"\x01\x00", timeout_ms=timeout_ms)
        except PN532Timeout:
            return None
        return self._target_uid(response)


class NFCReader:
    def __init__(self, debug=False, i2c_id=0, sda_pin=4, scl_pin=5,
                 i2c_freq=I2C_FREQUENCY, initialize=True):
        self.debug = debug
        self.i2c_id = i2c_id
        self.sda_pin = sda_pin
        self.scl_pin = scl_pin
        self.i2c_freq = i2c_freq
        self.initialized = False
        self._access_lock = asyncio.Lock()
        self._configure_bus()
        if initialize:
            self._initialize_sync()

    def _initialize_sync(self):
        _, version, revision, _ = self.nfc.firmware_version()
        print("PN532 detected: Firmware {}.{}".format(version, revision))
        self.nfc.sam_configuration()
        self.initialized = True

    def _configure_bus(self):
        self.i2c = I2C(
            self.i2c_id, sda=Pin(self.sda_pin), scl=Pin(self.scl_pin),
            freq=self.i2c_freq, timeout=I2C_TIMEOUT_US,
        )
        self.nfc = PN532_I2C(self.i2c, debug=self.debug)

    def _clear_bus(self):
        if hasattr(self.i2c, "deinit"):
            self.i2c.deinit()
        # Release lines as inputs; only ever drive them LOW during bus clear.
        # This also removes the hardware-I2C alternate function temporarily.
        scl = Pin(self.scl_pin, Pin.IN, Pin.PULL_UP)
        sda = Pin(self.sda_pin, Pin.IN, Pin.PULL_UP)
        if not scl.value():
            raise OSError(errno.ETIMEDOUT, "PN532 SCL held low; reset/power check needed")
        for _ in range(9):
            if sda.value():
                break
            scl.init(Pin.OUT, value=0)
            _sleep_us(5)
            scl.init(Pin.IN, Pin.PULL_UP)
            _sleep_us(5)
            if not scl.value():
                raise OSError(errno.ETIMEDOUT, "PN532 SCL held low during bus clear")
        # Generate a STOP, then check that both lines were released.
        scl.init(Pin.OUT, value=0)
        sda.init(Pin.OUT, value=0)
        _sleep_us(5)
        scl.init(Pin.IN, Pin.PULL_UP)
        _sleep_us(5)
        if not scl.value():
            sda.init(Pin.IN, Pin.PULL_UP)
            raise OSError(errno.ETIMEDOUT, "PN532 SCL held low during STOP")
        sda.init(Pin.IN, Pin.PULL_UP)
        _sleep_us(5)
        if not sda.value():
            raise OSError(errno.ETIMEDOUT, "PN532 SDA held low after bus clear")

    async def _recover_unlocked(self):
        self.initialized = False
        self._clear_bus()
        self._configure_bus()
        # NXP's ACK abort discards an unfinished command or stale response.
        self.i2c.writeto(self.nfc.address, self.nfc.ACK)
        await _sleep_ms(10)
        firmware = await self.nfc.call_async(0x02)
        if len(firmware) < 4 or firmware[0] != 0x32:
            raise PN532Error("PN532 firmware check failed during recovery")
        await self.nfc.call_async(0x14, b"\x01\x14\x01")
        self.initialized = True
        print("PN532 reinitialized.")

    async def recover_async(self):
        """Clear the bus and resynchronize the PN532 without restarting motion."""
        async with self._access_lock:
            await self._recover_unlocked()

    def read_uid(self, timeout=0.5):
        if not self.initialized:
            self._initialize_sync()
        return self.nfc.read_passive_target(timeout=timeout)

    async def read_uid_async(self, timeout=0.5):
        # Recovery cannot change the I2C transport halfway through another read.
        async with self._access_lock:
            if not self.initialized:
                await self._recover_unlocked()
            return await self.nfc.read_passive_target_async(timeout=timeout)

    def read_part_id(self, timeout=0.5):
        uid = self.read_uid(timeout=timeout)
        if not uid:
            return None
        return get_part_id(uid_to_hex(uid))

    async def read_part_id_async(self, timeout=0.5):
        uid = await self.read_uid_async(timeout=timeout)
        if not uid:
            return None
        return get_part_id(uid_to_hex(uid))

    def wait_for_part(self):
        print("Waiting for NFC part...")
        while True:
            uid = self.read_uid()
            if uid:
                return uid

    def print_part(self):
        print("Scanning for NFC parts...")
        try:
            while True:
                uid = self.read_uid()
                if uid:
                    print("part detected:", uid)
        except KeyboardInterrupt:
            print("\nStopped by user")
