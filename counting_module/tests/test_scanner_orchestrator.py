"""
Tests for the ScannerOrchestrator component.

The ScannerOrchestrator is the operator's main entry point for the
booking integration flow. It coordinates the QR scanner, booking
validator, main.py subprocess, and Firebase sync into a continuous
boarding loop.

This is the top-level conductor — it doesn't scan QRs, validate
bookings, or count passengers itself. It just decides WHEN each of
those components runs and feeds them the right state from SQLite.

Firebase, subprocess, sqlite3, and the underlying QRScanner and
BookingValidator are all mocked throughout these tests so the
orchestrator can be verified in pure isolation.
"""

import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from scanner_orchestrator import ScannerOrchestrator

TEST_DB = "local_database/test_apcoms.db"


class TestOrchestratorInitialization:
    """Tests covering ScannerOrchestrator construction."""

    def test_orchestrator_initializes_with_defaults(self):
        """
        ScannerOrchestrator should instantiate without arguments
        and expose sensible defaults. The scanner, validator, and
        firebase_sync components are not constructed until run()
        is called, so the orchestrator itself stays lightweight
        and easy to test.
        """
        orchestrator = ScannerOrchestrator()
        assert orchestrator is not None
        assert hasattr(orchestrator, "db_path")
        assert hasattr(orchestrator, "shuttle_id")

    def test_orchestrator_accepts_custom_db_path(self):
        """
        Tests need to point at the test database to avoid polluting
        production state. The db_path parameter follows the same
        pattern as DataLogger and ScenarioManager.
        """
        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        assert orchestrator.db_path == TEST_DB

    def test_orchestrator_uses_shuttle_id_from_env(self):
        """
        Like firebase_sync and data_logger, the orchestrator should
        read the shuttle_id from the SHUTTLE_ID environment variable.
        This keeps configuration consistent across the whole
        counting module.
        """
        with patch.dict(os.environ, {"SHUTTLE_ID": "shuttle_test_42"}):
            orchestrator = ScannerOrchestrator()
            assert orchestrator.shuttle_id == "shuttle_test_42"


class TestReadCurrentStop:
    """Tests covering how the orchestrator discovers the shuttle's stop."""

    def setup_method(self):
        """
        Reset the test database before each test so state from a
        previous test doesn't leak. We use the same TEST_DB path
        the other tests use so isolation is consistent.
        """
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state WHERE key='current_stop'")
        conn.commit()
        conn.close()

    def test_read_current_stop_returns_persisted_value(self):
        """
        When main.py has written current_stop to system_state, the
        orchestrator should read it back. This is how the
        orchestrator knows which stop the shuttle is at so QR
        validation compares pickups correctly.
        """
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_state (key, value) VALUES ('current_stop', ?)",
            ("CONAS",),
        )
        conn.commit()
        conn.close()

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.read_current_stop()

        assert result == "CONAS"

    def test_read_current_stop_defaults_when_missing(self):
        """
        On fresh deployment (or after a database reset) the
        current_stop row may not exist yet. The orchestrator
        should return a sensible default ('Western Gate', the
        first stop in the loop) so the first boarding session
        can still proceed without manual setup.
        """
        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.read_current_stop()

        assert result == "Western Gate"


class TestProcessScan:
    """Tests covering single-scan processing through the orchestrator."""

    @patch("scanner_orchestrator.BookingValidator")
    def test_valid_scan_marks_booking_active(self, mock_validator_class):
        """
        A valid scan should trigger mark_as_active on the validator,
        flipping the booking from 'reserved' to 'active' in Firebase.
        The orchestrator returns the result dict so the queue loop
        can log it appropriately.
        """
        mock_validator = MagicMock()
        mock_validator.validate_scan.return_value = {
            "valid": True,
            "booking": {
                "booking_id": "abc123",
                "user_uid": "user1",
                "pickup_stop": "CONAS",
                "destination_stop": "COCIS",
            },
        }
        mock_validator.mark_as_active.return_value = True
        mock_validator_class.return_value = mock_validator

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.process_scan(
            payload='{"v":1,"bookingId":"abc123","t":"token"}',
            current_stop="CONAS",
        )

        assert result["valid"] is True
        mock_validator.validate_scan.assert_called_once_with(
            '{"v":1,"bookingId":"abc123","t":"token"}',
            current_stop="CONAS",
        )
        mock_validator.mark_as_active.assert_called_once_with(
            result["booking"]
        )

    @patch("scanner_orchestrator.BookingValidator")
    def test_invalid_scan_does_not_mark_active(self, mock_validator_class):
        """
        A rejected scan should NOT trigger mark_as_active. We must
        never transition a booking to 'active' when validation
        failed — that would corrupt the booking state. The
        orchestrator returns the rejection result so the queue
        loop can display the reason to the operator.
        """
        mock_validator = MagicMock()
        mock_validator.validate_scan.return_value = {
            "valid": False,
            "booking": None,
            "reason": "wrong_pickup_stop",
        }
        mock_validator_class.return_value = mock_validator

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.process_scan(
            payload='{"v":1,"bookingId":"abc123","t":"token"}',
            current_stop="CONAS",
        )

        assert result["valid"] is False
        assert result["reason"] == "wrong_pickup_stop"
        mock_validator.mark_as_active.assert_not_called()

    @patch("scanner_orchestrator.BookingValidator")
    def test_valid_scan_but_mark_active_fails(self, mock_validator_class):
        """
        Validation passed but mark_as_active returned False (e.g.
        Firebase write failure). The orchestrator should surface
        this as a failure so the operator knows the booking
        wasn't actually transitioned. We return a tagged result
        indicating the validation passed but the transition didn't.
        """
        mock_validator = MagicMock()
        mock_validator.validate_scan.return_value = {
            "valid": True,
            "booking": {
                "booking_id": "abc123",
                "user_uid": "user1",
            },
        }
        mock_validator.mark_as_active.return_value = False
        mock_validator_class.return_value = mock_validator

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.process_scan(
            payload='{"v":1,"bookingId":"abc123","t":"token"}',
            current_stop="CONAS",
        )

        assert result["valid"] is False
        assert result["reason"] == "mark_active_failed"


class TestRunScanQueue:
    """Tests covering the queue loop that processes multiple scans."""

    @patch("scanner_orchestrator.time.sleep")
    @patch("scanner_orchestrator.BookingValidator")
    @patch("scanner_orchestrator.QRScanner")
    def test_queue_loops_until_no_scan(
        self, mock_scanner_class, mock_validator_class, mock_sleep
    ):
        """
        The queue should keep running scanner.run() in a loop. Each
        call that produces a payload counts as one passenger boarding.
        When scanner.run() exits without invoking the callback (user
        pressed 'q'), the queue ends.

        We simulate 2 successful scans then a 'q' exit by configuring
        scanner.run() to invoke the callback on the first 2 calls and
        not invoke it on the 3rd call.
        """
        # set up validator to always return valid scans
        mock_validator = MagicMock()
        mock_validator.validate_scan.return_value = {
            "valid": True,
            "booking": {"booking_id": "abc", "user_uid": "u"},
        }
        mock_validator.mark_as_active.return_value = True
        mock_validator_class.return_value = mock_validator

        # set up scanner: first 2 runs invoke callback, 3rd does not
        mock_scanner = MagicMock()
        call_index = [0]

        def fake_run(on_qr_detected):
            if call_index[0] < 2:
                on_qr_detected(f'{{"v":1,"bookingId":"id{call_index[0]}","t":"tok"}}')
            call_index[0] += 1

        mock_scanner.run.side_effect = fake_run
        mock_scanner_class.return_value = mock_scanner

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        scan_count = orchestrator.run_scan_queue(current_stop="CONAS")

        # 2 successful scans, then queue ended
        assert scan_count == 2
        # scanner.run() called 3 times total (2 successes + 1 exit)
        assert mock_scanner.run.call_count == 3
        # validator was called for each successful scan
        assert mock_validator.validate_scan.call_count == 2
        assert mock_validator.mark_as_active.call_count == 2

    @patch("scanner_orchestrator.time.sleep")
    @patch("scanner_orchestrator.BookingValidator")
    @patch("scanner_orchestrator.QRScanner")
    def test_queue_pauses_between_scans(
        self, mock_scanner_class, mock_validator_class, mock_sleep
    ):
        """
        Between successful scans, the orchestrator should pause
        briefly to give the next passenger time to step up and
        unlock their phone. We mock time.sleep so the test runs
        instantly but assert it was called with the expected
        pause duration. Increased to 3 seconds for better demo visibility.
        """
        mock_validator = MagicMock()
        mock_validator.validate_scan.return_value = {
            "valid": True,
            "booking": {"booking_id": "abc", "user_uid": "u"},
        }
        mock_validator.mark_as_active.return_value = True
        mock_validator_class.return_value = mock_validator

        mock_scanner = MagicMock()
        call_index = [0]

        def fake_run(on_qr_detected):
            if call_index[0] < 1:
                on_qr_detected('{"v":1,"bookingId":"abc","t":"tok"}')
            call_index[0] += 1

        mock_scanner.run.side_effect = fake_run
        mock_scanner_class.return_value = mock_scanner

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.run_scan_queue(current_stop="CONAS")

        # at least one sleep call with 3-second pause between scans
        mock_sleep.assert_called_with(3)

    @patch("scanner_orchestrator.time.sleep")
    @patch("scanner_orchestrator.BookingValidator")
    @patch("scanner_orchestrator.QRScanner")
    def test_queue_continues_after_rejected_scan(
        self, mock_scanner_class, mock_validator_class, mock_sleep
    ):
        """
        A rejected scan (invalid payload, wrong stop, etc) should
        not terminate the queue. The operator may want to give the
        passenger a chance to re-scan, or move on to the next
        person. We confirm the loop continues after a rejection
        until the operator quits.
        """
        mock_validator = MagicMock()
        # first scan rejected, second accepted
        mock_validator.validate_scan.side_effect = [
            {"valid": False, "booking": None, "reason": "invalid_token"},
            {
                "valid": True,
                "booking": {"booking_id": "abc", "user_uid": "u"},
            },
        ]
        mock_validator.mark_as_active.return_value = True
        mock_validator_class.return_value = mock_validator

        mock_scanner = MagicMock()
        call_index = [0]

        def fake_run(on_qr_detected):
            if call_index[0] < 2:
                on_qr_detected(f'{{"v":1,"bookingId":"id{call_index[0]}","t":"tok"}}')
            call_index[0] += 1

        mock_scanner.run.side_effect = fake_run
        mock_scanner_class.return_value = mock_scanner

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        scan_count = orchestrator.run_scan_queue(current_stop="CONAS")

        # only the SUCCESSFUL scan counts toward boarding
        assert scan_count == 1
        # but the validator was called twice (rejection + success)
        assert mock_validator.validate_scan.call_count == 2


class TestAdvanceAndSync:
    """
    Tests covering the post-main.py transition: advance the shuttle
    to its next stop and push the new state to Firebase so the
    mobile app reflects that the shuttle has left this stop.
    """

    def setup_method(self):
        """
        Reset the test database before each test. Seeds the system_state
        with a current occupancy snapshot so advance_and_sync has
        meaningful values to build the Firebase payload from.
        """
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state")
        # seed an occupancy snapshot as if main.py had just finished
        seed = [
            ("current_stop", "CONAS"),
            ("current_stop_index", "2"),
            ("current_count", "5"),
            ("available_seats", "15"),
        ]
        cursor.executemany(
            "INSERT INTO system_state (key, value) VALUES (?, ?)",
            seed,
        )
        conn.commit()
        conn.close()

    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    def test_advance_and_sync_advances_stop(
        self, mock_counting_class, mock_firebase_class
    ):
        """
        After main.py finishes the boarding scenario, advance_and_sync
        should call CountingLogic.advance_stop() so the shuttle is
        recorded as having moved to the next stop in the loop.
        """
        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "Main Library"
        mock_counting.current_stop_index = 3
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_firebase = MagicMock()
        mock_firebase_class.return_value = mock_firebase

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        mock_counting.initialize.assert_called_once()
        mock_counting.advance_stop.assert_called_once()

    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    def test_advance_and_sync_pushes_to_firebase(
        self, mock_counting_class, mock_firebase_class
    ):
        """
        After advancing, the orchestrator should push a complete
        occupancy payload to Firebase so the mobile app's display
        updates to show the new current_stop and next_stop. This
        prevents users from seeing stale data while the shuttle
        is in transit between stops.

        The payload must match firebase_sync.sync_to_firebase()'s
        expected shape: passenger_count, available_seats,
        occupancy_status, current_stop, next_stop.
        """
        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "Main Library"
        mock_counting.current_stop_index = 3
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_firebase = MagicMock()
        mock_firebase_class.return_value = mock_firebase

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        mock_firebase.initialize.assert_called_once()
        mock_firebase.sync_to_firebase.assert_called_once()

        # inspect the payload that was passed to sync_to_firebase
        call_args = mock_firebase.sync_to_firebase.call_args
        payload = call_args[0][0]
        assert payload["current_stop"] == "Main Library"
        assert payload["next_stop"] == "Africa Hall"
        # occupancy fields are read from SQLite seed
        assert payload["passenger_count"] == 5
        assert payload["available_seats"] == 15

    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    def test_advance_and_sync_wraps_next_stop(
        self, mock_counting_class, mock_firebase_class
    ):
        """
        When the shuttle is on its last stop in the loop, the
        next_stop must wrap back to the first stop (Western Gate).
        Validates that the modulo math in determining next_stop is
        correct so the mobile app shows a sensible 'next stop'
        rather than a stale or invalid value at the loop boundary.
        """
        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "Lumumba Hall"
        mock_counting.current_stop_index = 10  # last in the list
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_firebase = MagicMock()
        mock_firebase_class.return_value = mock_firebase

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        payload = mock_firebase.sync_to_firebase.call_args[0][0]
        assert payload["current_stop"] == "Lumumba Hall"
        assert payload["next_stop"] == "Western Gate"

    @patch("scanner_orchestrator.NoShowCanceller")
    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    def test_advance_and_sync_cancels_no_shows_before_advancing(
        self, mock_counting_class, mock_firebase_class, mock_canceller_class
    ):
        """
        Before advancing the stop, the orchestrator must cancel
        any reserved bookings whose passengers didn't show up to
        scan their QR. This must happen BEFORE advance_stop()
        because we need to know which stop is being LEFT — once
        advance runs, the SQLite current_stop has changed to the
        NEW stop and we'd be cancelling no-shows at the wrong
        pickup point.

        We verify ordering by checking that cancel_no_shows was
        called with the stop name BEFORE advance, and that
        advance_stop was called after.
        """
        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "CONAS"
        mock_counting.current_stop_index = 2
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_canceller = MagicMock()
        mock_canceller.cancel_no_shows.return_value = 0
        mock_canceller_class.return_value = mock_canceller

        mock_firebase = MagicMock()
        mock_firebase_class.return_value = mock_firebase

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        # cancel_no_shows must be called with the stop being LEFT
        # (CONAS, captured from get_current_stop BEFORE advance)
        mock_canceller.cancel_no_shows.assert_called_once_with(stop="CONAS")

        # and advance_stop must have been called too — both happen
        mock_counting.advance_stop.assert_called_once()

    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    @patch("scanner_orchestrator.NoShowCanceller")
    def test_advance_and_sync_writes_arrival_timestamp(
        self, mock_canceller_class, mock_counting_class, mock_firebase_class
    ):
        """
        advance_and_sync should write the current Unix-ms timestamp
        to system_state as 'current_stop_arrived_at_ms'. This is the
        moment the shuttle is conceptually pulling up at the new
        stop, and downstream queries use this timestamp to count
        ONLY bookings completed during this visit (not previous
        visits earlier in the day).
        """
        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "Main Library"
        mock_counting.current_stop_index = 3
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_canceller = MagicMock()
        mock_canceller.cancel_no_shows.return_value = 0
        mock_canceller_class.return_value = mock_canceller

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        # verify a timestamp was written to system_state
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM system_state WHERE key='current_stop_arrived_at_ms'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        # should parse as an integer and be a reasonable Unix-ms value
        timestamp = int(row[0])
        # must be a recent timestamp (positive, post-2024 in ms)
        assert timestamp > 1700000000000
        # and not crazy-far in the future
        assert timestamp < 2000000000000

    @patch("scanner_orchestrator.FirebaseSyncComponent")
    @patch("scanner_orchestrator.CountingLogic")
    @patch("scanner_orchestrator.NoShowCanceller")
    def test_advance_and_sync_writes_arrival_date(
        self, mock_canceller_class, mock_counting_class, mock_firebase_class
    ):
        """
        advance_and_sync should also write the current calendar date
        as 'current_stop_arrived_date' in YYYY-MM-DD format. This
        date is the safety net for the timestamp comparison: if for
        any reason the timestamp doesn't get updated (e.g. shuttle
        restarted mid-day), the date filter still prevents stale
        data from yesterday from contaminating today's counts.
        """
        import datetime

        mock_counting = MagicMock()
        mock_counting.get_current_stop.return_value = "Main Library"
        mock_counting.current_stop_index = 3
        mock_counting.designated_stops_list = [
            "Western Gate", "CEDAT", "CONAS", "Main Library",
            "Africa Hall", "Swimming Pool", "Mitchell Hall",
            "COCIS", "Complex Hall", "CEES", "Lumumba Hall",
        ]
        mock_counting_class.return_value = mock_counting

        mock_canceller = MagicMock()
        mock_canceller.cancel_no_shows.return_value = 0
        mock_canceller_class.return_value = mock_canceller

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.advance_and_sync()

        # verify date was written as YYYY-MM-DD
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM system_state WHERE key='current_stop_arrived_date'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        # must be today's date in YYYY-MM-DD format
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        assert row[0] == today


class TestRunMainLoop:
    """
    Tests covering the orchestrator's full run() loop that ties
    queue scanning, main.py subprocess execution, stop advancement,
    and operator gating together.
    """

    @patch("scanner_orchestrator.db.reference")
    @patch("scanner_orchestrator.subprocess.run")
    @patch.object(ScannerOrchestrator, "advance_and_sync")
    @patch.object(ScannerOrchestrator, "run_scan_queue")
    @patch.object(ScannerOrchestrator, "has_pickups_here")
    @patch.object(ScannerOrchestrator, "should_stop_here")
    @patch.object(ScannerOrchestrator, "read_current_stop")
    @patch("builtins.input")
    def test_run_executes_full_cycle(
        self,
        mock_input,
        mock_read_stop,
        mock_should_stop,
        mock_has_pickups,
        mock_run_queue,
        mock_advance,
        mock_subprocess,
        mock_db_reference,
    ):
        """
        A complete cycle through run() should: read the current
        stop, confirm the stop is worth pausing at, confirm there
        are pickups at this stop, run the scan queue, launch
        main.py and wait for it to finish, advance to the next
        stop, and prompt the operator before looping.

        We force the loop to exit after one full cycle by raising
        KeyboardInterrupt from input() — simulating the operator
        pressing Ctrl+C after the first stop is processed.
        """
        mock_read_stop.return_value = "Western Gate"
        mock_should_stop.return_value = True  # passengers are waiting
        mock_has_pickups.return_value = True  # scanner should open
        mock_run_queue.return_value = 3  # 3 passengers boarded
        mock_input.side_effect = KeyboardInterrupt()

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.run()

        mock_read_stop.assert_called_once()
        mock_run_queue.assert_called_once_with("Western Gate")
        mock_subprocess.assert_called_once()
        # subprocess should be called with python + main.py
        call_args = mock_subprocess.call_args[0][0]
        assert "python" in call_args[0].lower() or call_args[0].endswith("python.exe")
        assert "main.py" in call_args[1]
        mock_advance.assert_called_once()
        mock_input.assert_called_once()

    @patch("scanner_orchestrator.db.reference")
    @patch("scanner_orchestrator.subprocess.run")
    @patch.object(ScannerOrchestrator, "advance_and_sync")
    @patch.object(ScannerOrchestrator, "run_scan_queue")
    @patch.object(ScannerOrchestrator, "has_pickups_here")
    @patch.object(ScannerOrchestrator, "should_stop_here")
    @patch.object(ScannerOrchestrator, "read_current_stop")
    @patch("builtins.input")
    def test_run_loops_through_multiple_stops(
        self,
        mock_input,
        mock_read_stop,
        mock_should_stop,
        mock_has_pickups,
        mock_run_queue,
        mock_advance,
        mock_subprocess,
        mock_db_reference,
    ):
        """
        After the operator presses Enter at the end of a cycle,
        run() should loop back and start a new cycle at the NEW
        current stop. We verify two full cycles execute before
        the loop is terminated by KeyboardInterrupt.
        """
        # each iteration reads a different stop (orchestrator picks
        # up the new value after advance_and_sync wrote it)
        mock_read_stop.side_effect = ["Western Gate", "CEDAT"]
        mock_should_stop.return_value = True  # both stops have activity
        mock_has_pickups.return_value = True  # both have pickups
        mock_run_queue.return_value = 2
        # Enter pressed once, then Ctrl+C the second time
        mock_input.side_effect = ["", KeyboardInterrupt()]

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.run()

        # two full cycles
        assert mock_read_stop.call_count == 2
        assert mock_run_queue.call_count == 2
        assert mock_subprocess.call_count == 2
        assert mock_advance.call_count == 2

    @patch("scanner_orchestrator.db.reference")
    @patch("scanner_orchestrator.subprocess.run")
    @patch.object(ScannerOrchestrator, "advance_and_sync")
    @patch.object(ScannerOrchestrator, "run_scan_queue")
    @patch.object(ScannerOrchestrator, "has_pickups_here")
    @patch.object(ScannerOrchestrator, "should_stop_here")
    @patch.object(ScannerOrchestrator, "read_current_stop")
    @patch("builtins.input")
    @patch("scanner_orchestrator.time.sleep")
    def test_run_skips_empty_stop(
        self,
        mock_sleep,
        mock_input,
        mock_read_stop,
        mock_should_stop,
        mock_has_pickups,
        mock_run_queue,
        mock_advance,
        mock_subprocess,
        mock_db_reference,
    ):
        """
        When should_stop_here returns False, the orchestrator must
        SKIP the scanner queue and the main.py launch, and simply
        advance to the next stop. The shuttle still physically
        visits the stop (advance_and_sync is called) but pauses
        for zero passenger-handling overhead.

        First iteration: empty stop → skip
        Second iteration: passenger waiting → full cycle → operator
        presses Ctrl+C to exit
        """
        # two iterations: first empty stop, second has passengers
        mock_read_stop.side_effect = ["Western Gate", "CEDAT"]
        mock_should_stop.side_effect = [False, True]
        mock_has_pickups.return_value = True  # CEDAT has pickups
        mock_run_queue.return_value = 1
        mock_input.side_effect = KeyboardInterrupt()

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.run()

        # both iterations advanced the shuttle
        assert mock_advance.call_count == 2
        # but the scanner queue and main.py only ran ONCE -- the
        # iteration where someone was actually waiting
        assert mock_run_queue.call_count == 1
        mock_run_queue.assert_called_with("CEDAT")
        assert mock_subprocess.call_count == 1

    @patch("scanner_orchestrator.db.reference")
    @patch("scanner_orchestrator.subprocess.run")
    @patch.object(ScannerOrchestrator, "advance_and_sync")
    @patch.object(ScannerOrchestrator, "run_scan_queue")
    @patch.object(ScannerOrchestrator, "should_stop_here")
    @patch.object(ScannerOrchestrator, "read_current_stop")
    @patch("builtins.input")
    def test_run_handles_keyboard_interrupt_gracefully(
        self,
        mock_input,
        mock_read_stop,
        mock_should_stop,
        mock_run_queue,
        mock_advance,
        mock_subprocess,
        mock_db_reference,
    ):
        """
        Ctrl+C should exit the run loop cleanly rather than
        raising the KeyboardInterrupt to the user. This is what
        the operator uses to shut down the boarding system at
        the end of a service shift.
        """
        mock_read_stop.return_value = "Western Gate"
        mock_should_stop.return_value = True  # passenger waiting
        mock_run_queue.return_value = 0
        mock_input.side_effect = KeyboardInterrupt()

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        # should NOT raise — orchestrator catches the interrupt
        try:
            orchestrator.run()
        except KeyboardInterrupt:
            pytest.fail("run() should catch KeyboardInterrupt internally")

    @patch("scanner_orchestrator.db.reference")
    @patch("scanner_orchestrator.subprocess.run")
    @patch.object(ScannerOrchestrator, "advance_and_sync")
    @patch.object(ScannerOrchestrator, "run_scan_queue")
    @patch.object(ScannerOrchestrator, "has_alightings_here")
    @patch.object(ScannerOrchestrator, "has_pickups_here")
    @patch.object(ScannerOrchestrator, "should_stop_here")
    @patch.object(ScannerOrchestrator, "read_current_stop")
    @patch("builtins.input")
    def test_run_skips_scanner_for_alighting_only_stop(
        self,
        mock_input,
        mock_read_stop,
        mock_should_stop,
        mock_has_pickups,
        mock_has_alightings,
        mock_run_queue,
        mock_advance,
        mock_subprocess,
        mock_db_reference,
    ):
        """
        At an alighting-only stop (passengers want to leave but
        nobody is boarding), the orchestrator must:
          - NOT open the scanner queue
          - STILL launch main.py so the AI counts the alightings
          - advance normally afterwards

        Verifies the new alighting-only branch in run().
        """
        mock_read_stop.return_value = "Main Library"
        mock_should_stop.return_value = True
        mock_has_pickups.return_value = False    # alighting-only stop
        mock_has_alightings.return_value = True  # someone IS alighting here
        mock_input.side_effect = KeyboardInterrupt()

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        orchestrator.run()

        # scanner queue NEVER opened
        mock_run_queue.assert_not_called()
        # main.py still launched for AI counting
        mock_subprocess.assert_called_once()
        # advance still happened
        mock_advance.assert_called_once()


class TestShouldStopHere:
    """
    Tests covering the decision of whether the shuttle should pause
    at a given stop to run the scanner queue, or pass quickly through
    because nobody is waiting.

    The shuttle physically visits every stop on its route (real
    shuttles don't teleport). What this method controls is whether
    we open the scanner queue and run main.py at the stop, or skip
    those costly steps and advance immediately.

    A stop is worth pausing at if EITHER:
      - There are reserved bookings with pickup_stop matching this stop
        (passengers boarding here)
      - There are active bookings with destination_stop matching this stop
        (passengers alighting here)

    When Firebase is unreachable, the method conservatively returns
    True — better to waste a few seconds at an empty stop than to
    skip a stop where a passenger is actually waiting.
    """

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_true_for_reserved_pickup(self, mock_db, mock_admin):
        """
        With a reserved booking whose pickup_stop matches the given
        stop, the shuttle should pause here — there's a passenger
        waiting to board.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is True

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_true_for_active_destination(self, mock_db, mock_admin):
        """
        With an active booking whose destination_stop matches the
        given stop, the shuttle should pause — a passenger onboard
        is expecting to alight here. Without pausing the AI count
        of their alighting and the booking completion sync would
        all be skipped.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "Western Gate",
                "destination_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is True

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_false_when_no_pickups_or_alightings(
        self, mock_db, mock_admin
    ):
        """
        With no reserved bookings at the stop AND no active bookings
        destined here, the shuttle has nothing to do at this stop.
        It still physically passes through, but doesn't pause for
        the scanner queue.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "Main Library",  # not our query stop
                "destination_stop": "CEDAT",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "pickup_stop": "CONAS",  # CONAS but completed, irrelevant
                "destination_stop": "Africa Hall",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_filters_by_shuttle_id(self, mock_db, mock_admin):
        """
        A booking on a DIFFERENT shuttle with this pickup_stop must
        not cause this shuttle to pause. Critical for multi-shuttle
        deployments where shuttles share stops.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b_other": {
                "shuttle_key": "shuttle_002",  # different shuttle
                "status": "reserved",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_true_on_firebase_error(self, mock_db, mock_admin):
        """
        If Firebase is unreachable during the query, default to
        TRUE so the shuttle doesn't accidentally skip a stop where
        a passenger may be waiting. Conservative fallback that
        prefers wasted seconds over missed passengers.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is True

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_false_when_no_bookings_exist(self, mock_db, mock_admin):
        """
        Fresh deployment with zero bookings in Firebase — the method
        returns False cleanly so the shuttle moves smoothly through
        its route without unnecessary pauses.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.should_stop_here("CONAS")

        assert result is False


class TestHasPickupsHere:
    """
    Tests covering the narrower check that distinguishes pickup
    stops from alighting-only stops.

    should_stop_here() returns True for EITHER pickups OR alightings.
    has_pickups_here() returns True ONLY when there is at least one
    reserved booking with pickup_stop == this stop. Used by run()
    to decide whether to open the scanner queue:
      - Pickups present  -> open scanner queue (passengers will scan)
      - Pickups absent   -> skip scanner queue (alighting only, no
                            scanner action needed; AI counts the
                            passengers leaving the shuttle)
    """

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_true_when_reserved_pickup_at_stop(
        self, mock_db, mock_admin
    ):
        """
        A reserved booking with pickup_stop matching this stop
        means a passenger is waiting to scan. Scanner queue must
        open.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is True

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_false_for_alighting_only_stop(
        self, mock_db, mock_admin
    ):
        """
        A stop with active bookings DESTINED here but no reserved
        pickup bookings is an alighting-only stop. The shuttle
        should NOT open the scanner queue here — nobody is going
        to scan. The AI handles the alightings visually.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "Western Gate",
                "destination_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_false_when_no_bookings_match(self, mock_db, mock_admin):
        """
        No reserved pickup at this stop AND no destination match
        either - just returns False. Used in skip-empty-stop case
        but also caller in run() needs the False to detect.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "Main Library",
                "destination_stop": "CEDAT",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_ignores_non_reserved_statuses(self, mock_db, mock_admin):
        """
        Only 'reserved' bookings indicate a pending scan. Active
        bookings have already scanned. Completed and cancelled
        bookings can't scan. Only 'reserved' status counts.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "cancelled",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_filters_by_shuttle_id(self, mock_db, mock_admin):
        """
        Reserved bookings on OTHER shuttles must not trigger this
        shuttle's scanner. Critical for multi-shuttle deployments.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b_other": {
                "shuttle_key": "shuttle_002",
                "status": "reserved",
                "pickup_stop": "CONAS",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is False

    @patch("scanner_orchestrator.firebase_admin")
    @patch("scanner_orchestrator.db")
    def test_returns_true_on_firebase_error(self, mock_db, mock_admin):
        """
        If Firebase fails, default to TRUE so the scanner opens
        and waits. Better to have an idle scanner than to skip a
        waiting passenger because of a network glitch.
        """
        mock_admin._apps = ["existing_app"]
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase unreachable")
        mock_db.reference.return_value = mock_ref

        orchestrator = ScannerOrchestrator(db_path=TEST_DB)
        result = orchestrator.has_pickups_here("CONAS")

        assert result is True
