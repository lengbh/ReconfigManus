import asyncio

from motor_driver import Motor
from nfc_reader import NFCReader, PN532Error, uid_to_hex
from part_uid_dict import get_part_id


class Conveyor:
    SPEED = 100
    RUN_DURATION_BOX_MS = 4000
    RUN_DURATION_OUT_MS = 3000
    NFC_SCAN_TIMEOUT = 0.05
    POLL_INTERVAL_MS = 10
    TAG_REMOVAL_CONFIRMATIONS = 3
    NFC_RECOVERY_INTERVAL_MS = 1000

    def __init__(
        self,
        motor_in1_pin,
        motor_in2_pin,
        motor_pwm_pin,
        nfc_sda_pin,
        nfc_scl_pin,
        nfc_i2c_id=0,
        telemetry=None,
        fault_logger=None,
    ):
        self.telemetry = telemetry
        self.fault_logger = fault_logger
        self.nfc_connected = None
        self.nfc_error = None
        self.nfc_faults = 0
        self.nfc_recovery_attempts = 0
        self.pwm_enabled = motor_pwm_pin is not None
        self.running = False
        self.direction = "stopped"
        self.part_id = None
        self.motor = Motor(motor_in1_pin, motor_in2_pin, motor_pwm_pin)
        try:
            self.nfc_reader = NFCReader(
                i2c_id=nfc_i2c_id,
                sda_pin=nfc_sda_pin,
                scl_pin=nfc_scl_pin,
                initialize=False,
            )
        except Exception:
            self.motor.cleanup()
            raise
        self._emit_state("stopped", None, 0, "ready")

    def _emit_state(self, direction, part_id, duration_ms, event):
        self.running = direction != "stopped"
        self.direction = direction
        self.part_id = part_id
        if self.telemetry is not None:
            self.telemetry.emit(
                "conveyor/state",
                {
                    "running": self.running,
                    "direction": direction,
                    "speed_command_percent": self.SPEED if self.running else 0,
                    "pwm_enabled": self.pwm_enabled,
                    "duration_ms": duration_ms,
                    "part_id": part_id,
                    "position_source": "commanded",
                    "nfc_connected": self.nfc_connected,
                    "nfc_error": self.nfc_error,
                },
                event=event,
                force=True,
            )

    async def _sleep_ms(self, duration_ms):
        if hasattr(asyncio, "sleep_ms"):
            await asyncio.sleep_ms(duration_ms)
        else:
            await asyncio.sleep(duration_ms / 1000)

    def _emit_nfc_status(self, event):
        if self.telemetry is not None:
            self.telemetry.emit("status", {
                "nfc_connected": self.nfc_connected,
                "nfc_error": self.nfc_error,
                "nfc_faults": self.nfc_faults,
                "nfc_recovery_attempts": self.nfc_recovery_attempts,
            }, event=event)

    async def _recover_nfc(self, error):
        first_failure = self.nfc_connected is not False
        self.nfc_connected = False
        self.nfc_error = str(error)
        self.motor.stop()
        if first_failure:
            self.nfc_faults += 1
            self._emit_state("stopped", self.part_id, 0, "nfc_fault")
            if self.fault_logger is not None:
                self.fault_logger(error, source="NFC reader fault; recovering")
        self._emit_nfc_status("nfc_fault")
        while True:
            await self._sleep_ms(self.NFC_RECOVERY_INTERVAL_MS)
            self.nfc_recovery_attempts += 1
            try:
                await self.nfc_reader.recover_async()
            except (OSError, PN532Error) as recovery_error:
                self.nfc_error = str(recovery_error)
                print("PN532 recovery retry:", recovery_error)
                self._emit_nfc_status("nfc_retry")
            else:
                return

    async def _read_uid(self):
        while True:
            try:
                uid = await self.nfc_reader.read_uid_async(timeout=self.NFC_SCAN_TIMEOUT)
            except (OSError, PN532Error) as error:
                await self._recover_nfc(error)
                continue
            if not self.nfc_connected:
                recovering = self.nfc_connected is False
                self.nfc_connected = True
                self.nfc_error = None
                event = "nfc_recovered" if recovering else "nfc_ready"
                self._emit_state("stopped", self.part_id, 0, event)
                self._emit_nfc_status(event)
            return uid

    async def wait_for_tag_removal(self):
        missing_reads = 0
        print("Remove tag...")
        while missing_reads < self.TAG_REMOVAL_CONFIRMATIONS:
            previous_faults = self.nfc_faults
            uid = await self._read_uid()
            if self.nfc_faults != previous_faults:
                # Lost communication cannot count towards proving tag removal.
                missing_reads = 0
            if uid:
                missing_reads = 0
            else:
                missing_reads += 1
            await self._sleep_ms(self.POLL_INTERVAL_MS)

    async def process_tag(self, uid):
        uid_hex = uid_to_hex(uid)
        part_id = get_part_id(uid_hex)
        if self.telemetry is not None:
            self.telemetry.emit(
                "part/event",
                {"uid": uid_hex, "part_id": part_id, "recognized": part_id is not None},
                event="detected",
                force=True,
            )
        try:
            if part_id is None:
                print("Unknown tag UID:", uid_hex)
            elif part_id % 2 == 0:
                print("Even part", part_id, "- conveyor forward...")
                self.motor.run_forward(self.SPEED)
                self._emit_state("forward", part_id, self.RUN_DURATION_BOX_MS, "started")
                await self._sleep_ms(self.RUN_DURATION_BOX_MS)
            else:
                print("Odd part", part_id, "- conveyor backward...")
                self.motor.run_backward(self.SPEED)
                self._emit_state("backward", part_id, self.RUN_DURATION_OUT_MS, "started")
                await self._sleep_ms(self.RUN_DURATION_OUT_MS)
        finally:
            self.motor.stop()
            self._emit_state("stopped", part_id, 0, "stopped")
        print("Conveyor stopped.")
        await self.wait_for_tag_removal()
        print("Ready for next part.")

    async def run(self):
        try:
            while True:
                uid = await self._read_uid()
                if uid:
                    await self.process_tag(uid)
                else:
                    await self._sleep_ms(self.POLL_INTERVAL_MS)
        finally:
            self.motor.stop()
            self._emit_state("stopped", self.part_id, 0, "stopped")

    def cleanup(self):
        self.motor.cleanup()
        self._emit_state("stopped", self.part_id, 0, "stopped")
