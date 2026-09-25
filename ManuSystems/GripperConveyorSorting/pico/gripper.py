from machine import Pin, PWM


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


class RobotBase(ServoMotor):
    def move_to_drop_position(self):
        self.write_angle(12)

    def move_to_load_position(self):
        self.write_angle(180)


class Gripper(ServoMotor):
    def close(self):
        self.write_angle(180)

    def open(self):
        self.write_angle(90)
