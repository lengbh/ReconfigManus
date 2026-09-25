import asyncio
from machine import ADC

from gripper import Gripper, RobotBase
from motor_driver import Motor
from nfc_reader import NFCReader
from part_uid_dict import get_part_id


NFC_SDA_PIN = 4
NFC_SCL_PIN = 5
BASE_SERVO_PIN = 9
GRIPPER_SERVO_PIN = 10
MOTOR_IN1_PIN = 17
MOTOR_IN2_PIN = 27
MOTOR_PWM_PIN = None
PLACEMENT_SENSOR_PIN = 26

CONVEYOR_SPEED = 100
RUN_DURATION_BOX_MS = 4000
RUN_DURATION_OUT_MS = 3000
SERVO_MOVE_MS = 1500
NFC_SCAN_TIMEOUT = 0.05
POLL_INTERVAL_MS = 10

SENSOR_TRIGGER_LEVEL = 61200
SENSOR_RESET_LEVEL = 58000
TAG_REMOVAL_CONFIRMATIONS = 3


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


def uid_to_hex(uid):
    return "".join("{:02X}".format(byte) for byte in uid)


async def run_gripper_cycle(base, gripper):
    print("Placement detected. Closing gripper...")
    gripper.close()
    await sleep_ms(SERVO_MOVE_MS)

    print("Moving part to conveyor...")
    base.move_to_drop_position()
    await sleep_ms(SERVO_MOVE_MS)

    print("Releasing part...")
    gripper.open()
    await sleep_ms(SERVO_MOVE_MS)

    base.move_to_load_position()
    print("Part released. Base returning...")
    await sleep_ms(SERVO_MOVE_MS)


async def gripper_task(
    sensor,
    base,
    gripper,
):
    sensor_armed = True

    while True:
        sensor_value = sensor.read_u16()

        if not sensor_armed and sensor_value < SENSOR_RESET_LEVEL:
            sensor_armed = True

        if sensor_armed and sensor_value > SENSOR_TRIGGER_LEVEL:
            sensor_armed = False
            await run_gripper_cycle(base, gripper)

        await sleep_ms(POLL_INTERVAL_MS)


async def wait_for_tag_removal(reader):
    missing_reads = 0
    print("Remove tag...")

    while missing_reads < TAG_REMOVAL_CONFIRMATIONS:
        uid = reader.read_uid(timeout=NFC_SCAN_TIMEOUT)

        if uid:
            missing_reads = 0
        else:
            missing_reads += 1

        await sleep_ms(POLL_INTERVAL_MS)


async def process_tag(uid, reader, motor):
    uid_hex = uid_to_hex(uid)
    part_id = get_part_id(uid_hex)

    try:
        if part_id is None:
            print("Unknown tag UID:", uid_hex)
        elif part_id % 2 == 0:
            print("Even part", part_id, "- conveyor forward...")
            motor.run_forward(CONVEYOR_SPEED)
            await sleep_ms(RUN_DURATION_BOX_MS)
        else:
            print("Odd part", part_id, "- conveyor backward...")
            motor.run_backward(CONVEYOR_SPEED)
            await sleep_ms(RUN_DURATION_OUT_MS)
    finally:
        motor.stop()

    print("Conveyor stopped.")
    await wait_for_tag_removal(reader)
    print("Ready for next part.")


async def conveyor_task(reader, motor):
    while True:
        uid = reader.read_uid(timeout=NFC_SCAN_TIMEOUT)

        if uid:
            await process_tag(uid, reader, motor)
        else:
            await sleep_ms(POLL_INTERVAL_MS)


async def run_system(motor, reader, sensor, base, gripper):
    print("Initialising gripper position...")
    base.move_to_load_position()
    gripper.open()
    await sleep_ms(SERVO_MOVE_MS)

    print("System ready.")

    await asyncio.gather(
        gripper_task(
            sensor,
            base,
            gripper,
        ),
        conveyor_task(
            reader,
            motor,
        ),
    )


def main():
    motor = Motor(MOTOR_IN1_PIN, MOTOR_IN2_PIN, MOTOR_PWM_PIN)
    base = RobotBase(BASE_SERVO_PIN)
    gripper = Gripper(GRIPPER_SERVO_PIN)

    try:
        sensor = ADC(PLACEMENT_SENSOR_PIN)
        reader = NFCReader(
            i2c_id=0,
            sda_pin=NFC_SDA_PIN,
            scl_pin=NFC_SCL_PIN,
        )
        asyncio.run(run_system(motor, reader, sensor, base, gripper))
    except KeyboardInterrupt:
        print("Shutdown requested.")
    finally:
        motor.cleanup()
        base.deinit()
        gripper.deinit()
        print("System stopped safely.")


if __name__ == "__main__":
    main()

