import asyncio

from motor_driver import Motor
from nfc_reader import NFCReader, uid_to_hex
from part_uid_dict import get_part_id


class Conveyor:
    SPEED = 100
    RUN_DURATION_BOX_MS = 4000
    RUN_DURATION_OUT_MS = 3000
    NFC_SCAN_TIMEOUT = 0.05
    POLL_INTERVAL_MS = 10
    TAG_REMOVAL_CONFIRMATIONS = 3

    def __init__(
        self,
        motor_in1_pin,
        motor_in2_pin,
        motor_pwm_pin,
        nfc_sda_pin,
        nfc_scl_pin,
        nfc_i2c_id=0,
    ):
        self.motor = Motor(
            motor_in1_pin,
            motor_in2_pin,
            motor_pwm_pin,
        )

        try:
            self.nfc_reader = NFCReader(
                i2c_id=nfc_i2c_id,
                sda_pin=nfc_sda_pin,
                scl_pin=nfc_scl_pin,
            )
        except Exception:
            self.motor.cleanup()
            raise

    async def _sleep_ms(self, duration_ms):
        if hasattr(asyncio, "sleep_ms"):
            await asyncio.sleep_ms(duration_ms)
        else:
            await asyncio.sleep(duration_ms / 1000)

    async def wait_for_tag_removal(self):
        missing_reads = 0
        print("Remove tag...")

        while missing_reads < self.TAG_REMOVAL_CONFIRMATIONS:
            uid = self.nfc_reader.read_uid(
                timeout=self.NFC_SCAN_TIMEOUT
            )

            if uid:
                missing_reads = 0
            else:
                missing_reads += 1

            await self._sleep_ms(self.POLL_INTERVAL_MS)

    async def process_tag(self, uid):
        uid_hex = uid_to_hex(uid)
        part_id = get_part_id(uid_hex)

        try:
            if part_id is None:
                print("Unknown tag UID:", uid_hex)
            elif part_id % 2 == 0:
                print("Even part", part_id, "- conveyor forward...")
                self.motor.run_forward(self.SPEED)
                await self._sleep_ms(self.RUN_DURATION_BOX_MS)
            else:
                print("Odd part", part_id, "- conveyor backward...")
                self.motor.run_backward(self.SPEED)
                await self._sleep_ms(self.RUN_DURATION_OUT_MS)
        finally:
            self.motor.stop()

        print("Conveyor stopped.")
        await self.wait_for_tag_removal()
        print("Ready for next part.")

    async def run(self):
        while True:
            uid = self.nfc_reader.read_uid(timeout=self.NFC_SCAN_TIMEOUT)

            if uid:
                await self.process_tag(uid)
            else:
                await self._sleep_ms(self.POLL_INTERVAL_MS)

    def cleanup(self):
        self.motor.cleanup()
