"""
No-Show Canceller Component for APCOMS

Auto-cancels reserved bookings whose passengers failed to scan
their QR at the pickup stop before the shuttle departed. Called
by ScannerOrchestrator's advance_and_sync flow just before the
shuttle is marked as having left a stop.

The cancellation closes the booking lifecycle for no-shows so
the seat is freed in Firebase and the booker can rebook for a
later trip. Without this component, no-show reserved bookings
would linger forever, occupying seats that are physically empty.

This is the third terminal state in the booking lifecycle:
  reserved -> active     (QR scan, Phase 3)
  reserved -> completed  (alighting, Phase 6)
  reserved -> cancelled  (no-show, Phase 7)

Robustness through SQLite queueing:
  When a Firebase write fails (network glitch, permission issue),
  the cancellation intent is persisted to a local pending_cancellations
  table in SQLite. On every subsequent call, the queue is drained
  first so eventual consistency is guaranteed even through repeated
  network outages. Mirrors the queue-and-retry pattern already used
  by firebase_sync for occupancy updates.
"""

import os
import sqlite3
import logging
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

load_dotenv()

# Firebase Realtime Database sentinel for server-side timestamp.
# Mirrors the SERVER_TIMESTAMP pattern used in booking_validator
# and booking_completer. The database substitutes this for the
# actual server time on write so we never trust client clocks.
SERVER_TIMESTAMP = {".sv": "timestamp"}

logger = logging.getLogger(__name__)


class NoShowCanceller:
    """
    Cancels no-show reserved bookings when the shuttle leaves a stop.

    Firebase clients are loaded lazily — the canceller can be
    constructed and tested without an active Firebase connection.

    Attributes:
        shuttle_id: Identifier for this shuttle, used to filter
                    bookings so only THIS shuttle's reservations
                    are considered. Read from SHUTTLE_ID env var.
        db_path:    Path to the SQLite database used for persisting
                    the pending_cancellations queue. Tests override
                    this to avoid polluting production state.
    """

    def __init__(self, shuttle_id=None, db_path=None, seat_pool_manager=None):
        """
        Initialize the NoShowCanceller.

        Args:
            shuttle_id: Optional override for the shuttle ID.
                        Defaults to the SHUTTLE_ID environment
                        variable or 'shuttle_001' if unset.
            db_path:    Optional override for the SQLite database
                        path. Defaults to 'local_database/apcoms.db'.
            seat_pool_manager: Optional SeatPoolManager instance. When
                               present, every successful cancellation
                               releases the held seat back to the pool.
        """
        self.shuttle_id = shuttle_id or os.getenv(
            "SHUTTLE_ID", "shuttle_001"
        )
        self.db_path = db_path or "local_database/apcoms.db"
        self.seat_pool_manager = seat_pool_manager
        self._firebase_ready = False

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK on first use.

        Idempotent — safe to call repeatedly; only the first call
        actually initializes. Mirrors the pattern used in
        BookingValidator and BookingCompleter so the whole counting
        module shares the same Firebase app and credentials.
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
            logger.info("Firebase initialized for NoShowCanceller")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def find_no_show_bookings(self, stop):
        """
        Find all reserved bookings whose pickup is the given stop.

        Queries /bookings/ in Firebase, filters for bookings
        belonging to THIS shuttle with status 'reserved' and
        matching pickup_stop. Returns ALL matches (not just the
        oldest) because the shuttle is leaving this stop — every
        reserved passenger at this pickup has missed their ride
        and needs cancelling.

        Returns an empty list on any of these conditions:
          - No bookings exist in Firebase yet
          - No bookings match the filter criteria
          - Firebase is unreachable

        The empty-list-on-failure behaviour means a network glitch
        causes the cancellation step to be silently skipped this
        cycle. The booking remains 'reserved' until either the
        next advance cycle picks it up or it's manually cleaned.

        Args:
            stop: The shuttle stop name. Only reserved bookings
                  with pickup_stop matching this value are returned.

        Returns:
            A list of matching booking dicts. Empty if no matches
            or Firebase is unreachable.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return []

        if not all_bookings:
            return []

        matches = []
        for booking_id, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "reserved":
                continue
            if booking.get("pickup_stop") != stop:
                continue
            matches.append(booking)

        return matches

    def cancel_one(self, booking):
        """
        Cancel a single no-show booking in Firebase.

        Performs an atomic multi-path update to /bookings/{id}
        and /user_bookings/{uid}/{id}, writing the status change,
        cancel_reason, and cancelled_at timestamp. Mirrors the
        multi-path pattern used by BookingCompleter and
        BookingValidator so the two collections stay in sync.

        Called once per no-show booking. The caller
        (cancel_no_shows) iterates the list of found no-shows
        and invokes cancel_one for each — independent calls means
        partial failures are handled naturally: some can succeed
        while others queue for retry.

        Args:
            booking: The booking dict from find_no_show_bookings.
                     Must include booking_id and user_uid.

        Returns:
            True on successful Firebase write, False if the
            update failed or if the booking record is missing
            required fields. Callers should queue failed
            cancellations locally for retry.
        """
        booking_id = booking.get("booking_id")
        user_uid = booking.get("user_uid")

        if not booking_id or not user_uid:
            logger.error(
                f"Cannot cancel booking -- missing booking_id or "
                f"user_uid: {booking}"
            )
            return False

        self._ensure_firebase()

        try:
            updates = {
                f"bookings/{booking_id}/status": "cancelled",
                f"bookings/{booking_id}/cancel_reason": "no_show_at_pickup",
                f"bookings/{booking_id}/cancelled_at": SERVER_TIMESTAMP,
                f"user_bookings/{user_uid}/{booking_id}/status": "cancelled",
                f"user_bookings/{user_uid}/{booking_id}/cancel_reason": "no_show_at_pickup",
                f"user_bookings/{user_uid}/{booking_id}/cancelled_at": SERVER_TIMESTAMP,
            }
            db.reference("/").update(updates)
            logger.info(
                f"Booking {booking_id} cancelled (no_show_at_pickup)"
            )
        except Exception as e:
            logger.error(
                f"Error cancelling booking {booking_id}: {e}"
            )
            return False

        # Firebase accepted the cancellation -- release the held seat
        # back to the pool. Seat-release failures are logged but don't
        # undo the cancellation; next reconciliation cycle will catch
        # any drift.
        if self.seat_pool_manager is not None:
            try:
                self.seat_pool_manager.increment(reason="no_show")
            except Exception as e:
                logger.error(
                    f"Seat release failed after cancelling {booking_id}: {e}"
                )

        return True

    def _init_queue_table(self):
        """
        Create the pending_cancellations table if it doesn't exist.

        Internal helper called by queue write/read methods so the
        table is always present without requiring a separate
        initialization step. Idempotent — repeated calls are a
        no-op once the table exists.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_cancellations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    booking_id TEXT NOT NULL,
                    user_uid TEXT NOT NULL,
                    cancel_reason TEXT NOT NULL,
                    queued_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error initializing queue table: {e}")

    def _queue_cancellation(self, booking):
        """
        Persist a failed cancellation to SQLite for later retry.

        Called when cancel_one's Firebase write fails. The
        cancellation intent survives main.py and orchestrator
        restarts so even prolonged outages don't lose data — the
        next call to cancel_no_shows will drain the queue first
        and retry against Firebase.

        Args:
            booking: The booking dict that failed to cancel.
                     Only booking_id and user_uid are persisted
                     since cancel_reason is always 'no_show_at_pickup'
                     for this component.
        """
        self._init_queue_table()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_cancellations
                (booking_id, user_uid, cancel_reason)
                VALUES (?, ?, ?)
            """, (
                booking.get("booking_id"),
                booking.get("user_uid"),
                "no_show_at_pickup",
            ))
            conn.commit()
            conn.close()
            logger.info(
                f"Queued cancellation for booking "
                f"{booking.get('booking_id')} (Firebase retry)"
            )
        except sqlite3.Error as e:
            logger.error(f"Error queuing cancellation: {e}")

    def _drain_queue(self):
        """
        Attempt to apply all pending cancellations to Firebase.

        Reads every row from pending_cancellations, calls
        cancel_one for each (using a minimal booking dict
        containing only the persisted fields), and deletes
        each row on successful Firebase write. Rows whose
        Firebase write still fails remain in the queue for
        the next drain attempt.

        Called at the start of every cancel_no_shows() invocation
        so the queue is always drained on the next opportunity.
        Eventual consistency: even repeated outages don't lose
        data — the queue just keeps growing until Firebase is
        reachable again.

        Returns:
            The number of cancellations successfully drained
            from the queue this call.
        """
        self._init_queue_table()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, booking_id, user_uid, cancel_reason "
                "FROM pending_cancellations"
            )
            rows = cursor.fetchall()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error reading queue: {e}")
            return 0

        drained_count = 0
        for row in rows:
            queue_id, booking_id, user_uid, _ = row
            booking = {
                "booking_id": booking_id,
                "user_uid": user_uid,
            }
            success = self.cancel_one(booking)
            if success:
                # remove this row from the queue
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM pending_cancellations WHERE id = ?",
                        (queue_id,),
                    )
                    conn.commit()
                    conn.close()
                    drained_count += 1
                except sqlite3.Error as e:
                    logger.error(
                        f"Error removing queue entry {queue_id}: {e}"
                    )

        if drained_count > 0:
            logger.info(
                f"Drained {drained_count} pending cancellation(s) "
                f"from queue"
            )
        return drained_count

    def cancel_no_shows(self, stop):
        """
        Cancel all no-show reserved bookings at the given stop.

        This is the public method the orchestrator calls when
        the shuttle is leaving a stop. It performs three phases:

          1. Drain the pending_cancellations queue first so any
             retries from previous Firebase outages get applied
             on every fresh call.
          2. Query Firebase for reserved bookings with pickup_stop
             matching this stop and shuttle_key matching this
             shuttle.
          3. For each match: attempt cancel_one. On failure,
             queue the cancellation locally so it'll be retried
             on the next call.

        The queue-first ordering guarantees eventual consistency
        even through repeated network outages — failed
        cancellations don't get lost, they just get tried again
        next cycle.

        Args:
            stop: The shuttle stop being left. All reserved
                  bookings with this as their pickup_stop are
                  candidates for no-show cancellation.

        Returns:
            The total number of cancellations successfully
            applied to Firebase this call (drained queue +
            new no-shows that succeeded). Bookings that failed
            and were queued do NOT count toward this total.
        """
        # phase 1: drain queue first so retries get attempted
        drained = self._drain_queue()

        # phase 2: find fresh no-shows at this stop
        no_shows = self.find_no_show_bookings(stop)

        if not no_shows:
            return drained

        # phase 3: try to cancel each, queue failures for retry
        fresh_cancellations = 0
        for booking in no_shows:
            success = self.cancel_one(booking)
            if success:
                fresh_cancellations += 1
            else:
                self._queue_cancellation(booking)

        total = drained + fresh_cancellations
        if total > 0:
            logger.info(
                f"Cancelled {total} no-show booking(s) at {stop}"
            )
        return total
