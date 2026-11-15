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
- `pico/crash_log.py`
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
The onboard LED shows connection progress without needing a USB console:

- **Fast blinking** (100 ms on / 100 ms off): waiting for Wi-Fi.
- **Slow blinking** (500 ms on / 500 ms off): Wi-Fi connected, waiting for MQTT.
- **Off**: Wi-Fi and MQTT connected.
- **Steady on**: controller stopped, including shutdown after a Python exception.

Blinking resumes automatically if a connection drops. If MQTT is disabled or
misconfigured, the integrated program keeps blinking slowly once Wi-Fi connects.
When MQTT is enabled, the MQTT client owns reconnection and the LED task only
observes connection state; otherwise the standalone Wi-Fi task maintains the
connection. Running `wifi_connection.py` directly tests only Wi-Fi, so its LED
turns off once Wi-Fi connects.

The gripper robot's separate LED uses the GP6 signal (physical pin 9, active
high). At startup it turns on for one second, then off. When the light sensor
detects a part, it stays on throughout closing, moving to the conveyor, opening,
and returning to the load position. It turns off after the return finishes, or
if the cycle is interrupted or the controller shuts down.

No packages from `pi/requirements.txt` are needed on the Pico.

The complete pin allocation is:

- PN532 SDA: GP4 (physical pin 6)
- PN532 SCL: GP5 (physical pin 7)
- Gripper LED signal: GP6 (physical pin 9)
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

PN532 ACK and response reads retry `ETIMEDOUT` up to three attempts, with 10 ms
between attempts. Async retries yield so other controller tasks can run. The
bus runs at 100 kHz with a bounded 50 ms I2C transfer timeout.

Reader detection and initialization run in the background conveyor task, so a
reader left unresponsive at startup does not prevent the gripper or MQTT from
starting. Reader faults pause the conveyor and trigger recovery with a
one-second delay between attempts while the gripper and MQTT tasks continue.
Recovery clears a stuck SDA line with up to nine clock pulses, reinitializes
the I2C controller, aborts
the unfinished PN532 command, checks its firmware, and reapplies SAM
configuration. It does not restart the Pico or replay a conveyor movement.
Scanning resumes only after a successful reader response. A failed read is not
an absent tag; tag-removal confirmations restart after an outage so the same
part is not sorted twice. Invalid ACKs and frames also enter reader recovery.

The first failure in each outage is saved to `/last_error.txt`; repeated recovery
attempts do not repeatedly write to flash. MQTT status includes `nfc_connected`,
`nfc_error`, `nfc_faults`, and `nfc_recovery_attempts`. A PN532 that keeps SCL or
SDA low may still require its power/reset or wiring to be fixed; in that case
the conveyor remains stopped and recovery continues. Invalid pin/configuration
settings and unrelated control errors still stop the controller.


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

Set `MQTT_HOST` to the broker computer's address on the Pico's network.
An empty `MQTT_HOST` disables MQTT while local sorting and Wi-Fi continue.
Once Mosquitto is available:

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

For a Mac connected by Ethernet to a single-port TP-Link TL-WR802N, use
**Access Point** mode so Ethernet and the Pico's Wi-Fi share a LAN. For an
isolated setup without another DHCP server, give the access point a static LAN
address and enable its DHCP server. Use the Mac's **Ethernet** LAN IPv4 address
as `MQTT_HOST`; reserve that address in the router's DHCP settings so it remains
stable. A self-assigned `169.254.x.x` Ethernet address indicates the Mac has not
received a usable router LAN address. After changing `MQTT_HOST`, copy the
updated `mqtt_config.py` to the Pico and restart it.

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
| `conveyor/state` | `running`, `direction`, `speed_command_percent`, `pwm_enabled`, `duration_ms`, `part_id`, `nfc_connected`, `nfc_error` | QoS 0, retained |
| `placement/state` | `detected`, `armed` | QoS 0, retained |
| `part/event` | NFC `uid`, `part_id`, `recognized` | QoS 1, not retained |
| `status` | `online`, `mqtt_connected`, `wifi_connected`, `mqtt_enabled`, `reason`, `nfc_connected`, `nfc_error`, `nfc_faults`, `nfc_recovery_attempts` | QoS 0, retained |

The common envelope contains `schema_version`, `device_id`, `seq`, `uptime_ms`,
and `event`. `seq` is a controller-wide sequence number; consumers can deduplicate
QoS 1 messages. The retained Last Will reports `online: false` after unexpected
connection loss; its `seq` and `uptime_ms` are null because it is generated by the
broker. Retained poses are the most recently reported commands: check status
before presenting them as a live connection. State fields are merged so Wi-Fi
and MQTT status producers do not erase one another's fields.

Placement reports semantic state changes, rather than periodic sensor samples.
The gripper controller emits `ready` once after initialization, with `armed: true`
and `detected` from the first reading. A startup reading above the trigger emits
`ready` with `detected: true`, immediately followed by `detected` with
`armed: false`. A first reading in the hysteresis band starts with
`detected: false`. Later `detected` events carry `detected: true, armed: false`;
a reading below the reset threshold emits `rearmed` with
`detected: false, armed: true`. Both thresholds remain internal to the Pico.
Unchanged readings emit nothing, including while the gripper completes a cycle.
A broker reconnect republishes the latest snapshot with its existing sequence
number; it does not create a new detection event. ADC values and thresholds are
not sent over MQTT.

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

## Crash traceback log

Unhandled startup/controller errors and hardware-cleanup failures are saved to
`/last_error.txt` on the Pico's internal flash. Unhandled background-task errors,
including errors in the MQTT client's detached tasks, also save a traceback.
The first NFC fault in each recovery episode is saved even though the controller
keeps running; its report is labelled `NFC reader fault; recovering`.
The report includes the source, MicroPython tick count, free heap, and traceback.
Normal restarts and manual stops preserve the file. The next recorded error
replaces it; a cleanup error during the same controller failure is appended so
the initiating traceback is retained. Handled MQTT connection retries do not
write to flash. The file is closed and the filesystem synced where supported.

After a failure, move the USB cable from the router to the Pico and open
`last_error.txt` from the Pico's filesystem in Thonny. Save a copy on the Mac
before running further diagnostics. Alternatively, print it from the REPL:

```python
with open("/last_error.txt") as log:
    print(log.read())
```

This captures Python exceptions; a hard freeze, sudden power loss, or an error
before the application imports finish may leave no new traceback. Logging does
not automatically restart the controller.

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
