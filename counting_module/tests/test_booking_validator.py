"""
Tests for the BookingValidator component.

The BookingValidator is responsible for validating QR scan payloads
against Firebase booking records and managing the booking lifecycle
transitions that the QR scanner triggers (status -> active on valid
scan, boarded_at timestamp).

Validation logic is the heart of the booking integration. These
tests verify each rule independently and cover the success and
rejection paths. Firebase interactions are mocked throughout —
this component is tested in pure isolation.
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from booking_validator import BookingValidator


class TestBookingValidatorInitialization:
    """Tests covering BookingValidator construction."""

    def test_validator_initializes_with_defaults(self):
        """
        BookingValidator should instantiate without arguments and
        be ready to validate. The Firebase client itself is lazily
        loaded so tests can instantiate the class without needing
        Firebase credentials.
        """
        validator = BookingValidator()
        assert validator is not None


class TestPayloadParsing:
    """Tests covering parsing of QR payload strings."""

    def test_parse_payload_extracts_booking_id_and_token(self):
        """
        The QR payload is a JSON string created by Cissy's app
        when a booking is made. parse_payload should extract the
        bookingId AND the token so the validator can both look up
        the booking record and verify QR authenticity.

        The actual payload structure produced by the latest mobile
        app is: {v: 1, bookingId, t}. Short form with anti-forgery
        token, no other fields needed (the rest comes from the
        booking record in Firebase).
        """
        payload = '{"v":1,"bookingId":"abc123","t":"token_xyz"}'

        validator = BookingValidator()
        result = validator.parse_payload(payload)

        assert result is not None
        assert result["bookingId"] == "abc123"
        assert result["t"] == "token_xyz"

    def test_parse_payload_returns_none_for_invalid_json(self):
        """
        If the QR contains malformed JSON (e.g. a random string,
        not from our app), parse_payload should return None rather
        than crashing. This lets callers reject the scan cleanly
        with a clear reason rather than seeing a stack trace.
        """
        validator = BookingValidator()
        result = validator.parse_payload("not_valid_json_at_all")

        assert result is None

    def test_parse_payload_returns_none_for_missing_booking_id(self):
        """
        A payload that is valid JSON but does not contain the
        bookingId field is invalid. The validator must reject it
        by returning None so callers can give the user a clear
        error message.
        """
        payload = '{"v":1,"t":"some_token"}'

        validator = BookingValidator()
        result = validator.parse_payload(payload)

        assert result is None

    def test_parse_payload_returns_none_for_missing_token(self):
        """
        Cissy's app embeds a short random token in every QR payload
        as an anti-forgery measure. A payload without the 't' field
        is incomplete and must be rejected — without the token we
        can't verify the QR was legitimately issued for this booking.
        """
        payload = '{"v":1,"bookingId":"abc123"}'

        validator = BookingValidator()
        result = validator.parse_payload(payload)

        assert result is None

    def test_parse_payload_handles_empty_string(self):
        """
        An empty payload (which shouldn't happen in practice but
        could occur during a glitched scan) must be rejected
        gracefully — return None, don't crash.
        """
        validator = BookingValidator()
        result = validator.parse_payload("")

        assert result is None


class TestFetchBooking:
    """Tests covering Firebase booking lookup by ID."""

    @patch("booking_validator.db")
    def test_fetch_booking_returns_booking_dict_when_found(self, mock_db):
        """
        Given a booking ID that exists in Firebase, fetch_booking
        should return the booking as a dictionary. The dictionary
        includes all booking fields per the schema document (status,
        pickup_stop, user_uid, etc).
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id": "abc123",
            "status": "reserved",
            "pickup_stop": "Western Gate",
            "user_uid": "user1",
        }
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        result = validator.fetch_booking("abc123")

        assert result is not None
        assert result["booking_id"] == "abc123"
        assert result["status"] == "reserved"
        mock_db.reference.assert_called_once_with("bookings/abc123")

    @patch("booking_validator.db")
    def test_fetch_booking_returns_none_when_not_found(self, mock_db):
        """
        If the booking ID does not exist in Firebase, fetch_booking
        should return None. This lets callers cleanly reject the
        scan with a "Booking not found" message rather than handling
        a missing-key exception.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        result = validator.fetch_booking("nonexistent_id")

        assert result is None

    @patch("booking_validator.db")
    def test_fetch_booking_returns_none_on_firebase_error(self, mock_db):
        """
        If Firebase raises an exception (network error, permission
        denied, etc), fetch_booking should catch it and return None
        rather than crashing. This makes the scanner resilient to
        transient Firebase issues — the user sees a rejection
        message and can re-scan.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        result = validator.fetch_booking("abc123")

        assert result is None


class TestValidateScan:
    """
    Tests covering the full validate_scan() flow.

    validate_scan() is the public entry point used by the QR
    scanner runtime. It accepts a raw QR payload string and the
    current shuttle stop, then runs all validation rules and
    returns a structured result.

    Result dictionary shape:
        {
            "valid": bool,
            "booking": dict or None,
            "reason": str    (only set when valid is False)
        }
    """

    @patch("booking_validator.db")
    def test_valid_scan_returns_success(self, mock_db):
        """
        When the payload parses, the booking exists in Firebase,
        its status is 'reserved', and its pickup_stop matches the
        current shuttle stop, validate_scan should return a
        success result with the booking attached.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id": "abc123",
            "status": "reserved",
            "pickup_stop": "Western Gate",
            "user_uid": "user1",
            "qr_token": "valid_token",
        }
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        payload = '{"bookingId":"abc123","t":"valid_token"}'
        result = validator.validate_scan(payload, current_stop="Western Gate")

        assert result["valid"] is True
        assert result["booking"]["booking_id"] == "abc123"

    def test_invalid_payload_returns_failure(self):
        """
        If the QR payload is unparseable, validate_scan should
        reject with reason 'invalid_payload'. No Firebase calls
        are made — the payload failure is detected before any
        network round trip.
        """
        validator = BookingValidator()
        result = validator.validate_scan("not_valid_json", current_stop="Western Gate")

        assert result["valid"] is False
        assert result["reason"] == "invalid_payload"

    @patch("booking_validator.db")
    def test_missing_booking_returns_failure(self, mock_db):
        """
        If the booking ID parses but does not exist in Firebase,
        validate_scan should reject with reason 'booking_not_found'.
        This protects against scanning a QR for a booking that has
        been deleted from the database.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        payload = '{"bookingId":"abc123","t":"valid_token"}'
        result = validator.validate_scan(payload, current_stop="Western Gate")

        assert result["valid"] is False
        assert result["reason"] == "booking_not_found"

    @patch("booking_validator.db")
    def test_wrong_status_returns_failure(self, mock_db):
        """
        If the booking exists but its status is not 'reserved'
        (e.g. already 'active' because someone scanned it earlier,
        or 'cancelled'), validate_scan should reject with reason
        'wrong_status' so the operator knows the QR is unusable.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id": "abc123",
            "status": "active",
            "pickup_stop": "Western Gate",
            "qr_token": "valid_token",
        }
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        payload = '{"bookingId":"abc123","t":"valid_token"}'
        result = validator.validate_scan(payload, current_stop="Western Gate")

        assert result["valid"] is False
        assert result["reason"] == "wrong_status"

    @patch("booking_validator.db")
    def test_wrong_pickup_stop_returns_failure(self, mock_db):
        """
        If the booking's pickup_stop does not match the shuttle's
        current_stop, validate_scan should reject with reason
        'wrong_pickup_stop'. This enforces the campus policy that
        users must scan at the stop they booked for.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id": "abc123",
            "status": "reserved",
            "pickup_stop": "CEDAT",
            "qr_token": "valid_token",
        }
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        payload = '{"bookingId":"abc123","t":"valid_token"}'
        result = validator.validate_scan(payload, current_stop="Western Gate")

        assert result["valid"] is False
        assert result["reason"] == "wrong_pickup_stop"

    @patch("booking_validator.db")
    def test_wrong_token_returns_failure(self, mock_db):
        """
        Cissy's app issues a random token per booking and stores it
        on the booking record as qr_token. The QR payload includes
        the same token as field 't'. If they don't match, the scan
        is rejected as 'invalid_token' — protects against forgery
        attempts where someone might learn a bookingId and try to
        scan a fake QR for it.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "booking_id": "abc123",
            "status": "reserved",
            "pickup_stop": "Western Gate",
            "user_uid": "user1",
            "qr_token": "real_token",
        }
        mock_db.reference.return_value = mock_ref

        validator = BookingValidator()
        payload = '{"bookingId":"abc123","t":"forged_token"}'
        result = validator.validate_scan(payload, current_stop="Western Gate")

        assert result["valid"] is False
        assert result["reason"] == "invalid_token"


class TestMarkAsActive:
    """Tests covering the booking transition to 'active' status."""

    @patch("booking_validator.db")
    def test_mark_as_active_updates_both_paths(self, mock_db):
        """
        After a valid scan, the booking must be marked active in
        BOTH /bookings/{id} and /user_bookings/{uid}/{id} so the
        mobile app's per-user view stays in sync. Cissy's app
        writes both paths at booking creation; we mirror her
        atomic-update pattern here.
        """
        mock_root_ref = MagicMock()
        mock_db.reference.return_value = mock_root_ref

        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
            "status": "reserved",
            "pickup_stop": "Western Gate",
        }

        validator = BookingValidator()
        result = validator.mark_as_active(booking)

        assert result is True
        # one atomic update call to the root with multi-path payload
        mock_db.reference.assert_called_with("/")
        mock_root_ref.update.assert_called_once()
        update_payload = mock_root_ref.update.call_args[0][0]
        assert update_payload["bookings/abc123/status"] == "active"
        assert update_payload["user_bookings/user1/abc123/status"] == "active"
        assert "bookings/abc123/boarded_at" in update_payload
        assert "user_bookings/user1/abc123/boarded_at" in update_payload

    @patch("booking_validator.db")
    def test_mark_as_active_returns_false_on_firebase_error(self, mock_db):
        """
        If the Firebase update fails (network error, permission
        denied, etc), mark_as_active should return False rather
        than crashing. Callers can then surface a clean error to
        the operator instead of seeing a stack trace.
        """
        mock_root_ref = MagicMock()
        mock_root_ref.update.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_root_ref

        booking = {
            "booking_id": "abc123",
            "user_uid": "user1",
            "status": "reserved",
        }

        validator = BookingValidator()
        result = validator.mark_as_active(booking)

        assert result is False

    @patch("booking_validator.db")
    def test_mark_as_active_handles_missing_user_uid(self, mock_db):
        """
        A booking record without a user_uid is corrupt — we
        should not write to /user_bookings/None/... so the method
        must reject the operation cleanly. Returns False so
        callers can flag this as an integrity issue.
        """
        booking = {
            "booking_id": "abc123",
            "status": "reserved",
        }

        validator = BookingValidator()
        result = validator.mark_as_active(booking)

        assert result is False
