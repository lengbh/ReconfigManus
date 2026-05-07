"""
Motor Driver Control Script

Hardware:
- Raspberry Pi (GPIO using BCM mode)
- Motor driver: fischertechnik SBC Motor Driver 2 (H-bridge type)
- External power supply matched to motor type

---

## Motor types (fischertechnik)

We use two categories of motors:
1. Low-voltage motors:
   - 5V / 9V motors (most common fischertechnik motors)
   - Use: 9V power supply (typical)
2. High-voltage motors:
   - 24V motors (industrial / stronger torque)
   - Use: 24V power supply

⚠️ There is typically NO 12V motor in this setup
→ Always match supply voltage to motor rating

---

## Power wiring

Motor supply:
VCC (motor) -> 9V OR 24V (depending on motor)
GND         -> Power GND

Raspberry Pi:
Powered separately (5V ONLY)

CRITICAL:
Raspberry Pi GND must connect to motor GND (shared ground)

---

## Control pins (BCM numbering)

```
IN1 -> GPIO17
IN2 -> GPIO27
ENA (PWM) -> GPIO18
```

---

## Motor connection

```
Motor connected to driver output (e.g., M1)
```

---

## Control logic

```
IN1=1, IN2=0 -> forward
IN1=0, IN2=1 -> backward
IN1=0, IN2=0 -> stop
PWM (ENA) controls speed (0–100%)
```

---

## Pre-run GPIO testing (recommended)

Before running Python, verify wiring manually:

Set pin as output:
pinctrl set 17 op

Toggle HIGH/LOW:
pinctrl set 17 dh
pinctrl set 17 dl

Example:
pinctrl set 17 op
pinctrl set 17 dh
pinctrl set 17 dl

Repeat for:
GPIO27 (IN2)
GPIO18 (PWM, optional)

Expected:
- Driver input toggles
- Motor may react if enabled
- Confirms wiring BEFORE Python

---

## ⚠️ Voltage & safety notes (CRITICAL)

- Match voltage strictly:
  9V motor  -> 9V supply
  24V motor -> 24V supply
- NEVER:
  - connect 9V/24V to Raspberry Pi
  - connect motor VCC to GPIO pins
- Control pins (IN1/IN2/ENA):
  → 3.3V logic ONLY (safe for Pi)
- Check driver capability:
  → NOT all drivers support 24V
  → verify before connecting 24V

---

## Usage

python3 -i motor_driver.py

Example:
>>> motor.run_forward(50)
>>> motor.run_backward(80)
>>> motor.stop()
"""

import RPi.GPIO as GPIO
import time

class Motor:
    def __init__(self, pin_in1, pin_in2, pin_pwm=None, freq=1000):
        self.in1 = pin_in1
        self.in2 = pin_in2
        self.pwm_pin = pin_pwm
    
        GPIO.setmode(GPIO.BCM)
    
        GPIO.setup(self.in1, GPIO.OUT)
        GPIO.setup(self.in2, GPIO.OUT)
    
        # PWM setup
        self.pwm = None
        if self.pwm_pin is not None:
            GPIO.setup(self.pwm_pin, GPIO.OUT)
            self.pwm = GPIO.PWM(self.pwm_pin, freq)
            self.pwm.start(0)
    
        self.stop()
    
    def run_forward(self, speed=100):
        GPIO.output(self.in1, 1)
        GPIO.output(self.in2, 0)
        self._set_speed(speed)
    
    def run_backward(self, speed=100):
        GPIO.output(self.in1, 0)
        GPIO.output(self.in2, 1)
        self._set_speed(speed)
    
    def stop(self):
        GPIO.output(self.in1, 0)
        GPIO.output(self.in2, 0)
        if self.pwm:
            self.pwm.ChangeDutyCycle(0)
    
    def _set_speed(self, speed):
        if self.pwm:
            speed = max(0, min(100, speed))
            self.pwm.ChangeDutyCycle(speed)
    
    def cleanup(self):
        if self.pwm:
            self.pwm.stop()
        GPIO.cleanup()
    
# =====================

# Example usage

# =====================

IN1 = 17
IN2 = 27
motor = Motor(IN1, IN2, None)