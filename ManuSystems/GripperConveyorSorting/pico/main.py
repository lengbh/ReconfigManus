import asyncio
from machine import ADC, Pin
from time import sleep

import mqtt_config as settings
from conveyor import Conveyor
from crash_log import log_background_exception, save_last_traceback
from gripper import (
    Gripper, GripperBase, gripper_task, prepare_gripper,
)
from mqtt_connection import MqttPublisher
from telemetry import Telemetry
from wifi_connection import connect_wifi, wifi_status_task


NFC_SDA_PIN = 4
NFC_SCL_PIN = 5
GRIPPER_LED_PIN = 6
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


def release_resources(publisher, conveyor, gripper_base, gripper, gripper_led=None):
    """Attempt every shutdown action even if one peripheral raises an error."""
    first_error = None
    for resource, method in ((publisher, "close"), (conveyor, "cleanup"),
                             (gripper_base, "deinit"), (gripper, "deinit"),
                             (gripper_led, "off")):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception as error:
                print("Shutdown cleanup failed:", method, error)
                if first_error is None:
                    first_error = error
    if first_error is not None:
        raise first_error


async def run_system(
    conveyor, sensor, gripper_base, gripper, telemetry=None, publisher=None,
    gripper_led=None,
):
    """Run local control independently of broker availability."""
    tasks = []
    loop = asyncio.get_event_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(log_background_exception)
    try:
        if publisher is not None:
            tasks.append(asyncio.create_task(publisher.run()))
            if publisher.owns_wifi:
                wifi = wifi_status_task(telemetry=telemetry, publisher=publisher)
            else:
                wifi = connect_wifi(settings.WIFI_SSID, settings.WIFI_PASSWORD,
                                    telemetry=telemetry, publisher=publisher)
        else:
            wifi = connect_wifi(settings.WIFI_SSID, settings.WIFI_PASSWORD,
                                telemetry=telemetry)
        tasks.append(asyncio.create_task(wifi))

        # Position both axes simultaneously at startup; networking never gates
        # physical initialization or the autonomous sorting sequence.
        await prepare_gripper(gripper_base, gripper)
        print("System ready.")
        tasks.extend([
            asyncio.create_task(gripper_task(
                sensor, gripper_base, gripper, telemetry=telemetry,
                activity_led=gripper_led,
            )),
            asyncio.create_task(conveyor.run()),
        ])
        await asyncio.gather(*tasks)
    finally:
        try:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if publisher is not None:
                publisher.close()
        finally:
            loop.set_exception_handler(previous_handler)


def main():
    status_led = Pin("LED", Pin.OUT)
    status_led.off()
    gripper_base = None
    gripper = None
    gripper_led = None
    conveyor = None
    publisher = None
    crash_logged = False
    try:
        gripper_led = Pin(GRIPPER_LED_PIN, Pin.OUT, value=0)
        gripper_led.on()
        # Show the power-on pulse before starting peripherals or async tasks.
        sleep(1)
        gripper_led.off()
        telemetry = Telemetry(
            publish_hz=settings.TELEMETRY_HZ,
            event_capacity=settings.TELEMETRY_EVENT_CAPACITY,
            device_id=device_id(),
        )
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
            fault_logger=save_last_traceback,
        )
        publisher = MqttPublisher(telemetry, settings)
        asyncio.run(run_system(
            conveyor, sensor, gripper_base, gripper, telemetry, publisher,
            gripper_led=gripper_led,
        ))
    except KeyboardInterrupt:
        print("Shutdown requested.")
    except Exception as error:
        crash_logged = save_last_traceback(error)
        raise
    finally:
        try:
            release_resources(publisher, conveyor, gripper_base, gripper,
                              gripper_led=gripper_led)
        except Exception as error:
            # Keep the initiating traceback if shutdown raises another error.
            save_last_traceback(error, source="shutdown cleanup", append=crash_logged)
            raise
        finally:
            # Network tasks have finished, so their LED cleanup cannot undo this.
            # Keep the stopped indication even if peripheral cleanup fails.
            status_led.on()
        print("System stopped safely.")


if __name__ == "__main__":
    main()
