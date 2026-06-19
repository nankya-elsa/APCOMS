"""
Booking Validator Component for APCOMS

Validates QR scan payloads against Firebase booking records and
manages the lifecycle transition from 'reserved' to 'active' when
a passenger successfully scans their QR code at the shuttle entrance.

This component owns ALL booking validation logic. The QR scanner
hands it a payload string and gets back a structured result — either
a confirmation that the booking is now active, or a clear rejection
reason explaining why the scan was not accepted.

The validator does not handle camera reading (that's QRScanner's job)
or main.py orchestration (that's the scanner runtime's job). It is
purely concerned with the rules of valid boarding.

Validation rules enforced (per Phase 3 of the booking integration plan):
  1. The booking referenced by the payload must exist in Firebase
  2. The booking's current status must be 'reserved'
  3. The booking's pickup_stop must match the shuttle's current_stop
"""

import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

SERVER_TIMESTAMP = {".sv": "timestamp"}

load_dotenv()

logger = logging.getLogger(__name__)


class BookingValidator:
    """
    Validates QR scan payloads against Firebase booking records.

    Firebase interactions are lazily initialized — the validator
    can be constructed and tested without an active Firebase
    connection. The real Firebase client is loaded the first time
    a validation call actually needs to read or write Firebase.
    """

    def __init__(self):
        """
        Initialize the BookingValidator.

        Firebase clients are not initialized here so the class
        can be instantiated freely in tests. Production code paths
        call _ensure_firebase() before any Firebase operation,
        which lazily loads credentials and connects to the
        Realtime Database the first time it's needed.
        """
        self._firebase_ready = False

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK using credentials
        from the path stored in the FIREBASE_CREDENTIALS_PATH
        environment variable. Idempotent — safe to call multiple
        times; only the first call actually initializes.

        This pattern mirrors firebase_sync.py's approach so the
        whole counting module shares the same Firebase app and
        credentials.
        """
        if self._firebase_ready:
            return

        if firebase_admin._apps:
            self._firebase_ready = True
            return

        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
        database_url = os.getenv("FIREBASE_DATABASE_URL")

        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})
            self._firebase_ready = True
            logger.info("Firebase initialized for BookingValidator")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def parse_payload(self, payload):
        """
        Parse a QR payload string into a structured dictionary.

        The QR payload is the JSON string written by Cissy's mobile
        app at booking creation. It contains the booking ID and
        related metadata that the validator needs to look up the
        record in Firebase.

        Resilient to malformed input: returns None for invalid JSON,
        empty strings, or payloads missing the required bookingId
        field. Callers can use a None result as a signal to reject
        the scan with a clear "Invalid QR code" message rather than
        having to handle exceptions.

        Args:
            payload: A JSON string read from a QR code.

        Returns:
            A dictionary with the parsed fields, or None if the
            payload could not be parsed or is missing bookingId.
        """
        if not payload:
            return None

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        if "bookingId" not in data:
            return None

        if "t" not in data:
            return None

        return data

    def fetch_booking(self, booking_id):
            """
            Fetch a booking record from Firebase by its ID.

            Looks up /bookings/{booking_id} in the Realtime Database
            and returns the record as a dictionary. Returns None if
            the booking does not exist or if Firebase is unreachable.

            Resilience matters here: a scanner running at a shuttle
            gate cannot afford to crash on a transient network blip.
            Any Firebase exception becomes a clean None return so the
            caller can show a friendly "Try again" message.

            Args:
                booking_id: The Firebase push key of the booking,
                            extracted from the QR payload.

            Returns:
                The booking dictionary if found, or None if missing
                or unreachable.
            """
            self._ensure_firebase()

            try:
                ref = db.reference(f"bookings/{booking_id}")
                data = ref.get()
                if data is None:
                    return None
                return data
            except Exception as e:
                logger.error(f"Error fetching booking {booking_id}: {e}")
                return None

    def validate_scan(self, payload, current_stop):
        """
        Validate a complete QR scan against Firebase booking rules.

        This is the main public entry point for the booking
        validation flow. The QR scanner runtime calls this method
        with the raw payload string from the camera and the
        current shuttle stop, and gets back a structured result
        indicating whether the scan is valid and, if not, why.

        Validation runs in this order so the earliest failing rule
        determines the rejection reason:
          1. Payload parses to a dict with a bookingId
          2. Booking exists in Firebase
          3. Booking status is 'reserved'
          4. Booking pickup_stop matches the current shuttle stop

        Returns a dict that the orchestrator script can inspect
        to display the right terminal message, decide whether to
        proceed with marking the booking active, and choose
        whether to launch main.py.

        Args:
            payload:      The raw QR payload string (JSON).
            current_stop: The shuttle's current stop name.

        Returns:
            A result dict with shape:
              {
                  "valid": bool,
                  "booking": dict or None,
                  "reason": str    (only when valid is False)
              }

            Reason values:
              - 'invalid_payload':   QR string is not parseable
              - 'booking_not_found': Booking ID missing in Firebase
              - 'wrong_status':      Booking is not in 'reserved' state
              - 'wrong_pickup_stop': Booking pickup does not match
                                     the shuttle's current stop
              - 'invalid_token':     Token in QR does not match the
                                     booking's stored qr_token
        """
        # rule 1: parse the payload
        data = self.parse_payload(payload)
        if data is None:
            return {"valid": False, "booking": None, "reason": "invalid_payload"}

        booking_id = data["bookingId"]

        # rule 2: booking exists
        booking = self.fetch_booking(booking_id)
        if booking is None:
            return {"valid": False, "booking": None, "reason": "booking_not_found"}

        # rule 3: status is reserved
        status = booking.get("status")
        if status != "reserved":
            return {"valid": False, "booking": booking, "reason": "wrong_status"}

        # rule 4: pickup stop matches current shuttle stop
        if booking.get("pickup_stop") != current_stop:
            return {"valid": False, "booking": booking, "reason": "wrong_pickup_stop"}

        # rule 5: token in payload matches token stored on booking
        if data.get("t") != booking.get("qr_token"):
            return {"valid": False, "booking": booking, "reason": "invalid_token"}

        return {"valid": True, "booking": booking}

    def mark_as_active(self, booking):
        """
        Transition a validated booking to 'active' status.

        Called by the QR scanner runtime after validate_scan
        returns success. This method performs an atomic multi-path
        update to Firebase, writing the status change and
        boarded_at timestamp to both /bookings/{id} and
        /user_bookings/{uid}/{id} in a single operation.

        Mirrors the multi-path update pattern used by Cissy's
        mobile app at booking creation, so the two collections
        stay perfectly in sync.

        Args:
            booking: The booking dict returned by validate_scan().
                     Must include booking_id and user_uid.

        Returns:
            True on success, False if Firebase rejects the update
            or if the booking record is missing required fields
            (e.g. no user_uid — indicates corrupt data).
        """
        booking_id = booking.get("booking_id")
        user_uid = booking.get("user_uid")

        if not booking_id or not user_uid:
            logger.error(f"Cannot mark booking active — missing booking_id or user_uid: {booking}")
            return False

        self._ensure_firebase()

        try:
            updates = {
                f"bookings/{booking_id}/status": "active",
                f"bookings/{booking_id}/boarded_at": SERVER_TIMESTAMP,
                f"user_bookings/{user_uid}/{booking_id}/status": "active",
                f"user_bookings/{user_uid}/{booking_id}/boarded_at": SERVER_TIMESTAMP,
            }
            db.reference("/").update(updates)
            logger.info(f"Booking {booking_id} marked as active")
            return True
        except Exception as e:
            logger.error(f"Error marking booking {booking_id} as active: {e}")
            return False
