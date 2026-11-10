import asyncio
import time
from machine import I2C, Pin

from part_uid_dict import get_part_id


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
        try:
            status = self.i2c.readfrom(self.address, 1)
            return bool(status) and status[0] == 0x01
        except OSError:
            return False

    def _wait_ready(self, timeout_ms):
        started = _ticks_ms()
        while _ticks_diff(_ticks_ms(), started) < timeout_ms:
            if self._is_ready():
                return
            remaining = timeout_ms - _ticks_diff(_ticks_ms(), started)
            if remaining > 0:
                if hasattr(time, "sleep_ms"):
                    time.sleep_ms(min(10, remaining))
                else:
                    time.sleep(min(10, remaining) / 1000)
        raise PN532Timeout("PN532 response timed out")

    async def _wait_ready_async(self, timeout_ms):
        started = _ticks_ms()
        while _ticks_diff(_ticks_ms(), started) < timeout_ms:
            if self._is_ready():
                return
            remaining = timeout_ms - _ticks_diff(_ticks_ms(), started)
            if remaining > 0:
                # The servo and telemetry tasks keep running during NFC waits.
                await _sleep_ms(min(10, remaining))
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
        self._wait_ready(timeout_ms)
        self._check_ack(self.i2c.readfrom(self.address, 7))

    async def _read_ack_async(self, timeout_ms):
        await self._wait_ready_async(timeout_ms)
        self._check_ack(self.i2c.readfrom(self.address, 7))

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
        return self._parse_frame(self.i2c.readfrom(self.address, 65))

    async def _read_frame_async(self, timeout_ms):
        await self._wait_ready_async(timeout_ms)
        return self._parse_frame(self.i2c.readfrom(self.address, 65))

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
    def __init__(self, debug=False, i2c_id=0, sda_pin=4, scl_pin=5):
        i2c = I2C(
            i2c_id,
            sda=Pin(sda_pin),
            scl=Pin(scl_pin),
            freq=400000,
        )
        self.nfc = PN532_I2C(i2c, debug=debug)
        _, version, revision, _ = self.nfc.firmware_version()
        print("PN532 detected: Firmware {}.{}".format(version, revision))
        self.nfc.sam_configuration()

    def read_uid(self, timeout=0.5):
        return self.nfc.read_passive_target(timeout=timeout)

    async def read_uid_async(self, timeout=0.5):
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
