import time
from machine import Pin

from nfc_reader import NFCReader
from part_uid_dict import get_part_id


SCAN_TIMEOUT = 0.3
BLINK_ON_SECONDS = 0.15
BLINK_OFF_SECONDS = 0.15
REMOVAL_CONFIRMATIONS = 3


def uid_to_hex(uid):
    return "".join("{:02X}".format(byte) for byte in uid)


def blink(led, count):
    for _ in range(count):
        led.on()
        time.sleep(BLINK_ON_SECONDS)
        led.off()
        time.sleep(BLINK_OFF_SECONDS)


def wait_for_tag_removal(reader):
    missing_reads = 0
    print("Remove tag...")

    while missing_reads < REMOVAL_CONFIRMATIONS:
        if reader.read_uid(timeout=SCAN_TIMEOUT):
            missing_reads = 0
        else:
            missing_reads += 1


def main():
    led = Pin("LED", Pin.OUT, value=0)
    reader = NFCReader()

    print("NFC test ready. Place a tag on the reader.")

    try:
        while True:
            uid = reader.read_uid(timeout=SCAN_TIMEOUT)
            if not uid:
                continue

            uid_hex = uid_to_hex(uid)
            part_id = get_part_id(uid_hex)

            if part_id is None:
                print("Unknown tag UID:", uid_hex)
            else:
                print("Detected part_id:", part_id, "UID:", uid_hex)
                blink(led, part_id)

            wait_for_tag_removal(reader)
            print("Ready for next tag.")
    finally:
        led.off()


if __name__ == "__main__":
    main()
