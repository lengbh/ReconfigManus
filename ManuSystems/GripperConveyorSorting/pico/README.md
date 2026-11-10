# Pico 2 W

This directory contains the MicroPython hardware implementations.

Default wiring:

- Motor driver `IN1`: GP17
- Motor driver `IN2`: GP27
- PN532 `SDA`: GP4
- PN532 `SCL`: GP5
- PN532 power: 3V3
- All devices: common GND

For the complete integrated machine, copy these files to the Pico filesystem
root:

- `pico/main.py` as `main.py`
- `common/part_uid_dict.py`
- `pico/conveyor.py`
- `pico/gripper.py`
- `pico/motor_driver.py`
- `pico/nfc_reader.py`
- `pico/wifi_connection.py`
- `pico/telemetry.py`
- `pico/mqtt_connection.py`
- `pico/mqtt_config.py`
- the complete `pico/mqtt_as/` directory
- your local `pico/secrets.py`, created from `pico/secrets.example.py`

Before starting the integrated program, copy `secrets.example.py` to `secrets.py`
and set `WIFI_SSID`, `WIFI_PASSWORD`, and any MQTT credentials there. Keep
`secrets.py` private; it is ignored by Git. Existing nonempty Wi-Fi settings were
preserved in the local ignored file during this update. Run `wifi_connection.py`
directly from Thonny to enter credentials interactively and test Wi-Fi alone.
The onboard LED blinks whenever Wi-Fi is disconnected. When MQTT is enabled,
the MQTT client owns reconnection and the LED task only observes the link;
otherwise the standalone Wi-Fi task maintains the connection.

No packages from `pi/requirements.txt` are needed on the Pico.

The complete pin allocation is:

- PN532 SDA: GP4 (physical pin 6)
- PN532 SCL: GP5 (physical pin 7)
- Gripper base servo signal: GP9 (physical pin 12)
- Gripper servo signal: GP10 (physical pin 14)
- Conveyor motor driver IN1: GP17 (physical pin 22)
- Optional conveyor PWM/ENA: GP18 (physical pin 24)
- Placement sensor analog output: GP26/ADC0 (physical pin 31)
- Conveyor motor driver IN2: GP27 (physical pin 32)

The servos and conveyor motor require suitable external power supplies. Connect
their grounds to Pico GND, but never connect the motor supply voltage to a GPIO
or 3V3 pin.

## Motor hardware test

With the motor raised so it cannot drive the mechanism unexpectedly, also copy
`pico/test_motor_hardware.py` to the Pico. Run that file manually from Thonny.
It executes stop, forward, stop, backward, and a final stop.

The default test assumes the motor driver's enable input is already enabled.
To test PWM, connect `ENA` to GP18 and change `PWM_PIN` in the test from `None`
to `18`.

## NFC hardware test

Configure the PN532 board for I2C mode, then connect:

- PN532 `SDA` to Pico GP4 (physical pin 6)
- PN532 `SCL` to Pico GP5 (physical pin 7)
- PN532 `VCC` to Pico 3V3 OUT (physical pin 36)
- PN532 `GND` to a Pico GND pin

Copy these files to the Pico filesystem root:

- `common/part_uid_dict.py`
- `pico/nfc_reader.py`
- `pico/test_nfc_hardware.py`

Run `test_nfc_hardware.py` manually from Thonny. A recognized tag prints its UID
and part ID, then blinks the onboard LED once per part ID. The next scan starts
after the tag is removed. An unrecognized tag prints its UID without blinking.


## Continuous motion telemetry

The gripper base and claw have independent asynchronous movement channels. Each
normal movement issues intermediate servo commands every 20 ms (approximately
50 Hz) for the configured 1500 ms duration. The original close, rotate to drop,
open, rotate to load sequence and pin assignments are retained. Startup sends
the two initial positions simultaneously and waits for settling; it does not
invent a starting angle or a measured position.

The network publisher reports each active topic at up to 20 Hz by default.
`started`, `moving`, `finished`, `interrupted`, `initializing`, and `disabled`
events describe the motion lifecycle. A bounded 32-event buffer preserves
recent transitions while normal progress samples coalesce to the latest value.
Control never waits for MQTT publication. After reconnection, old trajectories
and part events are discarded and the current state snapshots are republished.
NFC waiting uses cooperative async polling so servo commands and telemetry can
continue while the PN532 is pending.

These are commanded servo positions, with `position_source: "commanded"`.
There is no encoder feedback or measured belt speed in this controller.
`initialized: true` means the initial positioning delay has completed, not
that physical homing or contact has been verified.

## MQTT setup

The broker is not configured yet: `MQTT_HOST = ""` deliberately keeps MQTT
inactive, while local sorting and Wi-Fi continue. Once Mosquitto is available:

1. Set `MQTT_HOST` in `mqtt_config.py` to the broker computer's numeric LAN IPv4
   address, for example `192.168.1.20`, and verify `MQTT_PORT` (default 1883).
   Hostnames are rejected because the underlying client performs synchronous DNS.
   The broker must listen on the LAN address; `localhost`/loopback is not reachable
   from the Pico. Broker installation and configuration are separate from this
   firmware update.
2. Fill in Wi-Fi and broker credentials in `secrets.py`.
3. Copy the listed files and `mqtt_as` folder to the Pico, with `part_uid_dict.py`
   from `common/` at the filesystem root. Restart the controller.
4. From the broker computer, inspect messages with
   `mosquitto_sub -h BROKER_IP -p 1883 -t 'gripper_conveyor/#' -v`
   (supply your broker's authentication options when required).

The vendored client is `mqtt_as` 0.8.5, pinned to upstream commit
`4dbce9ba8df169b1c1356deba14aec0bf7cde664`. Its MIT licence and source provenance
are in `mqtt_as/LICENSE` and `mqtt_as/UPSTREAM.txt`. No CPython Paho package is
needed on the Pico. MQTT uses a separate task with bounded connection and
publication waits. The driver manages Wi-Fi and broker reconnection. The main
controller cancels background tasks and releases motor/PWM resources on shutdown.
This version publishes telemetry; actuation remains the local sorting program.

## Topics and messages

All messages are JSON. The default prefix is `gripper_conveyor`.

| Topic suffix | Main fields | Delivery |
|---|---|---|
| `rotation/state` | `commanded_angle_deg`, `target_angle_deg`, `moving`, `motion_id`, `progress` | QoS 0, retained |
| `claw/state` | rotation fields plus `closure_fraction`, `travel_mm` | QoS 0, retained |
| `conveyor/state` | `running`, `direction`, `speed_command_percent`, `pwm_enabled`, `duration_ms`, `part_id` | QoS 0, retained |
| `placement/state` | `sensor_u16`, `detected`, `armed`, hysteresis thresholds | QoS 0, retained |
| `part/event` | NFC `uid`, `part_id`, `recognized` | QoS 1, not retained |
| `status` | `online`, `mqtt_connected`, `wifi_connected`, `mqtt_enabled`, `reason` | QoS 0, retained |

The common envelope contains `schema_version`, `device_id`, `seq`, `uptime_ms`,
and `event`. `seq` is a controller-wide sequence number; consumers can deduplicate
QoS 1 messages. The retained Last Will reports `online: false` after unexpected
connection loss; its `seq` and `uptime_ms` are null because it is generated by the
broker. Retained poses are the most recently reported commands: check status
before presenting them as a live connection. State fields are merged so Wi-Fi,
MQTT and placement producers do not erase one another's fields.

An illustrative rotation update is:

```json
{"schema_version":1,"device_id":"gripper-conveyor-DEVICE_ID","seq":42,"uptime_ms":3250,"event":"moving","axis":"rotation","commanded_angle_deg":96.0,"start_angle_deg":180.0,"target_angle_deg":12.0,"motion_id":2,"duration_ms":1500,"elapsed_ms":750,"progress":0.5,"moving":true,"initialized":true,"servo_enabled":true,"position_source":"commanded"}
```

`uptime_ms` is elapsed controller time rather than wall-clock UTC. Start a new
consumer timeline after a controller restart, when sequence and uptime reset.
Motion targets and durations, command interval, telemetry rate and buffer size
are configurable in `mqtt_config.py`.

## Claw linear calibration

`closure_fraction` is 0 at the configured open angle (90 degrees) and 1 at the
closed angle (180 degrees), including intermediate values during motion. To
publish linear travel, measure the claw's full stroke in millimetres and set
`CLAW_STROKE_MM` in `mqtt_config.py`. Travel is then
`closure_fraction * CLAW_STROKE_MM`, measured from the open position toward closed.
With the default `None`, `travel_mm` is null; use the normalized fraction to
animate the existing model without inventing a physical stroke length. If the
mechanism has a nonlinear angle/travel relationship, replace this calibration
with measured mapping points before interpreting it as millimetres.

## Validation

Run host-side tests from `GripperConveyorSorting` with Python 3.10 or newer:

```sh
python3 -m unittest discover -s tests -v
```

Tests substitute PWM, ADC, I2C and networking hardware. They verify motion
profiles and lifecycle events, cancellation, bounded telemetry, NFC timeouts and
cooperative waiting, sorting directions, MQTT recovery, topic semantics and
controller shutdown. Physical stroke, servo following accuracy, electrical
behavior and timing on your Pico still require hardware validation. The update
is not automatically flashed to the board.
