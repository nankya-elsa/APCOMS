"""
Manual smoke test for the QR scanner.

Opens the webcam and prints any QR payloads it sees.
Press 'q' in the preview window to quit.

This is NOT an automated test - it's a hands-on verification
that the scanner works against a real webcam.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from qr_scanner import QRScanner

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def handle_qr(payload):
    print(f"\n{'='*50}")
    print(f"QR DETECTED: {payload}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    print("APCOMS QR Scanner - Smoke Test")
    print("Hold a QR code up to the webcam")
    print("Press 'q' in the preview window to quit")
    print()

    scanner = QRScanner()
    scanner.run(on_qr_detected=handle_qr)

    print("\nScanner stopped. Bye!")
