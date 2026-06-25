"""
Tests for the booking_listener_setup helper module.

The helper extracts the booking-listener startup logic previously
embedded in ScannerOrchestrator._start_booking_listener so it can
be called from any process. The dashboard process now calls this
helper at startup so booking events are processed continuously
regardless of whether the orchestrator is running.

Owning the listener in the always-on dashboard rather than the
service-hours-only orchestrator avoids the previous bug where
bookings made while the orchestrator was idle would not decrement
the seat pool until the orchestrator next started. It also avoids
the double-decrement risk of running two listeners across two
processes by ensuring only one process ever runs the listener at
all.
"""

import os
import sys
import threading

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestStartBookingListener:
    """
    Tests for the start_booking_listener() helper function.

    The helper is expected to:
      1. Build a FirebaseSyncComponent for the given shuttle_id
      2. Build a SeatPoolManager wired to that FirebaseSyncComponent
      3. Build a BookingFirebaseListener wired to that SeatPoolManager
      4. Attach the listener's handler to db.reference("bookings").listen()
      5. Start a daemon polling thread as a fallback for child_changed
      6. Return the listener instance so the caller can hold a reference
    """

    @patch("booking_listener_setup.threading.Thread")
    @patch("booking_listener_setup.db.reference")
    @patch("booking_listener_setup.BookingFirebaseListener")
    @patch("booking_listener_setup.SeatPoolManager")
    @patch("booking_listener_setup.FirebaseSyncComponent")
    def test_helper_builds_full_listener_stack(
        self,
        mock_firebase_sync_class,
        mock_seat_pool_class,
        mock_listener_class,
        mock_db_reference,
        mock_thread_class,
    ):
        """
        Calling start_booking_listener should construct every layer
        of the listener stack and wire them together.
        """
        from booking_listener_setup import start_booking_listener

        mock_firebase_sync = mock_firebase_sync_class.return_value
        mock_seat_pool = mock_seat_pool_class.return_value
        mock_listener = mock_listener_class.return_value

        result = start_booking_listener(
            shuttle_id="shuttle_001",
            db_path="local_database/test_apcoms.db",
        )

        # built the firebase sync component for this shuttle
        mock_firebase_sync_class.assert_called_once_with(shuttle_id="shuttle_001")
        mock_firebase_sync.initialize.assert_called_once()

        # built the seat pool wired to that sync
        mock_seat_pool_class.assert_called_once()
        seat_pool_kwargs = mock_seat_pool_class.call_args.kwargs
        assert seat_pool_kwargs.get("db_path") == "local_database/test_apcoms.db"
        assert seat_pool_kwargs.get("firebase_sync") is mock_firebase_sync

        # built the listener wired to the seat pool
        mock_listener_class.assert_called_once()
        listener_kwargs = mock_listener_class.call_args.kwargs
        assert listener_kwargs.get("shuttle_id") == "shuttle_001"
        assert listener_kwargs.get("db_path") == "local_database/test_apcoms.db"
        assert listener_kwargs.get("seat_pool_manager") is mock_seat_pool

        # returned the listener instance
        assert result is mock_listener

    @patch("booking_listener_setup.threading.Thread")
    @patch("booking_listener_setup.db.reference")
    @patch("booking_listener_setup.BookingFirebaseListener")
    @patch("booking_listener_setup.SeatPoolManager")
    @patch("booking_listener_setup.FirebaseSyncComponent")
    def test_helper_attaches_streaming_listener_to_bookings_ref(
        self,
        mock_firebase_sync_class,
        mock_seat_pool_class,
        mock_listener_class,
        mock_db_reference,
        mock_thread_class,
    ):
        """
        The helper must attach a handler to db.reference('bookings').listen()
        so booking events flow from Firebase into the listener.
        """
        from booking_listener_setup import start_booking_listener

        mock_bookings_ref = MagicMock()
        mock_db_reference.return_value = mock_bookings_ref

        start_booking_listener(
            shuttle_id="shuttle_001",
            db_path="local_database/test_apcoms.db",
        )

        mock_db_reference.assert_any_call("bookings")
        mock_bookings_ref.listen.assert_called_once()

    @patch("booking_listener_setup.threading.Thread")
    @patch("booking_listener_setup.db.reference")
    @patch("booking_listener_setup.BookingFirebaseListener")
    @patch("booking_listener_setup.SeatPoolManager")
    @patch("booking_listener_setup.FirebaseSyncComponent")
    def test_helper_starts_polling_thread_as_daemon(
        self,
        mock_firebase_sync_class,
        mock_seat_pool_class,
        mock_listener_class,
        mock_db_reference,
        mock_thread_class,
    ):
        """
        The helper must start a daemon polling thread so cancellations
        the streaming listener misses (firebase-admin's .listen() does
        not deliver child_changed reliably) still get processed within
        a couple of seconds.
        """
        from booking_listener_setup import start_booking_listener

        mock_thread = mock_thread_class.return_value

        start_booking_listener(
            shuttle_id="shuttle_001",
            db_path="local_database/test_apcoms.db",
        )

        mock_thread_class.assert_called_once()
        thread_kwargs = mock_thread_class.call_args.kwargs
        assert thread_kwargs.get("daemon") is True
        mock_thread.start.assert_called_once()
