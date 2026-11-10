import asyncio
import math
import time

from machine import Pin, PWM


SERVO_MOVE_MS = 1500
COMMAND_INTERVAL_MS = 20
POLL_INTERVAL_MS = 10
SENSOR_TRIGGER_LEVEL = 61200
SENSOR_RESET_LEVEL = 58000


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


def ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def ticks_diff(new, old):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(new, old)
    return new - old


def clamp_angle(angle):
    angle = float(angle)
    if not math.isfinite(angle):
        raise ValueError("Servo angle must be finite")
    return max(0.0, min(180.0, angle))


class ServoMotor:
    MIN_DUTY = 1638
    MAX_DUTY = 8192

    def __init__(self, pin_number, telemetry=None, axis="rotation",
                 command_interval_ms=COMMAND_INTERVAL_MS,
                 movement_duration_ms=SERVO_MOVE_MS):
        command_interval_ms = int(command_interval_ms)
        movement_duration_ms = int(movement_duration_ms)
        if command_interval_ms < 1:
            raise ValueError("command_interval_ms must be positive")
        if movement_duration_ms < 0:
            raise ValueError("movement_duration_ms cannot be negative")
        self.telemetry = telemetry
        self.axis = axis
        self.command_interval_ms = command_interval_ms
        self.movement_duration_ms = movement_duration_ms
        self.commanded_angle_deg = None
        self.initialized = False
        self._lock = asyncio.Lock()
        self._motion_id = 0
        self._moving = False
        self._target_angle_deg = None
        self._start_angle_deg = None
        self._duration_ms = 0
        self._elapsed_ms = 0
        self._progress = None
        self._enabled = True
        self.servo = PWM(Pin(pin_number))
        try:
            self.servo.freq(50)
        except BaseException:
            self._enabled = False
            self.servo.deinit()
            raise

    def _write_pwm(self, angle):
        if not self._enabled:
            raise RuntimeError("Servo has been deinitialised")
        duty = int(self.MIN_DUTY + (angle / 180) * (self.MAX_DUTY - self.MIN_DUTY))
        self.servo.duty_u16(duty)

    def write_angle(self, angle):
        """Immediate low-level command; does not establish physical position."""
        angle = clamp_angle(angle)
        self._write_pwm(angle)
        self.commanded_angle_deg = angle
        return angle

    def _state(self):
        return {"axis": self.axis, "commanded_angle_deg": self.commanded_angle_deg,
                "target_angle_deg": self._target_angle_deg,
                "start_angle_deg": self._start_angle_deg,
                "motion_id": self._motion_id, "duration_ms": self._duration_ms,
                "elapsed_ms": self._elapsed_ms, "progress": self._progress,
                "moving": self._moving, "initialized": self.initialized,
                "servo_enabled": self._enabled,
                "position_source": "commanded"}

    def _emit(self, event, force=False):
        if self.telemetry is not None:
            self.telemetry.emit(self.axis + "/state", self._state(), event=event, force=force)

    async def move_to(self, target_angle, duration_ms=None):
        """Issue intermediate commands using elapsed time, never network waits.

        Initial positioning retains the old immediate target and settling delay:
        no intermediate position is invented before the initial command settles.
        All reported positions are commands, not measured mechanical feedback.
        """
        target = clamp_angle(target_angle)
        duration = self.movement_duration_ms if duration_ms is None else int(duration_ms)
        if duration < 0:
            raise ValueError("duration_ms cannot be negative")
        async with self._lock:
            self._motion_id += 1
            self._target_angle_deg = target
            self._start_angle_deg = self.commanded_angle_deg if self.initialized else None
            self._duration_ms = duration
            self._elapsed_ms = 0
            self._progress = None if not self.initialized else 0.0
            self._moving = True
            initializing = not self.initialized
            started = ticks_ms()
            try:
                if initializing:
                    self.commanded_angle_deg = None
                    self._write_pwm(target)
                    self._emit("initializing", force=True)
                else:
                    self._emit("started", force=True)
                while self._elapsed_ms < duration:
                    if not initializing:
                        self._progress = self._elapsed_ms / duration
                        angle = self._start_angle_deg + (target - self._start_angle_deg) * self._progress
                        self.write_angle(angle)
                        self._emit("moving")
                    else:
                        self._emit("initializing")
                    remaining = duration - self._elapsed_ms
                    await sleep_ms(min(self.command_interval_ms, remaining))
                    self._elapsed_ms = min(duration, max(0, ticks_diff(ticks_ms(), started)))
                self.write_angle(target)
                self.initialized = True
                self._moving = False
                self._elapsed_ms = duration
                self._progress = 1.0
                self._emit("finished", force=True)
                return target
            except BaseException:
                # Keep holding the last issued PWM command. Hardware shutdown
                # is explicitly handled by the owner with deinit().
                self._moving = False
                self._emit("interrupted", force=True)
                raise

    def deinit(self):
        if not self._enabled:
            return
        self._moving = False
        try:
            self.servo.deinit()
        finally:
            self._enabled = False
            self._emit("disabled", force=True)


class GripperBase(ServoMotor):
    def __init__(self, pin_number, telemetry=None,
                 command_interval_ms=COMMAND_INTERVAL_MS, movement_duration_ms=SERVO_MOVE_MS,
                 load_angle=180, drop_angle=12):
        self.load_angle = clamp_angle(load_angle)
        self.drop_angle = clamp_angle(drop_angle)
        super().__init__(pin_number, telemetry, "rotation", command_interval_ms, movement_duration_ms)

    async def move_to_drop_position(self):
        return await self.move_to(self.drop_angle)

    async def move_to_load_position(self):
        return await self.move_to(self.load_angle)


class Gripper(ServoMotor):
    def __init__(self, pin_number, telemetry=None,
                 command_interval_ms=COMMAND_INTERVAL_MS, movement_duration_ms=SERVO_MOVE_MS,
                 open_angle=90, closed_angle=180, claw_stroke_mm=None):
        self.open_angle = clamp_angle(open_angle)
        self.closed_angle = clamp_angle(closed_angle)
        if self.open_angle == self.closed_angle:
            raise ValueError("Claw open and closed angles must differ")
        if claw_stroke_mm is not None:
            claw_stroke_mm = float(claw_stroke_mm)
            if not math.isfinite(claw_stroke_mm) or claw_stroke_mm <= 0:
                raise ValueError("claw_stroke_mm must be positive when calibrated")
        self.claw_stroke_mm = claw_stroke_mm
        super().__init__(pin_number, telemetry, "claw", command_interval_ms, movement_duration_ms)

    def _state(self):
        state = super()._state()
        fraction = None
        if self.commanded_angle_deg is not None:
            fraction = (self.commanded_angle_deg - self.open_angle) / (self.closed_angle - self.open_angle)
            fraction = max(0.0, min(1.0, fraction))
        state["closure_fraction"] = fraction
        state["travel_mm"] = (fraction * self.claw_stroke_mm
                              if fraction is not None and self.claw_stroke_mm is not None else None)
        return state

    async def close(self):
        return await self.move_to(self.closed_angle)

    async def open(self):
        return await self.move_to(self.open_angle)


async def run_gripper_cycle(gripper_base, gripper):
    print("Placement detected. Closing gripper...")
    await gripper.close()
    print("Moving part to conveyor...")
    await gripper_base.move_to_drop_position()
    print("Releasing part...")
    await gripper.open()
    print("Part released. Gripper base returning...")
    await gripper_base.move_to_load_position()


async def prepare_gripper(gripper_base, gripper):
    print("Initialising gripper position...")
    tasks = []
    try:
        tasks.append(asyncio.create_task(gripper_base.move_to_load_position()))
        tasks.append(asyncio.create_task(gripper.open()))
        await asyncio.gather(*tasks)
    finally:
        # gather does not guarantee that a failed axis cancels its sibling.
        # Drain both before the owner disables PWM during error/shutdown cleanup.
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def gripper_task(sensor, gripper_base, gripper, telemetry=None):
    sensor_armed = True
    ready_reported = False
    while True:
        sensor_value = sensor.read_u16()
        if not ready_reported and telemetry is not None:
            telemetry.emit("placement/state",
                           {"sensor_u16": sensor_value, "trigger_level": SENSOR_TRIGGER_LEVEL,
                            "reset_level": SENSOR_RESET_LEVEL, "armed": True},
                           event="ready", force=True)
            ready_reported = True
        if not sensor_armed and sensor_value < SENSOR_RESET_LEVEL:
            sensor_armed = True
            if telemetry is not None:
                telemetry.emit("placement/state",
                               {"sensor_u16": sensor_value, "trigger_level": SENSOR_TRIGGER_LEVEL,
                                "reset_level": SENSOR_RESET_LEVEL, "detected": False, "armed": True},
                               event="rearmed", force=True)
        if sensor_armed and sensor_value > SENSOR_TRIGGER_LEVEL:
            sensor_armed = False
            if telemetry is not None:
                telemetry.emit("placement/state",
                               {"sensor_u16": sensor_value, "trigger_level": SENSOR_TRIGGER_LEVEL,
                                "reset_level": SENSOR_RESET_LEVEL, "detected": True, "armed": False},
                               event="detected", force=True)
            await run_gripper_cycle(gripper_base, gripper)
        await sleep_ms(POLL_INTERVAL_MS)
