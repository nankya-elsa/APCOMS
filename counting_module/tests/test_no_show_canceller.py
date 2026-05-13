"""
Tests for the NoShowCanceller component.

The NoShowCanceller is responsible for closing the booking
lifecycle for passengers who reserved a seat but never showed
up to scan their QR at the pickup stop. When the shuttle leaves
a stop, any reserved bookings with that stop as pickup get
auto-cancelled with reason 'no_show_at_pickup'.

This is the third lifecycle terminal state:
  reserved -> active     (QR scan, Phase 3)
  reserved -> completed  (alighting, Phase 6)
  reserved -> cancelled  (no-show, Phase 7) <- this component

To survive Firebase outages, cancellations that fail their
write are queued locally in SQLite and drained on the next
successful call. This keeps Firebase eventually consistent
with the shuttle's ground truth even through network blips,
mirroring the queue-and-retry pattern already used in
firebase_sync for occupancy updates.

Firebase, sqlite3, and time are mocked throughout these tests
so the component can be verified in pure isolation.
"""

import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from no_show_canceller import NoShowCanceller

TEST_DB = "local_database/test_apcoms.db"


class TestNoShowCancellerInitialization:
    """Tests covering NoShowCanceller construction."""

    def test_canceller_initializes_with_defaults(self):
        """
        NoShowCanceller should instantiate without arguments and
        be ready to use. Firebase initialization is lazy so the
        class can be constructed in tests without real credentials.
        """
        canceller = NoShowCanceller()
        assert canceller is not None
        assert hasattr(canceller, "shuttle_id")
        assert hasattr(canceller, "db_path")

    def test_canceller_uses_shuttle_id_from_env(self):
        """
        Mirrors the pattern used by firebase_sync, data_logger,
        scanner_orchestrator, and booking_completer. Reading from
        SHUTTLE_ID env var keeps shuttle identification consistent
        across the whole counting module.
        """
        with patch.dict(os.environ, {"SHUTTLE_ID": "shuttle_test_42"}):
            canceller = NoShowCanceller()
            assert canceller.shuttle_id == "shuttle_test_42"

    def test_canceller_accepts_explicit_overrides(self):
        """
        Tests need to point the canceller at custom db paths and
        shuttle IDs to avoid polluting production state and to
        verify shuttle-filtering logic. Both should be overridable
        at construction time.
        """
        canceller = NoShowCanceller(
            shuttle_id="custom_shuttle",
            db_path=TEST_DB,
        )
        assert canceller.shuttle_id == "custom_shuttle"
        assert canceller.db_path == TEST_DB


class TestFindNoShowBookings:
    """Tests covering the Firebase query that finds no-show bookings."""

    @patch("no_show_canceller.db")
    def test_returns_all_reserved_bookings_at_stop(self, mock_db):
        """
        When multiple reserved bookings exist for this shuttle with
        the same pickup stop, they should ALL be returned for
        cancellation. Unlike booking_completer which picks the
        oldest one, here we want every no-show — the shuttle is
        leaving the stop, so every reserved booking at this pickup
        has missed their ride.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_a": {
                "booking_id": "booking_a",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "booking_b": {
                "booking_id": "booking_b",
                "user_uid": "user2",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "booking_other_stop": {
                "booking_id": "booking_other_stop",
                "user_uid": "user3",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "Main Library",
            },
            "booking_already_active": {
                "booking_id": "booking_already_active",
                "user_uid": "user4",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        canceller = NoShowCanceller(shuttle_id="shuttle_001")
        result = canceller.find_no_show_bookings(stop="CONAS")

        assert len(result) == 2
        booking_ids = {b["booking_id"] for b in result}
        assert booking_ids == {"booking_a", "booking_b"}

    @patch("no_show_canceller.db")
    def test_returns_empty_list_when_no_matches(self, mock_db):
        """
        When no bookings match (everyone boarded successfully, or
        nobody booked for this stop), find_no_show_bookings returns
        an empty list. The shuttle leaves cleanly with no cancellation
        work to do.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_other_stop": {
                "booking_id": "booking_other_stop",
                "status": "reserved",
                "pickup_stop": "Main Library",
                "shuttle_key": "shuttle_001",
            },
        }
        mock_db.reference.return_value = mock_ref

        canceller = NoShowCanceller(shuttle_id="shuttle_001")
        result = canceller.find_no_show_bookings(stop="CONAS")

        assert result == []

    @patch("no_show_canceller.db")
    def test_returns_empty_when_firebase_empty(self, mock_db):
        """
        On a fresh deployment with no bookings yet, Firebase returns
        None for /bookings. find_no_show_bookings must handle this
        cleanly and return an empty list rather than crashing.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        canceller = NoShowCanceller(shuttle_id="shuttle_001")
        result = canceller.find_no_show_bookings(stop="CONAS")

        assert result == []

    @patch("no_show_canceller.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Reserved bookings for OTHER shuttles at the same stop must
        be ignored. We must not cancel another shuttle's bookings
        just because they share a pickup point. We verify this by
        including a perfectly-matching booking for a different
        shuttle and confirming it isn't returned.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "other_shuttle_booking": {
                "booking_id": "other_shuttle_booking",
                "shuttle_key": "shuttle_002",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        canceller = NoShowCanceller(shuttle_id="shuttle_001")
        result = canceller.find_no_show_bookings(stop="CONAS")

        assert result == []

    @patch("no_show_canceller.db")
    def test_returns_empty_on_firebase_error(self, mock_db):
        """
        If Firebase raises during the query (network glitch,
        permission issue), find_no_show_bookings catches it and
        returns an empty list. The shuttle keeps moving and the
        cancellation simply doesn't happen this cycle — the
        bookings remain 'reserved' until next attempt, and the
        queue-drain mechanism gives a future opportunity to clean
        them up if the same passengers don't book again.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_ref

        canceller = NoShowCanceller(shuttle_id="shuttle_001")
        result = canceller.find_no_show_bookings(stop="CONAS")

        assert result == []


class TestCancelOne:
    """
    Tests covering the Firebase write that cancels a single
    no-show booking.
    """

    @patch("no_show_canceller.db")
    def test_cancel_one_updates_both_paths(self, mock_db):
        """
        Cancellation must update BOTH /bookings/{id} and
        /user_bookings/{uid}/{id} atomically so the mobile app's
        per-user view stays consistent with the global bookings
        collection. We use a multi-path update so both writes
        succeed or both fail together.
        """
        mock_root_ref = MagicMock()
        mock_db.reference.return_value = mock_root_ref

        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
            "status": "reserved",
            "pickup_stop": "CONAS",
        }

        canceller = NoShowCanceller()
        result = canceller.cancel_one(booking)

        assert result is True
        mock_db.reference.assert_called_with("/")
        mock_root_ref.update.assert_called_once()
        payload = mock_root_ref.update.call_args[0][0]
        assert payload["bookings/abc123/status"] == "cancelled"
        assert payload["bookings/abc123/cancel_reason"] == "no_show_at_pickup"
        assert "bookings/abc123/cancelled_at" in payload
        assert payload["user_bookings/user1/abc123/status"] == "cancelled"
        assert payload["user_bookings/user1/abc123/cancel_reason"] == "no_show_at_pickup"
        assert "user_bookings/user1/abc123/cancelled_at" in payload

    @patch("no_show_canceller.db")
    def test_cancel_one_returns_false_on_firebase_error(self, mock_db):
        """
        If Firebase rejects the update, cancel_one should return
        False rather than crashing. The caller will queue this
        cancellation locally so it gets retried later — eventual
        consistency, never lost data.
        """
        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_root_ref

        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
            "status": "reserved",
        }

        canceller = NoShowCanceller()
        result = canceller.cancel_one(booking)

        assert result is False

    @patch("no_show_canceller.db")
    def test_cancel_one_handles_missing_user_uid(self, mock_db):
        """
        A booking record without user_uid is corrupt — we must
        not write to /user_bookings/None/... and create garbage
        paths in Firebase. The method rejects cleanly with False
        so the caller can flag the data quality issue.
        """
        booking = {
            "booking_id": "abc123",
            "status": "reserved",
        }

        canceller = NoShowCanceller()
        result = canceller.cancel_one(booking)

        assert result is False

    @patch("no_show_canceller.db")
    def test_cancel_one_handles_missing_booking_id(self, mock_db):
        """
        Same defensive principle for booking_id — a missing one
        means the booking record is corrupt. Reject cleanly
        rather than writing to /bookings/None/.
        """
        booking = {
            "user_uid": "user1",
            "status": "reserved",
        }

        canceller = NoShowCanceller()
        result = canceller.cancel_one(booking)

        assert result is False


class TestQueueAndDrain:
    """
    Tests covering the SQLite queue used to retry failed
    cancellations, ensuring eventual consistency with Firebase
    through repeated network outages.
    """

    def setup_method(self):
        """
        Reset the test database before each test so queued
        cancellations don't leak between tests. Uses the same
        TEST_DB path the other components use.
        """
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS pending_cancellations")
        conn.commit()
        conn.close()

    def test_queue_cancellation_persists_to_sqlite(self):
        """
        When cancel_one fails, the cancellation should be written
        to the pending_cancellations table in SQLite so a future
        call can drain and retry. We verify the row appears with
        the right fields.
        """
        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
        }

        canceller = NoShowCanceller(db_path=TEST_DB)
        canceller._queue_cancellation(booking)

        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT booking_id, user_uid, cancel_reason FROM pending_cancellations")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0] == ("abc123", "user1", "no_show_at_pickup")

    def test_queue_cancellation_appends_multiple(self):
        """
        Multiple failures should each get their own row in the
        queue. We don't deduplicate at queue time — the drain
        step's Firebase write will be idempotent (marking
        already-cancelled as cancelled is a no-op semantically).
        """
        canceller = NoShowCanceller(db_path=TEST_DB)
        canceller._queue_cancellation({
            "booking_id": "abc",
            "user_uid": "u1",
        })
        canceller._queue_cancellation({
            "booking_id": "def",
            "user_uid": "u2",
        })

        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_cancellations")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2

    @patch("no_show_canceller.db")
    def test_drain_queue_cancels_each_then_removes(self, mock_db):
        """
        On successful Firebase write, the queued cancellation
        should be removed from SQLite so it doesn't get retried
        forever. We seed the queue with 2 entries, mock Firebase
        to succeed, and confirm both entries are gone after drain.
        """
        # seed the queue with 2 pending cancellations
        canceller = NoShowCanceller(db_path=TEST_DB)
        canceller._queue_cancellation({
            "booking_id": "abc",
            "user_uid": "u1",
        })
        canceller._queue_cancellation({
            "booking_id": "def",
            "user_uid": "u2",
        })

        mock_root_ref = MagicMock()
        mock_db.reference.return_value = mock_root_ref

        drained = canceller._drain_queue()

        # both rows should now be gone from SQLite
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_cancellations")
        remaining = cursor.fetchone()[0]
        conn.close()

        assert drained == 2
        assert remaining == 0
        assert mock_root_ref.update.call_count == 2

    @patch("no_show_canceller.db")
    def test_drain_queue_keeps_entries_that_fail_again(self, mock_db):
        """
        If Firebase is still down during drain, the entries must
        REMAIN in the queue so the next drain attempt can retry.
        We verify by mocking Firebase to fail and confirming the
        row count is unchanged after drain.
        """
        canceller = NoShowCanceller(db_path=TEST_DB)
        canceller._queue_cancellation({
            "booking_id": "abc",
            "user_uid": "u1",
        })

        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Still offline")
        mock_db.reference.return_value = mock_root_ref

        drained = canceller._drain_queue()

        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_cancellations")
        remaining = cursor.fetchone()[0]
        conn.close()

        assert drained == 0
        assert remaining == 1


class TestCancelNoShows:
    """
    Tests covering the public cancel_no_shows() method that
    ties query, cancel, and queue-drain together.
    """

    def setup_method(self):
        """Reset queue table before each test."""
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS pending_cancellations")
        conn.commit()
        conn.close()

    @patch("no_show_canceller.db")
    def test_cancel_no_shows_drains_then_cancels_new(self, mock_db):
        """
        cancel_no_shows should ALWAYS drain the queue first
        before processing new no-shows for this stop. This
        guarantees that retries from previous outages get
        attempted on every fresh call, not just when there
        happen to be new no-shows at the current stop.
        """
        # seed the queue with 1 pending cancellation
        canceller = NoShowCanceller(
            shuttle_id="shuttle_001", db_path=TEST_DB
        )
        canceller._queue_cancellation({
            "booking_id": "queued_old",
            "user_uid": "u_old",
        })

        # Firebase returns 1 fresh no-show at CONAS
        mock_query_ref = MagicMock()
        mock_query_ref.get.return_value = {
            "fresh_no_show": {
                "booking_id": "fresh_no_show",
                "user_uid": "u_fresh",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
        }
        mock_root_ref = MagicMock()
        # db.reference is called many times: for drain (cancel_one),
        # for the query, and again for new cancellations. Return
        # mock_root_ref for the "/" calls and mock_query_ref for
        # the "bookings" calls.
        def reference_router(path):
            if path == "bookings":
                return mock_query_ref
            return mock_root_ref
        mock_db.reference.side_effect = reference_router

        count = canceller.cancel_no_shows(stop="CONAS")

        # 1 drained from queue + 1 fresh cancellation = 2
        assert count == 2
        # queue should be empty now
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_cancellations")
        assert cursor.fetchone()[0] == 0
        conn.close()

    @patch("no_show_canceller.db")
    def test_cancel_no_shows_queues_when_firebase_fails(self, mock_db):
        """
        When Firebase is unreachable during the cancellation
        writes, the failed cancellations should be queued in
        SQLite for retry. The method returns 0 (none confirmed
        cancelled) but the queue ensures eventual consistency
        — they'll be drained on the next call.
        """
        mock_query_ref = MagicMock()
        mock_query_ref.get.return_value = {
            "no_show_a": {
                "booking_id": "no_show_a",
                "user_uid": "u_a",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "no_show_b": {
                "booking_id": "no_show_b",
                "user_uid": "u_b",
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
        }
        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Firebase down")

        def reference_router(path):
            if path == "bookings":
                return mock_query_ref
            return mock_root_ref
        mock_db.reference.side_effect = reference_router

        canceller = NoShowCanceller(
            shuttle_id="shuttle_001", db_path=TEST_DB
        )
        count = canceller.cancel_no_shows(stop="CONAS")

        # 0 confirmed cancellations, but 2 queued for retry
        assert count == 0
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_cancellations")
        assert cursor.fetchone()[0] == 2
        conn.close()

    @patch("no_show_canceller.db")
    def test_cancel_no_shows_returns_zero_when_nothing_to_do(self, mock_db):
        """
        When no queued cancellations exist and no fresh no-shows
        match the stop, cancel_no_shows should return 0 cleanly.
        Most successful boarding stops will hit this case — clean
        departure, no cancellations needed.
        """
        mock_query_ref = MagicMock()
        mock_query_ref.get.return_value = {}
        mock_db.reference.return_value = mock_query_ref

        canceller = NoShowCanceller(
            shuttle_id="shuttle_001", db_path=TEST_DB
        )
        count = canceller.cancel_no_shows(stop="CONAS")

        assert count == 0
