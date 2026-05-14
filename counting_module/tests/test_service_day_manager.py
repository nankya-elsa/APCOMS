"""
Tests for the ServiceDayManager component.

The ServiceDayManager is responsible for resetting live shuttle
state to a fresh-day baseline at the start of each service day
(default 06:00 daily, configurable via day_start_time setting).

Live state that gets reset:
  - current_count        -> 0 (shuttle starts empty)
  - available_seats      -> total_capacity (all seats available)
  - current_stop_index   -> 0 (first stop in the route)
  - current_stop         -> first stop name (kept in sync with index)
  - system_status        -> Active (fresh service day)
  - camera_status        -> unknown (main.py will set 'ok' on startup)
  - current_fps          -> 0 (fresh metrics)
  - current_latency      -> 0 (fresh metrics)
  - last_reset_date      -> today's date (marker)

What is NEVER touched:
  - passenger_events table (historical record, panel-facing analytics)
  - diagnostic_logs table (forensic record)
  - pending_cancellations queue (drains naturally)
  - Configuration keys: total_capacity, designated_stops,
    shuttle_id, day_start_time, day_end_time

The manager is IDEMPOTENT — once a reset has occurred for a given
service day, subsequent calls are no-ops. This lets us safely call
it from multiple places (dashboard render, main.py startup,
orchestrator startup) without risk of double-reset.

All SQLite interactions use an injectable db_path so tests can
verify behaviour without polluting production state.
"""

import os
import sys
import sqlite3
import datetime
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from service_day_manager import ServiceDayManager

TEST_DB = "local_database/test_apcoms.db"


def _seed_state(db_path, **kwargs):
    """
    Helper to seed system_state with arbitrary key/value pairs
    in a single connection. Used by tests to set up the state
    snapshot the manager will read from.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    for k, v in kwargs.items():
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            (k, str(v)),
        )
    conn.commit()
    conn.close()


def _read_state(db_path, key):
    """Helper to read a single system_state value for assertions."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_state WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


class TestServiceDayManagerInitialization:
    """Tests covering ServiceDayManager construction."""

    def setup_method(self):
        """Clean the test database before each test."""
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    def test_manager_initializes_with_defaults(self):
        """
        ServiceDayManager should instantiate without arguments and
        be ready to use. No connections are opened at construction
        time so the class can be created freely in tests.
        """
        manager = ServiceDayManager()
        assert manager is not None
        assert hasattr(manager, "db_path")

    def test_manager_accepts_explicit_db_path(self):
        """
        Tests need to override the SQLite path to avoid polluting
        production state. Both the test database and any future
        deployment-specific path should be acceptable.
        """
        manager = ServiceDayManager(db_path=TEST_DB)
        assert manager.db_path == TEST_DB

    def test_manager_defaults_to_production_db_path(self):
        """
        Without an override, the manager points at the production
        SQLite database the rest of the counting module uses. This
        keeps a default that 'just works' when called from main.py
        or the dashboard without explicit configuration.
        """
        manager = ServiceDayManager()
        assert manager.db_path == "local_database/apcoms.db"


class TestShouldReset:
    """
    Tests covering the decision of whether a reset is needed right
    now. The decision depends on three inputs:

      1. The current datetime (controlled in tests via mock)
      2. day_start_time from system_state (default 06:00)
      3. last_reset_date from system_state

    The rule: a reset is needed if the most-recent service start
    (today's day_start if we're past it, otherwise yesterday's)
    hasn't yet been marked as reset in last_reset_date.
    """

    def setup_method(self):
        """Clean the test database before each test."""
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    @patch("service_day_manager.datetime")
    def test_reset_needed_when_past_todays_start_and_no_prior_reset(
        self, mock_dt
    ):
        """
        Time is 08:00 today, day_start_time is 06:00, and we've
        never reset (no last_reset_date in DB). The manager should
        say YES, reset needed — and the target date is today.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(TEST_DB, day_start_time="06:00")

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        assert needed is True
        assert target_date == "2026-05-14"

    @patch("service_day_manager.datetime")
    def test_reset_not_needed_when_already_reset_today(self, mock_dt):
        """
        Time is 08:00 today, day_start_time is 06:00, and we
        already reset earlier today. The manager should say NO,
        the reset for today has been done.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            day_start_time="06:00",
            last_reset_date="2026-05-14",
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        assert needed is False
        # target_date still returned as today's expected reset date
        # so callers can log it if they want
        assert target_date == "2026-05-14"

    @patch("service_day_manager.datetime")
    def test_reset_needed_when_last_reset_was_yesterday(self, mock_dt):
        """
        Time is 08:00 today. We last reset yesterday morning. Today's
        service has started (it's past 06:00) so a fresh reset for
        today is needed.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            day_start_time="06:00",
            last_reset_date="2026-05-13",
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        assert needed is True
        assert target_date == "2026-05-14"

    @patch("service_day_manager.datetime")
    def test_before_start_time_targets_yesterday(self, mock_dt):
        """
        Time is 03:00 today (before today's 06:00 service start).
        From the system's perspective the most-recent service day
        is yesterday — so the reset that should have happened is
        yesterday's. If we haven't recorded that, reset is needed.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 3, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            day_start_time="06:00",
            last_reset_date="2026-05-12",
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        assert needed is True
        # we expected a reset YESTERDAY morning; mark for that day
        assert target_date == "2026-05-13"

    @patch("service_day_manager.datetime")
    def test_default_day_start_when_setting_missing(self, mock_dt):
        """
        When day_start_time is not in system_state, the manager
        falls back to 06:00 by default. This keeps a fresh
        deployment working without requiring explicit configuration.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        # NOTE: no day_start_time seeded -- manager should use default 06:00
        _seed_state(TEST_DB)

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        # with default 06:00 and 'now' at 08:00, today's start has
        # passed; with no last_reset_date, a reset is needed
        assert needed is True
        assert target_date == "2026-05-14"

    @patch("service_day_manager.datetime")
    def test_at_exactly_start_time_triggers_reset(self, mock_dt):
        """
        At 06:00:00 exactly (matching day_start_time), the reset
        for today is considered due. Using >= for the boundary
        check avoids the edge case where a 06:00:00 dashboard load
        would mistakenly target yesterday.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 6, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(TEST_DB, day_start_time="06:00")

        manager = ServiceDayManager(db_path=TEST_DB)
        needed, target_date = manager.should_reset()

        assert needed is True
        assert target_date == "2026-05-14"


class TestPerformReset:
    """
    Tests covering the actual reset writes against SQLite.

    The reset clears live state to fresh-day baseline:
      - current_count -> 0
      - available_seats -> total_capacity (read from config)
      - current_stop_index -> 0
      - current_stop -> first designated stop name
      - system_status -> Active
      - camera_status -> unknown
      - current_fps -> 0
      - current_latency -> 0
      - last_reset_date -> the supplied target_date

    Critically, the reset must NOT touch:
      - passenger_events table (historical record)
      - diagnostic_logs table (forensic record)
      - Configuration keys: total_capacity, designated_stops,
        shuttle_id, day_start_time, day_end_time

    These tests verify both halves: what changes AND what stays.
    """

    def setup_method(self):
        """Clean the test database and seed a baseline of stale state."""
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        cursor.execute("DROP TABLE IF EXISTS passenger_events")
        cursor.execute("DROP TABLE IF EXISTS diagnostic_logs")
        conn.commit()
        conn.close()

    def test_reset_writes_fresh_live_state(self):
        """
        After perform_reset, all live state keys reflect a clean
        service-day start. We seed stale values to prove every
        single key gets overwritten.
        """
        _seed_state(
            TEST_DB,
            # stale live state to be overwritten
            current_count="20",
            available_seats="0",
            current_stop_index="7",
            current_stop="COCIS",
            system_status="Error",
            camera_status="error",
            current_fps="0",
            current_latency="999",
            # config must remain untouched
            total_capacity="20",
            designated_stops='["Western Gate", "CEDAT", "CONAS"]',
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        # live state reset to fresh-day baseline
        assert _read_state(TEST_DB, "current_count") == "0"
        assert _read_state(TEST_DB, "available_seats") == "20"
        assert _read_state(TEST_DB, "current_stop_index") == "0"
        assert _read_state(TEST_DB, "current_stop") == "Western Gate"
        assert _read_state(TEST_DB, "system_status") == "Active"
        assert _read_state(TEST_DB, "camera_status") == "unknown"
        assert _read_state(TEST_DB, "current_fps") == "0"
        assert _read_state(TEST_DB, "current_latency") == "0"
        assert _read_state(TEST_DB, "last_reset_date") == "2026-05-14"

    def test_reset_preserves_config_keys(self):
        """
        Configuration keys must NEVER be touched by reset. We seed
        each one and confirm they're unchanged after a reset.
        """
        _seed_state(
            TEST_DB,
            total_capacity="25",
            designated_stops='["Stop1", "Stop2", "Stop3"]',
            shuttle_id="shuttle_007",
            day_start_time="07:30",
            day_end_time="22:00",
            current_count="15",  # stale live state to trigger overwrite path
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        # every config key is preserved verbatim
        assert _read_state(TEST_DB, "total_capacity") == "25"
        assert (
            _read_state(TEST_DB, "designated_stops")
            == '["Stop1", "Stop2", "Stop3"]'
        )
        assert _read_state(TEST_DB, "shuttle_id") == "shuttle_007"
        assert _read_state(TEST_DB, "day_start_time") == "07:30"
        assert _read_state(TEST_DB, "day_end_time") == "22:00"

    def test_reset_uses_first_designated_stop_for_current_stop(self):
        """
        current_stop (the name) is set from the FIRST entry in the
        designated_stops list, kept in sync with current_stop_index=0.
        This fixes the old bug where index and name could drift.
        """
        _seed_state(
            TEST_DB,
            designated_stops='["Main Library", "CEDAT", "CONAS"]',
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        assert _read_state(TEST_DB, "current_stop_index") == "0"
        assert _read_state(TEST_DB, "current_stop") == "Main Library"

    def test_reset_falls_back_to_default_capacity_when_missing(self):
        """
        If total_capacity isn't set in system_state, the manager
        falls back to a sensible default (20). Keeps fresh
        deployments working without explicit configuration.
        """
        _seed_state(TEST_DB)  # nothing seeded

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        assert _read_state(TEST_DB, "available_seats") == "20"

    def test_reset_falls_back_to_default_first_stop_when_no_stops(self):
        """
        If designated_stops isn't set, current_stop falls back to
        'Western Gate' (the campus shuttle's first stop in the
        default route). Better than leaving current_stop blank.
        """
        _seed_state(TEST_DB)  # no designated_stops

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        assert _read_state(TEST_DB, "current_stop") == "Western Gate"

    def test_reset_does_not_touch_passenger_events(self):
        """
        The historical passenger_events table must survive reset
        untouched. Analytics depend on this data accumulating
        across many service days. We seed a row and confirm it
        remains.
        """
        # set up passenger_events with a known row
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE passenger_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shuttle_id TEXT,
                timestamp DATETIME,
                direction TEXT,
                passenger_count INTEGER,
                available_seats INTEGER,
                stop_location TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO passenger_events
                (shuttle_id, timestamp, direction, passenger_count,
                 available_seats, stop_location)
            VALUES ('shuttle_001', '2026-05-13 10:00:00', 'boarding',
                    5, 15, 'CONAS')
        """)
        conn.commit()
        conn.close()

        _seed_state(TEST_DB)  # also create system_state

        manager = ServiceDayManager(db_path=TEST_DB)
        manager.perform_reset(target_date="2026-05-14")

        # passenger_events row survives
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passenger_events")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1


class TestResetIfNeeded:
    """
    Tests covering the public reset_if_needed() method that
    combines should_reset (the decision) with perform_reset (the
    action). This is what callers actually invoke — they don't
    need to know about the two-phase internals.

    The method is idempotent: if no reset is needed, it returns
    cleanly without writing anything. If a reset IS needed, it
    performs the reset and returns the date that was reset.
    """

    def setup_method(self):
        """Clean test database before each test."""
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    @patch("service_day_manager.datetime")
    def test_resets_when_needed(self, mock_dt):
        """
        With no prior last_reset_date and 'now' past today's
        service start, reset_if_needed should perform the full
        reset and return the date that was reset.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            current_count="15",
            day_start_time="06:00",
            total_capacity="20",
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        result = manager.reset_if_needed()

        # reset actually happened
        assert result == "2026-05-14"
        assert _read_state(TEST_DB, "current_count") == "0"
        assert _read_state(TEST_DB, "last_reset_date") == "2026-05-14"

    @patch("service_day_manager.datetime")
    def test_no_op_when_already_reset_today(self, mock_dt):
        """
        If today's reset has already been performed (as recorded
        in last_reset_date), reset_if_needed must NOT overwrite
        any state. Stale values left after legitimate service-day
        progress (e.g. count=15, current_stop=CONAS) must survive
        untouched.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 10, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            current_count="15",
            current_stop="CONAS",
            day_start_time="06:00",
            last_reset_date="2026-05-14",  # today already reset
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        result = manager.reset_if_needed()

        # returns None to signal "no work done"
        assert result is None
        # live state is UNCHANGED -- service day in progress
        assert _read_state(TEST_DB, "current_count") == "15"
        assert _read_state(TEST_DB, "current_stop") == "CONAS"

    @patch("service_day_manager.datetime")
    def test_multiple_calls_only_reset_once(self, mock_dt):
        """
        Idempotency: calling reset_if_needed three times in
        succession should perform exactly ONE reset. After the
        first call marks last_reset_date, subsequent calls find
        the reset already done and become no-ops. Critical for
        safely calling the manager from multiple components
        (dashboard, main.py, orchestrator) without coordination.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 8, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            current_count="10",
            day_start_time="06:00",
        )

        manager = ServiceDayManager(db_path=TEST_DB)

        # first call performs the reset
        result1 = manager.reset_if_needed()
        assert result1 == "2026-05-14"

        # subsequent calls become no-ops
        result2 = manager.reset_if_needed()
        result3 = manager.reset_if_needed()
        assert result2 is None
        assert result3 is None

        # state matches the reset baseline once and stays there
        assert _read_state(TEST_DB, "current_count") == "0"

    @patch("service_day_manager.datetime")
    def test_resets_yesterday_when_called_before_todays_start(
        self, mock_dt
    ):
        """
        Called at 03:00 (before today's 06:00 service start) with
        last_reset_date older than yesterday: the reset should
        target YESTERDAY's date, not today's. Yesterday's morning
        was the most-recent service start that should have
        triggered a reset.
        """
        mock_dt.datetime.now.return_value = datetime.datetime(
            2026, 5, 14, 3, 0
        )
        mock_dt.datetime.strptime = datetime.datetime.strptime
        mock_dt.timedelta = datetime.timedelta

        _seed_state(
            TEST_DB,
            current_count="20",
            day_start_time="06:00",
            last_reset_date="2026-05-12",
        )

        manager = ServiceDayManager(db_path=TEST_DB)
        result = manager.reset_if_needed()

        assert result == "2026-05-13"
        assert _read_state(TEST_DB, "last_reset_date") == "2026-05-13"
        assert _read_state(TEST_DB, "current_count") == "0"
