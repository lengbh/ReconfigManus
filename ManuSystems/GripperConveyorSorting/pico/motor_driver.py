from machine import Pin, PWM


class Motor:
    def __init__(self, pin_in1, pin_in2, pin_pwm=None, freq=1000):
        self.in1 = Pin(pin_in1, Pin.OUT, value=0)
        self.in2 = Pin(pin_in2, Pin.OUT, value=0)
        self.pwm = None

        if pin_pwm is not None:
            self.pwm = PWM(Pin(pin_pwm))
            self.pwm.freq(freq)
            self.pwm.duty_u16(0)

    def run_forward(self, speed=100):
        self.in1.value(1)
        self.in2.value(0)
        self._set_speed(speed)

    def run_backward(self, speed=100):
        self.in1.value(0)
        self.in2.value(1)
        self._set_speed(speed)

    def stop(self):
        self.in1.value(0)
        self.in2.value(0)
        if self.pwm:
            self.pwm.duty_u16(0)

    def _set_speed(self, speed):
        if self.pwm:
            speed = max(0, min(100, speed))
            self.pwm.duty_u16(round(speed * 65535 / 100))

    def cleanup(self):
        self.stop()
        if self.pwm:
            self.pwm.deinit()
