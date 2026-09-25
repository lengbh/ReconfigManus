import time
from machine import I2C, Pin

from part_uid_dict import get_part_id


class PN532Error(Exception):
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

    def _wait_ready(self, timeout_ms):
        started = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
            try:
                if self.i2c.readfrom(self.address, 1)[0] == 0x01:
                    return
            except OSError:
                pass
            time.sleep_ms(10)
        raise PN532Error("PN532 response timed out")

    def _write_frame(self, payload):
        length = len(payload)
        frame = bytearray((0x00, 0x00, 0xFF, length, (-length) & 0xFF))
        frame.extend(payload)
        frame.extend(((-sum(payload)) & 0xFF, 0x00))
        self.i2c.writeto(self.address, frame)

        if self.debug:
            print("PN532 TX:", frame)

    def _read_ack(self, timeout_ms):
        self._wait_ready(timeout_ms)
        response = self.i2c.readfrom(self.address, 7)
        if response[1:] != self.ACK:
            raise PN532Error("Invalid PN532 acknowledgement")

    def _read_frame(self, timeout_ms):
        self._wait_ready(timeout_ms)
        raw = self.i2c.readfrom(self.address, 65)
        frame = raw[1:]

        if frame[:3] != b"\x00\x00\xFF":
            raise PN532Error("Invalid PN532 response preamble")

        length = frame[3]
        if ((length + frame[4]) & 0xFF) != 0:
            raise PN532Error("Invalid PN532 response length checksum")

        payload = frame[5:5 + length]
        checksum = frame[5 + length]
        if ((sum(payload) + checksum) & 0xFF) != 0:
            raise PN532Error("Invalid PN532 response checksum")

        if self.debug:
            print("PN532 RX:", payload)

        return payload

    def call(self, command, parameters=b"", timeout_ms=1000):
        payload = bytes((self.HOST_TO_PN532, command)) + parameters
        self._write_frame(payload)
        self._read_ack(timeout_ms)
        response = self._read_frame(timeout_ms)

        if len(response) < 2:
            raise PN532Error("PN532 returned a short response")
        if response[0] != self.PN532_TO_HOST or response[1] != command + 1:
            raise PN532Error("PN532 returned an unexpected response")

        return response[2:]

    def firmware_version(self):
        response = self.call(0x02)
        if len(response) < 4:
            raise PN532Error("PN532 firmware response was incomplete")
        return tuple(response[:4])

    def sam_configuration(self):
        self.call(0x14, b"\x01\x14\x01")

    def read_passive_target(self, timeout=0.5):
        timeout_ms = max(1, int(timeout * 1000))

        try:
            response = self.call(0x4A, b"\x01\x00", timeout_ms=timeout_ms)
        except PN532Error as error:
            if str(error) == "PN532 response timed out":
                return None
            raise

        if not response or response[0] == 0:
            return None
        if len(response) < 6:
            raise PN532Error("PN532 target response was incomplete")

        uid_length = response[5]
        uid = response[6:6 + uid_length]
        if len(uid) != uid_length:
            raise PN532Error("PN532 UID was incomplete")

        return uid


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

    def read_part_id(self, timeout=0.5):
        uid = self.read_uid(timeout=timeout)
        if not uid:
            return None

        uid_hex = "".join("{:02X}".format(byte) for byte in uid)
        return get_part_id(uid_hex)

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
