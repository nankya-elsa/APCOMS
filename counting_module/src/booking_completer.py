"""
Booking Completer Component for APCOMS

Closes the booking lifecycle by transitioning bookings from
'active' to 'completed' when a passenger alights at their
destination stop. Called by main.py on each detected alighting
event so the mobile app reflects accurate booking history.

This is the third and final lifecycle component:
  - BookingValidator   (Phase 3): reserved -> active (QR scan)
  - BookingCompleter   (Phase 6): active -> completed (alighting)
  - (auto-cancel)      (Phase 7): reserved -> cancelled (no-show)

When called, the completer queries Firebase for active bookings
whose destination matches the shuttle's current stop, picks the
oldest one (first to board is first to alight assumption), and
performs an atomic multi-path update to mark it completed in
both /bookings/{id} and /user_bookings/{uid}/{id}.

The component is resilient to no-match scenarios — non-app
passengers who alight without a booking will not match anything,
and the completer logs a warning rather than crashing main.py's
counting pipeline.
"""

import os
import logging
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

load_dotenv()

# Firebase Realtime Database sentinel for server-side timestamp.
# Mirrors the SERVER_TIMESTAMP pattern used in booking_validator.
# The database substitutes this for the actual server time on write.
SERVER_TIMESTAMP = {".sv": "timestamp"}

logger = logging.getLogger(__name__)


class BookingCompleter:
    """
    Transitions active bookings to 'completed' on alighting events.

    Firebase clients are loaded lazily — the completer can be
    constructed without an active Firebase connection, which
    makes it cheap to instantiate in tests and during dev runs
    where Firebase is unreachable.

    Attributes:
        shuttle_id: Identifier for this shuttle, used to filter
                    bookings to only those belonging to this
                    shuttle. Read from SHUTTLE_ID env var so
                    configuration stays consistent across the
                    counting module.
    """

    def __init__(self, shuttle_id=None):
        """
        Initialize the BookingCompleter.

        Args:
            shuttle_id: Optional override for the shuttle ID.
                        Defaults to the SHUTTLE_ID environment
                        variable or 'shuttle_001' if unset.
        """
        self.shuttle_id = shuttle_id or os.getenv(
            "SHUTTLE_ID", "shuttle_001"
        )
        self._firebase_ready = False

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK on first use.

        Idempotent — safe to call repeatedly; only the first call
        actually initializes. Mirrors the pattern used in
        BookingValidator so the whole counting module shares the
        same Firebase app and credentials.
        """
        if self._firebase_ready:
            return

        if firebase_admin._apps:
            self._firebase_ready = True
            return

        cred_path = os.getenv(
            "FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json"
        )
        database_url = os.getenv("FIREBASE_DATABASE_URL")

        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(
                cred, {"databaseURL": database_url}
            )
            self._firebase_ready = True
            logger.info("Firebase initialized for BookingCompleter")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def find_oldest_active_booking(self, current_stop):
        """
        Find the oldest active booking whose destination matches
        the shuttle's current stop.

        Queries /bookings/ in Firebase, filters for bookings
        belonging to THIS shuttle with status 'active' and
        matching destination_stop, then sorts ascending by
        boarded_at timestamp so the booking that has been
        riding the longest is returned first.

        Returns None when no booking matches. This is expected
        and common: non-app passengers alighting, false-positive
        alighting detections, or all matching bookings already
        completed. Callers should log a warning but not treat
        None as an error condition.

        Resilient to Firebase errors — any exception during the
        query is caught and converted to None so the counting
        pipeline never crashes from a transient Firebase issue.

        Args:
            current_stop: The shuttle's current stop name. Only
                          bookings with destination_stop matching
                          this value are considered.

        Returns:
            The oldest matching booking dict, or None if no
            booking matches or Firebase is unreachable.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return None

        if not all_bookings:
            return None

        # filter by shuttle, status, and destination, then sort
        # by boarded_at ascending so the oldest match is first
        matches = []
        for booking_id, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "active":
                continue
            if booking.get("destination_stop") != current_stop:
                continue
            matches.append(booking)

        if not matches:
            return None

        # sort by boarded_at ascending — missing values treated
        # as 0 so older bookings still sort sensibly even when
        # Firebase server clock has hiccups
        matches.sort(key=lambda b: b.get("boarded_at") or 0)
        return matches[0]

    def mark_as_completed(self, booking):
        """
        Transition an active booking to 'completed' in Firebase.

        Performs an atomic multi-path update to /bookings/{id}
        and /user_bookings/{uid}/{id}, writing the status change
        and completed_at timestamp. Mirrors the multi-path
        update pattern used by BookingValidator.mark_as_active()
        and Cissy's mobile app at booking creation, so the two
        collections stay perfectly in sync.

        Args:
            booking: The booking dict returned by
                     find_oldest_active_booking. Must include
                     booking_id and user_uid.

        Returns:
            True on success, False if Firebase rejects the
            update or if the booking record is missing required
            fields (corrupt data).
        """
        booking_id = booking.get("booking_id")
        user_uid = booking.get("user_uid")

        if not booking_id or not user_uid:
            logger.error(
                f"Cannot complete booking -- missing booking_id or "
                f"user_uid: {booking}"
            )
            return False

        self._ensure_firebase()

        try:
            updates = {
                f"bookings/{booking_id}/status": "completed",
                f"bookings/{booking_id}/completed_at": SERVER_TIMESTAMP,
                f"user_bookings/{user_uid}/{booking_id}/status": "completed",
                f"user_bookings/{user_uid}/{booking_id}/completed_at": SERVER_TIMESTAMP,
            }
            db.reference("/").update(updates)
            logger.info(f"Booking {booking_id} marked as completed")
            return True
        except Exception as e:
            logger.error(
                f"Error marking booking {booking_id} as completed: {e}"
            )
            return False

    def complete_alighting(self, current_stop):
        """
        Process a single alighting event at the shuttle's current stop.

        This is the main public method that main.py calls every time
        the counting logic detects a passenger alighting. It:
          1. Queries Firebase for the oldest active booking whose
             destination matches the current stop
          2. Marks that booking as 'completed' atomically in both
             /bookings/{id} and /user_bookings/{uid}/{id}
          3. Returns a clean boolean result

        For multiple simultaneous alightings, main.py calls this
        method once per alighting. Cascading works naturally because
        each successful call transitions the matched booking out of
        'active' state, so the next call's query returns the next
        oldest one. First to board is first to alight.

        Resilient to the no-match case: non-app passengers alight
        without a booking, and detection occasionally registers
        false-positive alightings. In both cases this method logs
        a clear warning and returns False without disrupting
        main.py's counting pipeline.

        Args:
            current_stop: The shuttle's current stop name. The
                          alighting must match a booking with this
                          destination_stop to be completed.

        Returns:
            True if a booking was successfully marked completed,
            False if no booking matched or the completion failed.
        """
        booking = self.find_oldest_active_booking(current_stop)

        if booking is None:
            logger.warning(
                f"Alighting detected at {current_stop} but no "
                f"active booking matched. May be a non-app passenger "
                f"or a false-positive detection."
            )
            return False

        success = self.mark_as_completed(booking)
        if success:
            logger.info(
                f"Completed booking {booking.get('booking_id')} "
                f"(user: {booking.get('user_uid')}) on alighting at "
                f"{current_stop}"
            )
        return success
