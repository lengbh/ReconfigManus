import time
from nfc_reader import NFCReader
from motor_driver import Motor

# === Configuration ===
IN1 = 17
IN2 = 27
PWM_PIN = None
CONVEYOR_SPEED = 100
RUN_DURATION_BOX = 4
RUN_DURATION_OUT = 3
SCAN_TIMEOUT = 0.3    # NFC poll timeout (keep short for responsiveness)

def main():
    # --- Hardware init ---
    print("Initialising motor...")
    motor = Motor(IN1, IN2, PWM_PIN)

    print("Initialising NFC reader...")
    nfc = NFCReader()

    print("System ready. Scanning for NFC tags...\n")

    try:
        while True:
            uid = nfc.read_part_id(timeout=SCAN_TIMEOUT)

            if uid:
                print(f"Tag detected: {uid}")

                if uid % 2 == 0:
                    print(f"Odd parts. Starting conveyor into the box...")
                    motor.run_forward(CONVEYOR_SPEED)
                    time.sleep(RUN_DURATION_BOX)
                else:
                    print(f"Even parts. Starting conveyor out of the module...")
                    motor.run_backward(CONVEYOR_SPEED)
                    time.sleep(RUN_DURATION_OUT)

                motor.stop()
                print("Conveyor stopped. Resuming scan...\n")
                time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nShutdown requested.")

    finally:
        motor.stop()
        motor.cleanup()
        print("GPIO cleaned up. Bye.")

if __name__ == "__main__":
    main()
