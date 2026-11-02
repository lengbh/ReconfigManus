import asyncio

from machine import Pin, PWM


SERVO_MOVE_MS = 1500
POLL_INTERVAL_MS = 10

SENSOR_TRIGGER_LEVEL = 61200
SENSOR_RESET_LEVEL = 58000


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


class ServoMotor:
    MIN_DUTY = 1638
    MAX_DUTY = 8192

    def __init__(self, pin_number):
        self.servo = PWM(Pin(pin_number))
        self.servo.freq(50)

    def write_angle(self, angle):
        angle = max(0, min(180, angle))
        duty = int(
            self.MIN_DUTY
            + (angle / 180) * (self.MAX_DUTY - self.MIN_DUTY)
        )
        self.servo.duty_u16(duty)

    def deinit(self):
        self.servo.deinit()


class GripperBase(ServoMotor):
    def move_to_drop_position(self):
        self.write_angle(12)

    def move_to_load_position(self):
        self.write_angle(180)


class Gripper(ServoMotor):
    def close(self):
        self.write_angle(180)

    def open(self):
        self.write_angle(90)


async def run_gripper_cycle(gripper_base, gripper):
    print("Placement detected. Closing gripper...")
    gripper.close()
    await sleep_ms(SERVO_MOVE_MS)

    print("Moving part to conveyor...")
    gripper_base.move_to_drop_position()
    await sleep_ms(SERVO_MOVE_MS)

    print("Releasing part...")
    gripper.open()
    await sleep_ms(SERVO_MOVE_MS)

    gripper_base.move_to_load_position()
    print("Part released. Gripper base returning...")
    await sleep_ms(SERVO_MOVE_MS)


async def prepare_gripper(gripper_base, gripper):
    print("Initialising gripper position...")
    gripper_base.move_to_load_position()
    gripper.open()
    await sleep_ms(SERVO_MOVE_MS)


async def gripper_task(sensor, gripper_base, gripper):
    sensor_armed = True

    while True:
        sensor_value = sensor.read_u16()

        if not sensor_armed and sensor_value < SENSOR_RESET_LEVEL:
            sensor_armed = True

        if sensor_armed and sensor_value > SENSOR_TRIGGER_LEVEL:
            sensor_armed = False
            await run_gripper_cycle(gripper_base, gripper)

        await sleep_ms(POLL_INTERVAL_MS)
