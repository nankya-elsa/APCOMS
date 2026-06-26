"""
Tests for the BookingFirebaseListener component.

The listener bridges Cissy's mobile app to our seat pool by
listening to Firebase /bookings for lifecycle events:

  - Booking created (status: reserved)
        -> seat_pool_manager.decrement(reason="book")
  - User cancellation (status: cancelled, reason != no_show)
        -> seat_pool_manager.increment(reason="user_cancel")

Other transitions are ignored:
  - active (QR scanned)  -> already handled at booking time
  - completed (alighted) -> handled by CountingLogic
  - no_show cancellation -> already handled by NoShowCanceller

Idempotency is enforced by recording each booking's last
processed status in SQLite. Repeat listener fires for the
same transition are skipped so we never double-mutate the pool.

Firebase listening, SQLite, and seat_pool_manager are all
mocked so the component is verified in pure isolation.
"""

import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from booking_firebase_listener import BookingFirebaseListener

TEST_DB = "local_database/test_apcoms.db"


def _reset_test_db():
    """Drop the processed_bookings table for a clean slate."""
    os.makedirs("local_database", exist_ok=True)
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS processed_bookings")
    conn.commit()
    conn.close()


class TestListenerInitialization:

    def setup_method(self):
        _reset_test_db()

    def test_listener_initializes_with_required_args(self):
        """
        BookingFirebaseListener should construct cleanly with a
        seat_pool_manager so it can act on booking events.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_test",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        assert listener.shuttle_id == "shuttle_test"
        assert listener.db_path == TEST_DB
        assert listener.seat_pool_manager is mock_pool

    def test_shuttle_id_defaults_to_env(self):
        """
        Following the pattern used by NoShowCanceller and
        firebase_sync — shuttle_id reads from SHUTTLE_ID env var
        when not explicitly provided so the whole counting module
        shares one identifier.
        """
        with patch.dict(os.environ, {"SHUTTLE_ID": "shuttle_xyz"}):
            listener = BookingFirebaseListener(
                db_path=TEST_DB, seat_pool_manager=MagicMock()
            )
            assert listener.shuttle_id == "shuttle_xyz"

    def test_seat_pool_manager_is_required(self):
        """
        seat_pool_manager is the whole point of this listener.
        Without it the listener has no action to take on events
        so the contract requires it at construction.
        """
        with pytest.raises(ValueError):
            BookingFirebaseListener(
                shuttle_id="shuttle_test",
                db_path=TEST_DB,
                seat_pool_manager=None,
            )


class TestProcessedStateTracking:

    def setup_method(self):
        _reset_test_db()

    def test_init_processed_table_creates_schema(self):
        """
        The processed_bookings table must be created on first use
        with columns booking_id (primary key) and last_status.
        Idempotent — repeated calls are a no-op.
        """
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_test",
            db_path=TEST_DB,
            seat_pool_manager=MagicMock(),
        )
        listener._init_processed_table()

        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_bookings'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_mark_processed_records_booking_status(self):
        """
        After marking a booking as processed with a given status,
        _get_last_processed_status returns that status. This is
        how the listener avoids double-acting on repeat events.
        """
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_test",
            db_path=TEST_DB,
            seat_pool_manager=MagicMock(),
        )
        listener._mark_processed("booking_abc", "reserved")

        assert listener._get_last_processed_status("booking_abc") == "reserved"

    def test_get_last_processed_returns_none_for_unseen_booking(self):
        """
        A booking we've never processed returns None. The listener
        uses this to detect first-time events and decide whether
        to act on the lifecycle transition.
        """
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_test",
            db_path=TEST_DB,
            seat_pool_manager=MagicMock(),
        )
        assert listener._get_last_processed_status("never_seen") is None

    def test_mark_processed_updates_existing_status(self):
        """
        A booking that goes reserved -> cancelled must have its
        recorded status updated on the second event. Otherwise
        the listener would think the booking was still reserved
        and could mis-handle a future event for the same id.
        """
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_test",
            db_path=TEST_DB,
            seat_pool_manager=MagicMock(),
        )
        listener._mark_processed("booking_abc", "reserved")
        listener._mark_processed("booking_abc", "cancelled")

        assert listener._get_last_processed_status("booking_abc") == "cancelled"


class TestNewBookingEvents:

    def setup_method(self):
        _reset_test_db()

    def test_new_reserved_booking_decrements_seat(self):
        """
        A first-time reserved booking for our shuttle is the
        canonical book event — call decrement with reason='book'
        and mark the booking as processed so we don't double-act.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "user_uid": "user_1",
            "status": "reserved",
            "pickup_stop": "CONAS",
        })

        mock_pool.decrement.assert_called_once_with(reason="book")
        assert listener._get_last_processed_status("booking_abc") == "reserved"

    def test_reserved_booking_for_other_shuttle_is_ignored(self):
        """
        Multi-shuttle deployments: Firebase has bookings for
        every shuttle, but each listener only reacts to its own.
        Reserved booking for shuttle_002 must not trigger our
        seat pool when we are shuttle_001.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_002",
            "status": "reserved",
        })

        mock_pool.decrement.assert_not_called()

    def test_already_processed_reserved_booking_does_not_double_decrement(self):
        """
        Firebase listeners fire on every write. If the booking
        was already processed as reserved (e.g. earlier in this
        run), a repeat event must NOT decrement the pool again.
        Idempotency is enforced by the processed_bookings table.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "reserved",
        })

        mock_pool.decrement.assert_not_called()

    def test_booking_missing_shuttle_key_is_ignored(self):
        """
        A booking record without shuttle_key is corrupt data;
        the listener cannot determine if it belongs to this
        shuttle so it must be safely ignored, not crash.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "status": "reserved",
        })

        mock_pool.decrement.assert_not_called()


class TestUserCancellationEvents:

    def setup_method(self):
        _reset_test_db()

    def test_user_cancellation_increments_seat(self):
        """
        A cancellation with a non-no-show reason is a user
        cancellation from Cissy's app. Release the held seat
        via increment(reason='user_cancel'). The booking must
        have been previously processed as reserved.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "Cancelled by user",
        })

        mock_pool.increment.assert_called_once_with(reason="user_cancel")
        assert listener._get_last_processed_status("booking_abc") == "cancelled"

    def test_no_show_cancellation_is_skipped(self):
        """
        NoShowCanceller already released the seat when it set
        cancel_reason='no_show_at_pickup'. The listener must
        recognise that reason and skip — otherwise the seat
        would be released twice and available_seats would drift
        permanently high.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "no_show_at_pickup",
        })

        mock_pool.increment.assert_not_called()

    def test_stale_from_previous_day_cancellation_is_skipped(self):
        """
        ServiceDayManager.perform_reset() resets available_seats to
        total_capacity at the service-day boundary BEFORE flipping
        stale reserved/active bookings to cancelled with reason
        'stale_from_previous_day'. The seat math is already correct
        by the time those Firebase writes propagate; if the listener
        also incremented, available_seats would drift above capacity.
        The listener must recognise this reason and skip — same
        pattern as no_show_at_pickup, different owner of the math.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_xyz", "reserved")

        listener.on_booking_event("booking_xyz", {
            "booking_id": "booking_xyz",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "stale_from_previous_day",
        })

        mock_pool.increment.assert_not_called()

    def test_admin_reset_cancellation_is_skipped(self):
        """
        Admin-triggered resets already clear the seat pool to capacity
        and cancel the live bookings. The listener must not release
        seats a second time for those cancellations.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_xyz", "reserved")

        listener.on_booking_event("booking_xyz", {
            "booking_id": "booking_xyz",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "reset_by_admin",
        })

        mock_pool.increment.assert_not_called()

    def test_cancellation_without_prior_reserved_is_skipped(self):
        """
        If the booking was never seen as reserved (e.g. the
        system was restarting when the booking was created),
        we have no record of the seat being held. A safe default
        is to skip rather than spuriously increment — the next
        startup reconciliation will catch any drift.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "Cancelled by user",
        })

        mock_pool.increment.assert_not_called()

    def test_cancellation_for_other_shuttle_is_ignored(self):
        """
        Same shuttle-scoping as reserved events: a cancellation
        on shuttle_002 must not touch shuttle_001's seat pool.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_002",
            "status": "cancelled",
            "cancel_reason": "Cancelled by user",
        })

        mock_pool.increment.assert_not_called()

    def test_already_processed_cancel_does_not_double_increment(self):
        """
        Repeat firings for an already-cancelled booking must NOT
        increment again. Same idempotency principle as the
        reserved-event path.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")
        listener._mark_processed("booking_abc", "cancelled")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "cancelled",
            "cancel_reason": "Cancelled by user",
        })

        mock_pool.increment.assert_not_called()


class TestOtherStatuses:

    def setup_method(self):
        _reset_test_db()

    def test_active_status_does_not_touch_seat_pool(self):
        """
        'active' is fired by BookingValidator when the passenger
        scans their QR. The seat was already held at booking
        time so no pool mutation is needed here — boarding is
        a count event, not a seat event.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "active",
        })

        mock_pool.increment.assert_not_called()
        mock_pool.decrement.assert_not_called()

    def test_completed_status_does_not_touch_seat_pool(self):
        """
        'completed' fires when the passenger alights. CountingLogic
        already released the seat through SeatPoolManager when it
        detected the alighting movement. The listener seeing the
        booking flip to completed is downstream of that release,
        so it must not double-act.
        """
        mock_pool = MagicMock()
        listener = BookingFirebaseListener(
            shuttle_id="shuttle_001",
            db_path=TEST_DB,
            seat_pool_manager=mock_pool,
        )
        listener._mark_processed("booking_abc", "reserved")

        listener.on_booking_event("booking_abc", {
            "booking_id": "booking_abc",
            "shuttle_key": "shuttle_001",
            "status": "completed",
        })

        mock_pool.increment.assert_not_called()
        mock_pool.decrement.assert_not_called()
