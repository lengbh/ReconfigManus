import asyncio
from machine import ADC

import mqtt_config as settings
from conveyor import Conveyor
from gripper import (
    Gripper, GripperBase, SENSOR_TRIGGER_LEVEL, SENSOR_RESET_LEVEL,
    gripper_task, prepare_gripper, sleep_ms,
)
from mqtt_connection import MqttPublisher
from telemetry import Telemetry
from wifi_connection import connect_wifi, wifi_status_task


NFC_SDA_PIN = 4
NFC_SCL_PIN = 5
GRIPPER_BASE_SERVO_PIN = 9
GRIPPER_SERVO_PIN = 10
MOTOR_IN1_PIN = 17
MOTOR_IN2_PIN = 27
MOTOR_PWM_PIN = None
PLACEMENT_SENSOR_PIN = 26


def device_id():
    try:
        from machine import unique_id
        from binascii import hexlify
        suffix = hexlify(unique_id()).decode()
    except (ImportError, AttributeError):
        suffix = "pico"
    return settings.MQTT_CLIENT_ID_PREFIX + "-" + suffix


def release_resources(publisher, conveyor, gripper_base, gripper):
    """Attempt every shutdown action even if one peripheral raises an error."""
    first_error = None
    for resource, method in ((publisher, "close"), (conveyor, "cleanup"),
                             (gripper_base, "deinit"), (gripper, "deinit")):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception as error:
                print("Shutdown cleanup failed:", method, error)
                if first_error is None:
                    first_error = error
    if first_error is not None:
        raise first_error


async def placement_telemetry_task(sensor, telemetry):
    """Sample throughout servo motion; the gripper task owns triggering."""
    detected = False
    while True:
        value = sensor.read_u16()
        if value > SENSOR_TRIGGER_LEVEL:
            detected = True
        elif value < SENSOR_RESET_LEVEL:
            detected = False
        telemetry.emit("placement/state", {
            "sensor_u16": value,
            "detected": detected,
            "trigger_level": SENSOR_TRIGGER_LEVEL,
            "reset_level": SENSOR_RESET_LEVEL,
        })
        await sleep_ms(telemetry.publish_interval_ms)


async def run_system(
    conveyor, sensor, gripper_base, gripper, telemetry=None, publisher=None
):
    """Run local control independently of broker availability."""
    tasks = []
    try:
        if publisher is not None:
            tasks.append(asyncio.create_task(publisher.run()))
            if publisher.owns_wifi:
                wifi = wifi_status_task(telemetry=telemetry)
            else:
                wifi = connect_wifi(settings.WIFI_SSID, settings.WIFI_PASSWORD,
                                    telemetry=telemetry)
        else:
            wifi = connect_wifi(settings.WIFI_SSID, settings.WIFI_PASSWORD,
                                telemetry=telemetry)
        tasks.append(asyncio.create_task(wifi))
        if telemetry is not None:
            tasks.append(asyncio.create_task(placement_telemetry_task(sensor, telemetry)))

        # Position both axes simultaneously at startup; networking never gates
        # physical initialization or the autonomous sorting sequence.
        await prepare_gripper(gripper_base, gripper)
        print("System ready.")
        tasks.extend([
            asyncio.create_task(gripper_task(
                sensor, gripper_base, gripper, telemetry=telemetry
            )),
            asyncio.create_task(conveyor.run()),
        ])
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if publisher is not None:
            publisher.close()


def main():
    gripper_base = None
    gripper = None
    conveyor = None
    publisher = None
    telemetry = Telemetry(
        publish_hz=settings.TELEMETRY_HZ,
        event_capacity=settings.TELEMETRY_EVENT_CAPACITY,
        device_id=device_id(),
    )
    try:
        gripper_base = GripperBase(
            GRIPPER_BASE_SERVO_PIN, telemetry=telemetry,
            command_interval_ms=settings.COMMAND_INTERVAL_MS,
            movement_duration_ms=settings.SERVO_MOVE_MS,
            load_angle=settings.BASE_LOAD_ANGLE, drop_angle=settings.BASE_DROP_ANGLE,
        )
        gripper = Gripper(
            GRIPPER_SERVO_PIN, telemetry=telemetry,
            command_interval_ms=settings.COMMAND_INTERVAL_MS,
            movement_duration_ms=settings.SERVO_MOVE_MS,
            open_angle=settings.CLAW_OPEN_ANGLE,
            closed_angle=settings.CLAW_CLOSED_ANGLE,
            claw_stroke_mm=settings.CLAW_STROKE_MM,
        )
        sensor = ADC(PLACEMENT_SENSOR_PIN)
        conveyor = Conveyor(
            motor_in1_pin=MOTOR_IN1_PIN, motor_in2_pin=MOTOR_IN2_PIN,
            motor_pwm_pin=MOTOR_PWM_PIN,
            nfc_sda_pin=NFC_SDA_PIN, nfc_scl_pin=NFC_SCL_PIN,
            telemetry=telemetry,
        )
        publisher = MqttPublisher(telemetry, settings)
        asyncio.run(run_system(
            conveyor, sensor, gripper_base, gripper, telemetry, publisher
        ))
    except KeyboardInterrupt:
        print("Shutdown requested.")
    finally:
        release_resources(publisher, conveyor, gripper_base, gripper)
        print("System stopped safely.")


if __name__ == "__main__":
    main()
