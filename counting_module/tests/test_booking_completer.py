"""
Tests for the BookingCompleter component.

The BookingCompleter is responsible for closing the booking
lifecycle when a passenger alights at their destination stop.
Called by main.py on each detected alighting event, it finds
the oldest active booking whose destination matches the
shuttle's current stop and transitions it to 'completed' in
Firebase.

This component completes the 4-state booking lifecycle:
  reserved (mobile app) -> active (QR scanner) -> completed
  (counting module on alighting). It owns no UI, no counting
  logic, no scanner orchestration -- purely Firebase booking
  state transitions for the alighting event.

All Firebase interactions are mocked throughout so the
component can be verified in pure isolation.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from booking_completer import BookingCompleter


class TestBookingCompleterInitialization:
    """Tests covering BookingCompleter construction."""

    def test_completer_initializes_with_defaults(self):
        """
        BookingCompleter should instantiate without arguments
        and be ready to query bookings. Firebase initialization
        is lazy so the class can be constructed in tests without
        needing real credentials.
        """
        completer = BookingCompleter()
        assert completer is not None
        assert hasattr(completer, "shuttle_id")

    def test_completer_uses_shuttle_id_from_env(self):
        """
        Like firebase_sync, data_logger, and scanner_orchestrator,
        BookingCompleter reads the shuttle_id from the SHUTTLE_ID
        environment variable. This keeps configuration consistent
        across the whole counting module.
        """
        with patch.dict(os.environ, {"SHUTTLE_ID": "shuttle_test_42"}):
            completer = BookingCompleter()
            assert completer.shuttle_id == "shuttle_test_42"

    def test_completer_accepts_explicit_shuttle_id(self):
        """
        For tests and special deployments, the shuttle_id can be
        passed at construction time, overriding the environment
        variable. This makes the class easy to test in isolation
        without environment manipulation.
        """
        completer = BookingCompleter(shuttle_id="custom_shuttle_99")
        assert completer.shuttle_id == "custom_shuttle_99"


class TestFindOldestActiveBooking:
    """
    Tests covering the Firebase query that finds the right
    booking to complete on an alighting event.
    """

    @patch("booking_completer.db")
    def test_returns_oldest_active_booking_at_destination(self, mock_db):
        """
        When multiple active bookings exist for the shuttle with
        the same destination stop, the OLDEST (first to board)
        should be returned. We sort by boarded_at ascending and
        pick the first match, modelling the natural assumption
        that the first person to board is the first to alight.
        """
        # Firebase returns all bookings for this shuttle.
        # Only some of them will match our filter criteria.
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id_younger": {
                "booking_id": "booking_id_younger",
                "user_uid": "user2",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 2000,
            },
            "booking_id_older": {
                "booking_id": "booking_id_older",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
            "booking_id_other_destination": {
                "booking_id": "booking_id_other_destination",
                "user_uid": "user3",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "Main Library",
                "boarded_at": 500,
            },
        }
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.find_oldest_active_booking(current_stop="COCIS")

        assert result is not None
        assert result["booking_id"] == "booking_id_older"

    @patch("booking_completer.db")
    def test_returns_none_when_no_active_booking_matches(self, mock_db):
        """
        When no active booking matches the shuttle's current stop,
        find_oldest_active_booking should return None so the caller
        can log a warning and continue. This is the common case
        when a non-app passenger alights without a booking.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_only_reserved": {
                "booking_id": "booking_only_reserved",
                "status": "reserved",
                "destination_stop": "COCIS",
                "shuttle_key": "shuttle_001",
            },
            "booking_different_destination": {
                "booking_id": "booking_different_destination",
                "status": "active",
                "destination_stop": "Main Library",
                "shuttle_key": "shuttle_001",
                "boarded_at": 1000,
            },
        }
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.find_oldest_active_booking(current_stop="COCIS")

        assert result is None

    @patch("booking_completer.db")
    def test_returns_none_when_firebase_empty(self, mock_db):
        """
        On a fresh deployment with no bookings, Firebase returns
        None for /bookings. find_oldest_active_booking must
        handle this cleanly and return None rather than crashing
        with a TypeError. This protects main.py's counting loop.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.find_oldest_active_booking(current_stop="COCIS")

        assert result is None

    @patch("booking_completer.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Bookings for OTHER shuttles must be ignored — the completer
        must never accidentally close a booking belonging to a
        different shuttle. We verify this by including a matching
        booking for a different shuttle and confirming it's not
        returned even though every other field matches.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "other_shuttle_booking": {
                "booking_id": "other_shuttle_booking",
                "shuttle_key": "shuttle_002",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
        }
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.find_oldest_active_booking(current_stop="COCIS")

        assert result is None

    @patch("booking_completer.db")
    def test_returns_none_on_firebase_error(self, mock_db):
        """
        If Firebase raises an exception during lookup (network
        glitch, permissions, etc), find_oldest_active_booking
        should catch it and return None. The counting pipeline
        must never crash because of a Firebase blip.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.find_oldest_active_booking(current_stop="COCIS")

        assert result is None


class TestMarkAsCompleted:
    """
    Tests covering the Firebase write that transitions a
    booking from 'active' to 'completed'.
    """

    @patch("booking_completer.db")
    def test_mark_as_completed_updates_both_paths(self, mock_db):
        """
        Completion must update BOTH /bookings/{id} and
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
            "status": "active",
            "destination_stop": "COCIS",
        }

        completer = BookingCompleter()
        result = completer.mark_as_completed(booking)

        assert result is True
        mock_db.reference.assert_called_with("/")
        mock_root_ref.update.assert_called_once()
        payload = mock_root_ref.update.call_args[0][0]
        assert payload["bookings/abc123/status"] == "completed"
        assert payload["user_bookings/user1/abc123/status"] == "completed"
        assert "bookings/abc123/completed_at" in payload
        assert "user_bookings/user1/abc123/completed_at" in payload

    @patch("booking_completer.db")
    def test_mark_as_completed_returns_false_on_firebase_error(self, mock_db):
        """
        If Firebase rejects the update (network glitch, permissions,
        etc), mark_as_completed should return False rather than
        crashing. Callers can log the failure and continue.
        """
        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_root_ref

        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
            "status": "active",
        }

        completer = BookingCompleter()
        result = completer.mark_as_completed(booking)

        assert result is False

    @patch("booking_completer.db")
    def test_mark_as_completed_handles_missing_user_uid(self, mock_db):
        """
        A booking record without user_uid is corrupt — we must
        not write to /user_bookings/None/... and risk creating
        garbage paths in Firebase. The method rejects cleanly
        with False so the caller can flag the data quality issue.
        """
        booking = {
            "booking_id": "abc123",
            "status": "active",
        }

        completer = BookingCompleter()
        result = completer.mark_as_completed(booking)

        assert result is False

    @patch("booking_completer.db")
    def test_mark_as_completed_handles_missing_booking_id(self, mock_db):
        """
        Same defensive principle for booking_id — a missing one
        means the booking record is corrupt. Reject cleanly
        rather than writing to /bookings/None/.
        """
        booking = {
            "user_uid": "user1",
            "status": "active",
        }

        completer = BookingCompleter()
        result = completer.mark_as_completed(booking)

        assert result is False


class TestCompleteAlighting:
    """
    Tests covering the full complete_alighting() flow that
    main.py calls on each detected alighting event.
    """

    @patch("booking_completer.db")
    def test_complete_alighting_full_flow_success(self, mock_db):
        """
        When an active booking matches the alighting's destination,
        complete_alighting should find it and mark it completed
        in one call. Returns True so main.py can log success.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "abc123": {
                "booking_id": "abc123",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
        }
        mock_root_ref = MagicMock()
        # db.reference is called twice: once with "bookings" for
        # the query, once with "/" for the atomic update
        mock_db.reference.side_effect = [mock_ref, mock_root_ref]

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.complete_alighting(current_stop="COCIS")

        assert result is True
        mock_root_ref.update.assert_called_once()

    @patch("booking_completer.db")
    def test_complete_alighting_returns_false_when_no_match(self, mock_db):
        """
        When no active booking matches the alighting (non-app
        passenger, false-positive detection, or all bookings
        already completed), complete_alighting returns False
        without raising. main.py logs a warning and continues
        the counting pipeline.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {}
        mock_db.reference.return_value = mock_ref

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.complete_alighting(current_stop="COCIS")

        assert result is False

    @patch("booking_completer.db")
    def test_complete_alighting_returns_false_on_completion_failure(
        self, mock_db
    ):
        """
        Booking was found, but the Firebase write failed. The
        booking stays 'active' (no partial state), and the
        method returns False so main.py knows to log the issue.
        Avoids silently swallowing a real Firebase failure.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "abc123": {
                "booking_id": "abc123",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
        }
        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Firebase down")
        mock_db.reference.side_effect = [mock_ref, mock_root_ref]

        completer = BookingCompleter(shuttle_id="shuttle_001")
        result = completer.complete_alighting(current_stop="COCIS")

        assert result is False

    @patch("booking_completer.db")
    def test_complete_alighting_cascades_for_multiple_alightings(
        self, mock_db
    ):
        """
        When multiple people alight at the same stop, main.py
        calls complete_alighting once per alighting event. Each
        call must complete a DIFFERENT booking (oldest first
        cascades naturally as the previously-completed booking
        is no longer 'active' on the next query).

        We simulate two sequential calls with a Firebase query
        that returns different active bookings each time -- the
        second call sees the world after the first completion.
        """
        first_query = {
            "older": {
                "booking_id": "older",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
            "younger": {
                "booking_id": "younger",
                "user_uid": "user2",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 2000,
            },
        }
        # after first completion, "older" is no longer active
        second_query = {
            "older": {
                "booking_id": "older",
                "user_uid": "user1",
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "COCIS",
                "boarded_at": 1000,
            },
            "younger": {
                "booking_id": "younger",
                "user_uid": "user2",
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "COCIS",
                "boarded_at": 2000,
            },
        }

        mock_query_ref_1 = MagicMock()
        mock_query_ref_1.get.return_value = first_query
        mock_query_ref_2 = MagicMock()
        mock_query_ref_2.get.return_value = second_query

        mock_root_ref = MagicMock()
        mock_db.reference.side_effect = [
            mock_query_ref_1, mock_root_ref,  # first call
            mock_query_ref_2, mock_root_ref,  # second call
        ]

        completer = BookingCompleter(shuttle_id="shuttle_001")

        result1 = completer.complete_alighting(current_stop="COCIS")
        result2 = completer.complete_alighting(current_stop="COCIS")

        assert result1 is True
        assert result2 is True
        # both updates should reference different bookings
        first_payload = mock_root_ref.update.call_args_list[0][0][0]
        second_payload = mock_root_ref.update.call_args_list[1][0][0]
        assert "bookings/older/status" in first_payload
        assert "bookings/younger/status" in second_payload
