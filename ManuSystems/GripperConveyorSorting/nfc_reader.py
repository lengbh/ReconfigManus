import board
import busio
from part_uid_dict import get_part_id
from adafruit_pn532.i2c import PN532_I2C

class NFCReader:
    def __init__(self, debug=False):
        # Initialize I2C + PN532
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.nfc = PN532_I2C(self.i2c, debug=debug)

        # Get firmware info
        ic, ver, rev, support = self.nfc.firmware_version
        print(f"PN532 detected: Firmware {ver}.{rev}")

        # Configure for reading parts
        self.nfc.SAM_configuration()

    def read_uid(self, timeout=0.5):
        """Read NFC part UID"""
        return self.nfc.read_passive_target(timeout=timeout)

    def read_part_id(self, timeout=0.5):
        """Read and convert the reading results UID to part id"""
        uid = self.read_uid(timeout=0.5)
        if not uid:
            return None
        # Convert UID bytes to hex string
        uid_hex = ''.join([f'{b:02X}' for b in uid])
        part_id = get_part_id(uid_hex)
        return part_id

    def wait_for_part(self):
        """Block until a part is detected"""
        print("Waiting for NFC part...")
        while True:
            uid = self.read_uid()
            if uid:
                return uid

    def print_part(self):
        """Continuously print detected parts"""
        print("Scanning for NFC parts...")
        try:
            while True:
                uid = self.read_uid()
                if uid:
                    print("part detected:", uid)
        except KeyboardInterrupt:
            print("\nStopped by user")
            
nfc = NFCReader()
