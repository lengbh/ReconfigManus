import asyncio
from machine import ADC

from conveyor import Conveyor
from gripper import Gripper, GripperBase, gripper_task, prepare_gripper
from wifi_connection import connect_wifi


NFC_SDA_PIN = 4
NFC_SCL_PIN = 5
GRIPPER_BASE_SERVO_PIN = 9
GRIPPER_SERVO_PIN = 10
MOTOR_IN1_PIN = 17
MOTOR_IN2_PIN = 27
MOTOR_PWM_PIN = None
PLACEMENT_SENSOR_PIN = 26
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"


async def run_system(conveyor, sensor, gripper_base, gripper):
    await prepare_gripper(gripper_base, gripper)

    print("System ready.")

    await asyncio.gather(
        gripper_task(sensor, gripper_base, gripper),
        conveyor.run(),
        connect_wifi(WIFI_SSID, WIFI_PASSWORD),
    )


def main():
    gripper_base = GripperBase(GRIPPER_BASE_SERVO_PIN)
    gripper = Gripper(GRIPPER_SERVO_PIN)
    conveyor = None

    try:
        sensor = ADC(PLACEMENT_SENSOR_PIN)
        conveyor = Conveyor(
            motor_in1_pin=MOTOR_IN1_PIN,
            motor_in2_pin=MOTOR_IN2_PIN,
            motor_pwm_pin=MOTOR_PWM_PIN,
            nfc_sda_pin=NFC_SDA_PIN,
            nfc_scl_pin=NFC_SCL_PIN,
        )
        # run the program
        asyncio.run(
            run_system(conveyor, sensor, gripper_base, gripper)
        )
    except KeyboardInterrupt:
        print("Shutdown requested.")
    finally:
        if conveyor is not None:
            conveyor.cleanup()
        gripper_base.deinit()
        gripper.deinit()
        print("System stopped safely.")


if __name__ == "__main__":
    main()
