"""
Manual smoke test for the QR scanner + booking validator.

Opens the webcam, waits for a QR code, validates it against
Firebase (booking exists, status reserved, pickup matches current
shuttle stop, token matches), and prints the result.

This is NOT an automated test — it's a hands-on verification
that the full Phase 3 validation pipeline works end-to-end.

Before running:
  1. Ensure a test booking exists in Firebase with status=reserved
  2. Update CURRENT_STOP below to match the booking's pickup_stop
  3. Display the booking's qr_payload as a QR code on your phone
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from qr_scanner import QRScanner
from booking_validator import BookingValidator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# pretend the shuttle is currently at this stop - change as needed
# to match the pickup_stop of the booking you're testing with
CURRENT_STOP = "CONAS"


def handle_qr(payload):
    print(f"\n{'='*60}")
    print(f"QR PAYLOAD DETECTED:")
    print(f"  {payload}")
    print(f"{'='*60}")

    validator = BookingValidator()
    result = validator.validate_scan(payload, current_stop=CURRENT_STOP)

    if result["valid"]:
        booking = result["booking"]
        print(f"\n✅ VALID SCAN — marking booking as active")
        print(f"   Booking ID:  {booking.get('booking_id')}")
        print(f"   User:        {booking.get('user_uid')}")
        print(f"   Pickup:      {booking.get('pickup_stop')}")
        print(f"   Destination: {booking.get('destination_stop')}")

        success = validator.mark_as_active(booking)
        if success:
            print(f"\n✅ Booking transitioned: reserved → active")
        else:
            print(f"\n⚠️  Validation passed but mark_as_active failed!")
    else:
        print(f"\n❌ SCAN REJECTED — reason: {result['reason']}")
        if result.get("booking"):
            print(f"   Booking found but failed validation rule")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("APCOMS QR Scanner + Validator Smoke Test")
    print(f"Current stop (simulated): {CURRENT_STOP}")
    print("Hold a valid QR code up to the webcam")
    print("Press 'q' in the preview window to quit")
    print()

    scanner = QRScanner()
    scanner.run(on_qr_detected=handle_qr)

    print("\nScanner stopped. Bye!")
