import time

from motor_driver import Motor


IN1 = 17
IN2 = 27
PWM_PIN = None
SPEED = 100
MOVE_SECONDS = 3
STOP_SECONDS = 2


def main():
    motor = Motor(IN1, IN2, PWM_PIN)

    try:
        print("STOP")
        motor.stop()
        time.sleep(STOP_SECONDS)

        print("FORWARD")
        motor.run_forward(SPEED)
        time.sleep(MOVE_SECONDS)

        print("STOP")
        motor.stop()
        time.sleep(STOP_SECONDS)

        print("BACKWARD")
        motor.run_backward(SPEED)
        time.sleep(MOVE_SECONDS)
    finally:
        print("FINAL STOP")
        motor.cleanup()


if __name__ == "__main__":
    main()
