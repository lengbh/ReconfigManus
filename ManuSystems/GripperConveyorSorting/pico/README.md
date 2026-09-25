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
- `pico/gripper.py`
- `pico/motor_driver.py`
- `pico/nfc_reader.py`

No packages from `pi/requirements.txt` are needed on the Pico.

The complete pin allocation is:

- PN532 SDA: GP4 (physical pin 6)
- PN532 SCL: GP5 (physical pin 7)
- Robot base servo signal: GP9 (physical pin 12)
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
