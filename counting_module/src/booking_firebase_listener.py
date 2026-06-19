"""
BookingFirebaseListener component for APCOMS.

Bridges Cissy's mobile app to our SeatPoolManager by listening
to Firebase /bookings for lifecycle events:

  - Booking created (status: reserved)
        -> seat_pool_manager.decrement(reason="book")
  - User cancellation (status: cancelled, reason != no_show)
        -> seat_pool_manager.increment(reason="user_cancel")

Other transitions are intentionally ignored:
  - active (QR scanned)  -- handled at booking time
  - completed (alighted) -- handled by CountingLogic
  - no_show cancellation -- handled by NoShowCanceller

Idempotency:
  Firebase listeners fire on every write to /bookings, including
  writes that don't change the status (e.g. updates to other
  fields). To avoid double-acting on the same lifecycle transition,
  every (booking_id, last_status) pair is persisted to SQLite. The
  listener only acts when the incoming status differs from the
  stored one, then updates the stored status.

This component does NOT itself attach to Firebase -- attaching is
the wiring step's responsibility (Slice 7). The public on_booking_event
method is the callback Firebase will invoke. Keeping the attachment
out of this class lets the whole module be tested in pure isolation
without mocking the Firebase library.
"""

import os
import sqlite3
import logging
import threading
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BookingFirebaseListener:
    """
    Listens to /bookings events and mutates the seat pool.

    Attributes:
        shuttle_id:         Identifies which shuttle's bookings this
                            listener cares about. Events for other
                            shuttles are ignored.
        db_path:            Path to the SQLite database where the
                            processed_bookings idempotency table
                            lives.
        seat_pool_manager:  SeatPoolManager instance receiving
                            increment/decrement calls. Required --
                            without it the listener has no purpose.
    """

    NO_SHOW_REASON = "no_show_at_pickup"
    STALE_REASON = "stale_from_previous_day"

    def __init__(self, shuttle_id=None, db_path=None, seat_pool_manager=None):
        if seat_pool_manager is None:
            raise ValueError(
                "BookingFirebaseListener requires a seat_pool_manager"
            )

        self.shuttle_id = shuttle_id or os.getenv(
            "SHUTTLE_ID", "shuttle_001"
        )
        self.db_path = db_path or "local_database/apcoms.db"
        self.seat_pool_manager = seat_pool_manager
        # Serialise on_booking_event so that the streaming listener and
        # the polling fallback can never both decide to act on the same
        # booking event in the same race window. Without this, both
        # threads can read last_status=None, both decrement, and the
        # seat pool double-acts. The SQLite idempotency table is the
        # source of truth but the read+write needs to be atomic, which
        # the lock guarantees.
        self._event_lock = threading.Lock()

    def on_booking_event(self, booking_id, booking_data):
        """
        Handle a single booking lifecycle event from Firebase.

        This is the public callback the wiring layer will pass to
        Firebase as the listener. It is safe to call repeatedly
        with the same event -- the processed_bookings table
        guarantees idempotency.

        Args:
            booking_id:   The Firebase key for this booking.
            booking_data: The booking dict from Firebase. Required
                          fields: shuttle_key, status. Optional but
                          recognised: cancel_reason.
        """
        if not isinstance(booking_data, dict):
            return

        shuttle_key = booking_data.get("shuttle_key")
        status = booking_data.get("status")

        if shuttle_key != self.shuttle_id:
            return
        if not status:
            return

        # Hold the lock across the read-check-act-write sequence so
        # the streaming listener thread and the poller thread can never
        # both squeeze through the idempotency check before either has
        # marked the booking as processed.
        with self._event_lock:
            last_status = self._get_last_processed_status(booking_id)

            # already at this status -- nothing to do
            if last_status == status:
                return

            if status == "reserved":
                self._handle_reserved(booking_id, last_status)
            elif status == "cancelled":
                self._handle_cancelled(booking_id, booking_data, last_status)
            # active/completed/anything else: ignore, but mark status
            # so future events for this booking know the history.
            self._mark_processed(booking_id, status)

    def _handle_reserved(self, booking_id, last_status):
        """
        First-time reserved event -- hold a seat.

        If we've already processed this booking as reserved (which
        the caller's last_status == status check above already
        filters), do nothing. Defensive only.
        """
        if last_status == "reserved":
            return
        try:
            self.seat_pool_manager.decrement(reason="book")
            logger.info(
                f"Booking {booking_id} reserved -- seat held"
            )
        except Exception as e:
            logger.error(
                f"Failed to hold seat for {booking_id}: {e}"
            )

    def _handle_cancelled(self, booking_id, booking_data, last_status):
        """
        Cancellation event -- release a seat if and only if it was
        a user cancellation we previously processed as reserved.

        Skips:
          - cancel_reason == 'no_show_at_pickup' (NoShowCanceller
            already released the seat directly)
          - cancel_reason == 'stale_from_previous_day'
            (ServiceDayManager already reset available_seats to
            total_capacity at the service-day boundary, before
            flipping stale bookings to cancelled. Incrementing here
            would push the seat pool above capacity.)
          - last_status != 'reserved' (never saw the original hold,
            no seat to release)
        """
        cancel_reason = booking_data.get("cancel_reason", "")

        # Reasons where the cancellation's writer already handled
        # the seat math themselves. The listener must NOT also
        # increment for these or available_seats drifts high.
        externally_handled = (self.NO_SHOW_REASON, self.STALE_REASON)
        if cancel_reason in externally_handled:
            logger.info(
                f"Booking {booking_id} cancelled ({cancel_reason}) -- "
                f"seat already released, skipping"
            )
            return

        if last_status != "reserved":
            logger.info(
                f"Booking {booking_id} cancelled but never processed "
                f"as reserved -- skipping seat release"
            )
            return

        try:
            self.seat_pool_manager.increment(reason="user_cancel")
            logger.info(
                f"Booking {booking_id} cancelled by user -- seat released"
            )
        except Exception as e:
            logger.error(
                f"Failed to release seat for {booking_id}: {e}"
            )

    def _init_processed_table(self):
        """
        Create the processed_bookings table if it doesn't exist.

        Idempotent helper called by every read/write path so the
        table is always present without requiring a separate
        initialization step.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_bookings (
                    booking_id TEXT PRIMARY KEY,
                    last_status TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to init processed_bookings table: {e}")

    def _mark_processed(self, booking_id, status):
        """
        Record the latest processed status for a booking.

        Used for idempotency -- the next event for this booking
        compares against this stored value to decide whether to act.
        """
        self._init_processed_table()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO processed_bookings
                (booking_id, last_status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (booking_id, status))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(
                f"Failed to mark processed {booking_id}: {e}"
            )

    def _get_last_processed_status(self, booking_id):
        """
        Return the last status this listener processed for a booking,
        or None if we've never seen it.
        """
        self._init_processed_table()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_status FROM processed_bookings WHERE booking_id = ?",
                (booking_id,),
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(
                f"Failed to read processed status for {booking_id}: {e}"
            )
            return None
