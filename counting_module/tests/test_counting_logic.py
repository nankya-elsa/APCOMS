import pytest
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from counting_logic import CountingLogic

TEST_DB = "local_database/test_apcoms.db"


class TestCountingLogicInitialization:

    def test_counting_logic_initializes_with_correct_total_capacity(self):
        """
        Test that CountingLogic initializes with the correct total capacity
        so the system knows the maximum number of passengers the shuttle
        can carry at any given time
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        assert counter.total_capacity == 20

    def test_passenger_count_reads_from_sqlite_on_startup(self):
        """
        Test that CountingLogic reads the last passenger count from
        SQLite on startup so counting continues from where it left off
        instead of always starting from zero
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()
        assert counter.passenger_count >= 0

    def test_available_seats_calculated_correctly_on_startup(self):
        """
        Test that available seats are correctly calculated from total
        capacity minus current passenger count on startup so the system
        always shows accurate seat availability
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()
        assert counter.available_seats == counter.total_capacity - counter.passenger_count

    def test_virtual_entry_zone_is_defined(self):
        """
        Test that virtual entry zone is defined on initialization so
        the system can determine when a passenger is boarding by
        detecting movement through the upper half of the camera frame
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        assert counter.virtual_entry_zone is not None

    def test_virtual_exit_zone_is_defined(self):
        """
        Test that virtual exit zone is defined on initialization so
        the system can determine when a passenger is alighting by
        detecting movement through the lower half of the camera frame
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        assert counter.virtual_exit_zone is not None

    def test_stops_list_is_loaded(self):
        """
        Test that designated stops list is loaded on initialization so
        the system knows all the shuttle stops along the predefined
        campus route for location tracking
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        assert counter.designated_stops_list is not None
        assert len(counter.designated_stops_list) > 0

    def test_current_stop_index_starts_at_zero(self):
        """
        Test that current stop index starts at 0 on initialization so
        the shuttle always begins its route from the first designated
        stop which is the Main Gate
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        assert counter.current_stop_index == 0

    def test_reads_total_capacity_from_sqlite_if_available(self):
        """
        Test that CountingLogic reads total_capacity from SQLite
        system_state table if it exists so fleet managers can update
        shuttle capacity via Flask Dashboard without changing code
        """
        import sqlite3
        import os
        os.environ.pop("TOTAL_CAPACITY", None)
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO system_state (key, value)
            VALUES ('total_capacity', '15')
        """)
        conn.commit()
        conn.close()

        logic = CountingLogic(db_path=TEST_DB)
        assert logic.total_capacity == 15

    def test_reads_stops_from_sqlite_if_available(self):
        """
        Test that CountingLogic reads designated_stops from SQLite
        system_state table if it exists so fleet managers can update
        shuttle stops via Flask Dashboard without changing code
        """
        import sqlite3
        import json
        import os
        os.environ.pop("DESIGNATED_STOPS", None)
        os.makedirs("local_database", exist_ok=True)
        stops = ["Stop A", "Stop B", "Stop C"]
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO system_state (key, value)
            VALUES ('designated_stops', ?)
        """, (json.dumps(stops),))
        conn.commit()
        conn.close()

        logic = CountingLogic(db_path=TEST_DB)
        assert logic.designated_stops_list == stops

    def test_falls_back_to_default_capacity_if_not_in_sqlite(self):
        """
        Test that CountingLogic falls back to default capacity of 20
        when system_state table has no capacity entry so the system
        works correctly on first deployment before setup_shuttle() runs
        """
        import sqlite3
        import os
        os.environ.pop("DESIGNATED_STOPS", None)
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state WHERE key='total_capacity'")
        conn.commit()
        conn.close()

        logic = CountingLogic(db_path=TEST_DB)
        assert logic.total_capacity == 20

    def test_falls_back_to_default_stops_if_not_in_sqlite(self):
        """
        Test that CountingLogic falls back to hardcoded stops list
        when system_state table has no stops entry so the system
        works correctly on first deployment before setup_shuttle() runs
        """
        import sqlite3
        import os
        os.environ.pop("DESIGNATED_STOPS", None)
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state WHERE key='designated_stops'")
        conn.commit()
        conn.close()

        logic = CountingLogic(db_path=TEST_DB)
        assert len(logic.designated_stops_list) > 0

    @patch.dict(os.environ, {"DESIGNATED_STOPS": "Stop A, Stop B, Stop C"}, clear=False)
    def test_uses_env_designated_stops_when_available(self):
        """
        Test that designated stops are loaded from the environment
        first so route changes can be made without editing code.
        """
        logic = CountingLogic(db_path=TEST_DB)
        assert logic.designated_stops_list == ["Stop A", "Stop B", "Stop C"]

    @patch.dict(os.environ, {"TOTAL_CAPACITY": "25"}, clear=False)
    def test_uses_env_total_capacity_when_available(self):
        """
        Test that total capacity is loaded from the environment first
        so deployment owners can change shuttle size without editing code.
        """
        logic = CountingLogic(db_path=TEST_DB)
        assert logic.total_capacity == 25

    @patch.dict(os.environ, {"DESIGNATED_STOPS": "Stop A, Stop B, Stop C"}, clear=False)
    def test_clamps_stale_stop_index_when_route_shortens(self):
        """
        Test that a persisted current_stop_index larger than the new
        route length is safely reset so the system does not crash.
        """
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO system_state (key, value)
            VALUES ('current_stop_index', '99')
        """)
        conn.commit()
        conn.close()

        logic = CountingLogic(db_path=TEST_DB)
        logic.initialize()

        assert logic.current_stop_index == 0
        assert logic.get_current_stop() == "Stop A"


class TestDirectionDetermination:

    def test_returns_boarding_when_moving_inward(self):
        """
        Test that determine_direction() returns boarding when a person
        moves from the upper half to the lower half of the camera frame
        confirming they are entering the shuttle
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)

        track = {
            "track_id": 1,
            "previous_centroid": (960, 200),  # upper half - outside
            "current_centroid": (960, 700)    # lower half - inside
        }

        direction = counter.determine_direction(track)
        assert direction == "boarding"

    def test_returns_alighting_when_moving_outward(self):
        """
        Test that determine_direction() returns alighting when a person
        moves from the lower half to the upper half of the camera frame
        confirming they are exiting the shuttle
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)

        track = {
            "track_id": 1,
            "previous_centroid": (960, 700),  # lower half - inside
            "current_centroid": (960, 200)    # upper half - outside
        }

        direction = counter.determine_direction(track)
        assert direction == "alighting"

    def test_returns_undetermined_when_movement_unclear(self):
        """
        Test that determine_direction() returns undetermined when a person
        stays in the same zone so the system ignores unclear movements
        and does not incorrectly increment or decrement the count
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)

        track = {
            "track_id": 1,
            "previous_centroid": (960, 200),  # upper half
            "current_centroid": (960, 300)    # still upper half
        }

        direction = counter.determine_direction(track)
        assert direction == "undetermined"

    def test_handles_none_track_gracefully(self):
        """
        Test that determine_direction() handles None track gracefully
        to prevent the system from crashing when invalid data is
        received from the Object Tracking Component
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        direction = counter.determine_direction(None)
        assert direction == "undetermined"

    @patch.dict(os.environ, {"TOTAL_CAPACITY": "25"})
    def test_total_capacity_falls_back_to_env_when_none_provided(self):
        """
        When the caller does NOT pass total_capacity, CountingLogic
        should read it from the TOTAL_CAPACITY environment variable.
        This matches the .env-driven deployment model: SHUTTLE_ID,
        TOTAL_CAPACITY, DESIGNATED_STOPS etc. are all set per
        deployment via .env rather than via the admin dashboard.
        """
        counter = CountingLogic(db_path=TEST_DB)
        assert counter.total_capacity == 25

    def test_total_capacity_defaults_to_20_when_env_not_set(self):
        """
        With neither a caller-provided total_capacity nor a
        TOTAL_CAPACITY environment variable, fall back to the
        hardcoded default of 20 seats.
        """
        with patch.dict(os.environ, {}, clear=True):
            counter = CountingLogic(db_path=TEST_DB)
            assert counter.total_capacity == 20


class TestCountUpdating:

    def test_increments_passenger_count_on_boarding(self):
        """
        Test that update_count() increments passenger count by 1 when
        a person boards the shuttle to maintain accurate real-time
        occupancy tracking as required by FR-CM-3.3
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()
        initial_count = counter.passenger_count

        track = {
            "track_id": 1,
            "previous_centroid": (960, 200),  # upper half - outside
            "current_centroid": (960, 700)    # lower half - inside
        }

        counter.update_count(track)
        assert counter.passenger_count == initial_count + 1

    def test_decrements_passenger_count_on_alighting(self):
        """
        Test that update_count() decrements passenger count by 1 when
        a person alights the shuttle to maintain accurate real-time
        occupancy tracking as required by FR-CM-3.4
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()

        board_track = {
            "track_id": 1,
            "previous_centroid": (960, 200),
            "current_centroid": (960, 700)
        }
        counter.update_count(board_track)
        count_after_boarding = counter.passenger_count

        alight_track = {
            "track_id": 2,
            "previous_centroid": (960, 700),  # lower half - inside
            "current_centroid": (960, 200)    # upper half - outside
        }
        counter.update_count(alight_track)
        assert counter.passenger_count == count_after_boarding - 1

    def test_prevents_double_counting_same_track_id(self):
        """
        Test that update_count() prevents the same track ID from being
        counted twice to ensure each passenger is counted exactly once
        per boarding or alighting event as required by FR-CM-3.5
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()
        initial_count = counter.passenger_count

        track = {
            "track_id": 1,
            "previous_centroid": (960, 200),
            "current_centroid": (960, 700)
        }

        counter.update_count(track)
        counter.update_count(track)

        assert counter.passenger_count == initial_count + 1

    def test_does_not_exceed_total_capacity_on_boarding(self):
        """
        Test that update_count() does not increment passenger count
        beyond total capacity to prevent the shuttle from being
        marked as having more passengers than it can physically carry
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.initialize()

        for i in range(20):
            track = {
                "track_id": i,
                "previous_centroid": (960, 200),
                "current_centroid": (960, 700)
            }
            counter.update_count(track)

        extra_track = {
            "track_id": 99,
            "previous_centroid": (960, 200),
            "current_centroid": (960, 700)
        }
        counter.update_count(extra_track)

        assert counter.passenger_count <= counter.total_capacity

    def test_does_not_go_below_zero_on_alighting(self):
        """
        Test that update_count() does not decrement passenger count
        below zero to prevent negative occupancy values which would
        indicate a system error in the counting logic
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 0
        counter.available_seats = 20

        track = {
            "track_id": 1,
            "previous_centroid": (960, 700),  # lower half - inside
            "current_centroid": (960, 200)    # upper half - outside
        }

        counter.update_count(track)
        assert counter.passenger_count >= 0

    def test_logs_warning_when_shuttle_at_full_capacity(self, caplog):
        """
        Test that update_count() logs a warning when shuttle is full
        to alert the System Monitor that no more passengers can board
        as required by the pseudocode
        """
        import logging
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 20
        counter.available_seats = 0

        track = {
            "track_id": 99,
            "previous_centroid": (960, 200),
            "current_centroid": (960, 700)
        }

        with caplog.at_level(logging.WARNING):
            counter.update_count(track)
        # message updated to be clearer about what the situation means
        assert "Illegal boarding attempt" in caplog.text
        assert "full capacity" in caplog.text

    def test_logs_warning_when_count_already_at_zero(self, caplog):
        """
        Test that update_count() logs a warning when passenger count
        is already at zero to alert the System Monitor of a potential
        counting error or invalid alighting event
        """
        import logging
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 0
        counter.available_seats = 20

        track = {
            "track_id": 1,
            "previous_centroid": (960, 700),
            "current_centroid": (960, 200)
        }

        with caplog.at_level(logging.WARNING):
            counter.update_count(track)
        # message updated to label this as a "ghost" detection
        assert "Ghost alighting" in caplog.text
        assert "already at zero" in caplog.text


class TestOccupancyCalculation:

    def test_returns_available_when_seats_greater_than_5(self):
        """
        Test that calculate_occupancy() returns Available when more
        than 5 seats are free so students know they can comfortably
        board the shuttle without rushing
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 10
        counter.available_seats = 10
        occupancy = counter.calculate_occupancy()
        assert occupancy["occupancy_status"] == "Available"

    def test_returns_nearly_full_when_seats_between_1_and_5(self):
        """
        Test that calculate_occupancy() returns Nearly Full when 1 to
        5 seats are available so students know the shuttle is filling
        up and they should hurry to the stop
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 17
        counter.available_seats = 3
        occupancy = counter.calculate_occupancy()
        assert occupancy["occupancy_status"] == "Nearly Full"

    def test_returns_full_when_no_seats_available(self):
        """
        Test that calculate_occupancy() returns Full when no seats
        are available so students know not to go to the shuttle stop
        and seek alternative transportation instead
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 20
        counter.available_seats = 0
        occupancy = counter.calculate_occupancy()
        assert occupancy["occupancy_status"] == "Full"


class TestStopManagement:

    def test_get_current_stop_returns_correct_stop(self):
        """
        Test that get_current_stop() returns the correct current stop
        from the designated stops list so the mobile app and Firebase
        can display accurate shuttle location to students
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.current_stop_index = 0
        current_stop = counter.get_current_stop()
        assert current_stop == counter.designated_stops_list[0]

    def test_advance_stop_moves_to_next_stop(self):
        """
        Test that advance_stop() moves to the next stop in the
        designated stops list to simulate the shuttle progressing
        along its predefined campus route
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.current_stop_index = 0
        first_stop = counter.get_current_stop()
        counter.advance_stop()
        second_stop = counter.get_current_stop()
        assert second_stop == counter.designated_stops_list[1]
        assert second_stop != first_stop

    def test_advance_stop_wraps_around_after_last_stop(self):
        """
        Test that advance_stop() wraps around to the first stop after
        the last stop to simulate the shuttle completing its full
        campus route loop and starting again from the beginning
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.current_stop_index = len(counter.designated_stops_list) - 1
        counter.advance_stop()
        assert counter.current_stop_index == 0


class TestCountReset:

    def test_reset_count_sets_passenger_count_to_zero(self):
        """
        Test that reset_count() sets passenger count back to zero
        so the system can start a fresh count when called by an
        administrator via the Flask dashboard at end of day
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.passenger_count = 15
        counter.reset_count()
        assert counter.passenger_count == 0

    def test_reset_count_restores_available_seats(self):
        """
        Test that reset_count() restores available seats back to total
        capacity so the system correctly reflects an empty shuttle
        after a reset is performed by the administrator
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.available_seats = 5
        counter.reset_count()
        assert counter.available_seats == counter.total_capacity

    def test_reset_count_clears_counted_tracks(self):
        """
        Test that reset_count() clears the counted tracks list so
        previously counted track IDs don't prevent new passengers
        from being counted after a reset is performed
        """
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        counter.counted_tracks = [1, 2, 3, 4, 5]
        counter.reset_count()
        assert counter.counted_tracks == []

    def test_reset_count_logs_reset_message(self, caplog):
        """
        Test that reset_count() logs a reset message with timestamp
        so the System Monitor has an audit trail of when resets
        were performed and by whom
        """
        import logging
        counter = CountingLogic(total_capacity=20, db_path=TEST_DB)
        with caplog.at_level(logging.INFO):
            counter.reset_count()
        assert "Passenger count reset at:" in caplog.text


class TestIllegalBoardingAlert:
    """
    Tests covering the diagnostic alert raised when the AI detects
    a boarding while the shuttle is already at capacity.

    The alert exists because at full capacity, no legitimate
    passenger should be boarding (the booking system would have
    refused their reservation). An AI-detected boarding under
    these conditions represents either:
      - A safety risk (someone forcing their way onto a full shuttle)
      - An AI false positive (luggage, reflections, etc.)

    Either way, the operator needs to know. The system:
      1. Does NOT increment passenger_count (capacity stays correct)
      2. Does NOT log a row to passenger_events (analytics stays clean)
      3. DOES log a diagnostic entry so the dashboard surfaces it
      4. DOES add the track_id to counted_tracks so the same person
         doesn't re-trigger the alert on every subsequent frame
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        """Clean test database state before each test."""
        import sqlite3
        import os
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    def _boarding_track(self, track_id):
        """
        Build a track dict shaped like determine_direction() expects.
        previous_centroid above midpoint (540) and current_centroid
        below midpoint = boarding direction.
        """
        return {
            "track_id": track_id,
            "previous_centroid": [400, 200],
            "current_centroid": [400, 800],
        }

    def test_alert_raised_when_boarding_at_capacity(self):
        """
        When a boarding track is processed while passenger_count
        is already at total_capacity, the DataLogger receives a
        log_diagnostic call with severity 'error'.
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = counting.total_capacity
        counting.available_seats = 0

        counting.update_count(self._boarding_track("track_illegal_1"))

        mock_logger.log_diagnostic.assert_called_once()
        # log_diagnostic takes a single dict argument
        passed_dict = mock_logger.log_diagnostic.call_args.args[0]
        assert passed_dict["log_type"] == "error"

    def test_passenger_count_unchanged_when_at_capacity(self):
        """
        At capacity, the boarding does NOT bump the live count.
        passenger_count stays at total_capacity. Preserves the
        existing safety guard.
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = counting.total_capacity
        counting.available_seats = 0

        counting.update_count(self._boarding_track("track_illegal_2"))

        assert counting.passenger_count == counting.total_capacity
        assert counting.available_seats == 0

    def test_track_id_marked_as_counted_to_prevent_spam(self):
        """
        Even though the boarding wasn't counted toward occupancy,
        the track_id must be added to counted_tracks. Otherwise the
        same person appearing in every frame would trigger the alert
        AGAIN every frame, flooding the diagnostic logs and dashboard.
        The alert should fire ONCE per illegal attempt.
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = counting.total_capacity
        counting.available_seats = 0

        track = self._boarding_track("track_illegal_3")
        counting.update_count(track)
        counting.update_count(track)  # same person, next frame

        assert mock_logger.log_diagnostic.call_count == 1
        assert "track_illegal_3" in counting.counted_tracks

    def test_no_alert_when_data_logger_is_none(self):
        """
        data_logger is an optional dependency. When None (the case
        for older tests and certain isolated usages), update_count
        still suppresses the boarding correctly but skips alerting
        rather than crashing. This keeps all existing tests passing.
        """
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=None)
        counting.initialize()
        counting.passenger_count = counting.total_capacity
        counting.available_seats = 0

        counting.update_count(self._boarding_track("track_no_logger"))

        assert counting.passenger_count == counting.total_capacity
        assert "track_no_logger" in counting.counted_tracks


class TestGhostAlightingAlert:
    """
    Tests covering the diagnostic warning raised when the AI detects
    an alighting while passenger_count is already at zero. This is
    almost always an AI false positive (camera saw a shadow, a
    reflection, or motion that looked like a person exiting an
    empty shuttle). Worth surfacing for diagnostics but lower
    severity than the illegal-boarding case.

    Same protective behaviour as the illegal-boarding alert:
      1. Count stays at zero (no negative count corruption)
      2. No passenger_event row written
      3. Diagnostic logged with severity 'warning' (not 'error')
      4. track_id marked as counted to prevent spam
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        """Clean test database state before each test."""
        import sqlite3
        import os
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    def _alighting_track(self, track_id):
        """
        Build a track dict that represents an alighting direction.
        previous_centroid below midpoint, current_centroid above
        midpoint = exit motion.
        """
        return {
            "track_id": track_id,
            "previous_centroid": [400, 800],
            "current_centroid": [400, 200],
        }

    def test_warning_raised_when_alighting_at_zero_count(self):
        """
        With passenger_count=0, an alighting detection should fire
        a diagnostic with severity 'warning' (less severe than the
        illegal-boarding 'error' because it's almost always an AI
        false positive).
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = 0

        counting.update_count(self._alighting_track("ghost_1"))

        mock_logger.log_diagnostic.assert_called_once()
        # log_diagnostic takes a single dict argument
        passed_dict = mock_logger.log_diagnostic.call_args.args[0]
        assert passed_dict["log_type"] == "warning"

    def test_count_never_goes_negative(self):
        """
        passenger_count must never drop below zero. The existing
        safety guard is preserved — we're adding alerting on top of
        it, not changing it.
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = 0

        counting.update_count(self._alighting_track("ghost_2"))

        assert counting.passenger_count == 0

    def test_ghost_alighting_marked_counted(self):
        """
        Same anti-spam protection as the illegal-boarding case —
        track_id added to counted_tracks so we don't re-fire the
        warning every frame for the same false positive.
        """
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=mock_logger)
        counting.initialize()
        counting.passenger_count = 0

        track = self._alighting_track("ghost_3")
        counting.update_count(track)
        counting.update_count(track)

        assert mock_logger.log_diagnostic.call_count == 1
        assert "ghost_3" in counting.counted_tracks

    def test_no_warning_when_data_logger_is_none(self):
        """
        Same graceful degradation as illegal-boarding: with no
        data_logger, the count guard still works, no warning fires,
        no crash.
        """
        counting = CountingLogic(db_path=self.TEST_DB, data_logger=None)
        counting.initialize()
        counting.passenger_count = 0

        counting.update_count(self._alighting_track("ghost_no_logger"))

        assert counting.passenger_count == 0
        assert "ghost_no_logger" in counting.counted_tracks


class TestBookingHoldsSeats:
    """
    Tests covering the new soft-hold reservation model where
    available_seats is an independently stored field that is
    decremented at booking time (not at scan time) and incremented
    on cancellation, no-show, or alighting.

    The key insight: available_seats and passenger_count are now
    independent. A shuttle can have 2 people onboard but only 5
    available_seats if 13 people have active bookings — those
    bookings are holding seats that haven't been physically
    occupied yet.

    Previously, available_seats was computed as:
        available_seats = total_capacity - passenger_count

    Now it is a stored field maintained explicitly on every
    event that affects it:
        Book        -> available_seats -= 1
        Cancel      -> available_seats += 1
        No-show     -> available_seats += 1
        Board (scan)-> no change to available_seats
        Alight      -> available_seats += 1
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        """Clean test database state before each test."""
        import sqlite3
        import os
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        cursor.execute("DROP TABLE IF EXISTS passenger_events")
        conn.commit()
        conn.close()

    def _boarding_track(self, track_id):
        return {
            "track_id": track_id,
            "previous_centroid": [400, 200],
            "current_centroid": [400, 800],
        }

    def _alighting_track(self, track_id):
        return {
            "track_id": track_id,
            "previous_centroid": [400, 800],
            "current_centroid": [400, 200],
        }

    def test_boarding_increments_passenger_count_only(self):
        """
        Test that boarding (a scan event) increments passenger_count
        by 1 but does NOT touch available_seats. In the soft-hold
        model the seat was already held when the booking was
        created — scanning just confirms the passenger physically
        boarded so only the onboard count changes.
        """
        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        counter.initialize()
        counter.available_seats = 15  # simulating 5 active bookings holding seats
        initial_count = counter.passenger_count

        counter.update_count(self._boarding_track(1))

        assert counter.passenger_count == initial_count + 1
        assert counter.available_seats == 15  # unchanged

    def test_alighting_decrements_count_and_delegates_seat_release(self):
        """
        Test that alighting decrements passenger_count and delegates
        the seat release to seat_pool_manager. The manager handles
        the SQLite write and Firebase sync; CountingLogic just needs
        to refresh its in-memory cache afterwards so reads of
        counter.available_seats stay fresh.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        mock_manager.get_current.return_value = 11
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 5
        counter.available_seats = 10

        counter.update_count(self._alighting_track(1))

        assert counter.passenger_count == 4
        mock_manager.increment.assert_called_once_with(reason="alight")
        assert counter.available_seats == 11

    def test_available_seats_read_from_sqlite_on_initialize(self):
        """
        Test that initialize() reads available_seats from system_state
        instead of computing it from total_capacity - passenger_count.
        This is the core of the soft-hold model — available_seats
        is a stored value maintained on every booking/cancel/board/
        alight event, not a derived value.
        """
        import sqlite3
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_count', '2')"
        )
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES ('available_seats', '5')"
        )
        conn.commit()
        conn.close()

        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        counter.initialize()

        # Old behaviour would compute available_seats as 20 - 2 = 18.
        # New behaviour reads the stored 5 (because 13 active
        # bookings are holding seats).
        assert counter.passenger_count == 2
        assert counter.available_seats == 5

    def test_available_seats_defaults_to_capacity_when_not_in_sqlite(self):
        """
        Test that available_seats defaults to total_capacity on fresh
        deployment when system_state has no available_seats entry.
        This ensures the system works correctly on first ever run
        before any bookings, scans, or service-day resets have set
        the stored value.
        """
        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        counter.initialize()

        assert counter.available_seats == 20

    def test_available_seats_independent_of_passenger_count(self):
        """
        Test that available_seats can be less than total_capacity
        minus passenger_count when bookings are holding seats. This
        is the entire point of the soft-hold model — a shuttle can
        have 2 people physically onboard but only 5 free seats
        because 13 active bookings are reserving the rest.
        """
        import sqlite3
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_count', '2')"
        )
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES ('available_seats', '5')"
        )
        conn.commit()
        conn.close()

        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        counter.initialize()

        # 2 onboard, 5 free, 13 reserved by bookings — total_capacity
        # is 20 but available_seats is NOT 20 - 2 = 18.
        assert counter.available_seats != counter.total_capacity - counter.passenger_count
        assert counter.available_seats == 5
        assert counter.passenger_count == 2

    def test_reset_count_resets_available_seats_to_capacity(self):
        """
        Test that reset_count() restores available_seats back to
        total_capacity. Even in the soft-hold model a manual reset
        means "empty the shuttle and clear all holds" — operators
        only invoke this in emergencies (e.g. wrong count detected
        mid-route) so blowing away the holds is intended.
        """
        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        counter.initialize()
        counter.passenger_count = 8
        counter.available_seats = 3

        counter.reset_count()

        assert counter.passenger_count == 0
        assert counter.available_seats == 20


class TestAlightingReleasesSeatViaPoolManager:
    """
    Tests covering the alighting flow delegating its seat release
    to SeatPoolManager rather than mutating self.available_seats
    inline.

    The manager owns the available_seats field — it writes to
    SQLite, syncs to Firebase, and caps at total_capacity. After
    delegation, CountingLogic refreshes self.available_seats from
    the manager so callers reading counter.available_seats see the
    fresh value.

    When seat_pool_manager is None, the alighting flow simply
    skips the seat release. There is no inline fallback — this
    is by design, single path, no drift risk.
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        cursor.execute("DROP TABLE IF EXISTS passenger_events")
        conn.commit()
        conn.close()

    def _alighting_track(self, track_id):
        return {
            "track_id": track_id,
            "previous_centroid": [400, 800],
            "current_centroid": [400, 200],
        }

    def test_alighting_calls_increment_with_alight_reason(self):
        """
        Every successful alighting must invoke
        seat_pool_manager.increment with reason='alight' so the
        audit log carries the cause of the seat release.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        mock_manager.get_current.return_value = 11
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 5

        counter.update_count(self._alighting_track(1))

        mock_manager.increment.assert_called_once_with(reason="alight")

    def test_alighting_refreshes_in_memory_available_seats(self):
        """
        After delegating to the manager, counter.available_seats
        must reflect the manager's new value so dashboards and
        UI components reading the attribute see fresh data without
        having to re-query SQLite themselves.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        mock_manager.get_current.return_value = 8
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 5
        counter.available_seats = 7  # stale

        counter.update_count(self._alighting_track(1))

        assert counter.available_seats == 8

    def test_ghost_alighting_does_not_release_seat(self):
        """
        Ghost alighting (alighting detected with count already at
        zero) is an AI false positive. The seat pool must NOT be
        incremented because no real passenger left the shuttle.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 0

        counter.update_count(self._alighting_track(1))

        mock_manager.increment.assert_not_called()

    def test_boarding_does_not_call_seat_pool_manager(self):
        """
        Boarding only confirms physical presence on the shuttle —
        the seat was already held at booking time. The manager
        must not be touched on boarding events.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 0

        boarding_track = {
            "track_id": 1,
            "previous_centroid": [400, 200],
            "current_centroid": [400, 800],
        }
        counter.update_count(boarding_track)

        mock_manager.increment.assert_not_called()
        mock_manager.decrement.assert_not_called()

    def test_alighting_without_manager_skips_seat_release(self):
        """
        When seat_pool_manager is None, the alighting flow still
        decrements passenger_count but takes no action on the seat
        pool. No inline fallback — single path, by design. The
        seat release is simply omitted, and a real production
        wiring is expected to always provide the manager.
        """
        counter = CountingLogic(
            total_capacity=20, db_path=self.TEST_DB, seat_pool_manager=None
        )
        counter.initialize()
        counter.passenger_count = 5
        counter.available_seats = 7

        counter.update_count(self._alighting_track(1))

        # passenger_count still decrements -- that's the core
        # counting responsibility CountingLogic still owns.
        assert counter.passenger_count == 4
        # available_seats is unchanged because no manager mutated it
        assert counter.available_seats == 7


class TestCountingLogicSeatPoolConstructor:
    """
    Tests covering the optional seat_pool_manager constructor
    parameter on CountingLogic.
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    def test_counter_accepts_seat_pool_manager(self):
        """
        Constructor accepts an optional seat_pool_manager so
        production code can wire in a real SeatPoolManager
        instance while isolated tests pass mocks.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        assert counter.seat_pool_manager is mock_manager

    def test_seat_pool_manager_defaults_to_none(self):
        """
        Without an explicit override, seat_pool_manager defaults
        to None so legacy callers and tests that don't care about
        seat releases continue to work unchanged.
        """
        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        assert counter.seat_pool_manager is None


class TestAlightingReleasesSeatViaPoolManager:
    """
    Tests covering the alighting flow delegating its seat release
    to SeatPoolManager rather than mutating self.available_seats
    inline.

    The manager owns the available_seats field — it writes to
    SQLite, syncs to Firebase, and caps at total_capacity. After
    delegation, CountingLogic refreshes self.available_seats from
    the manager so callers reading counter.available_seats see the
    fresh value.

    When seat_pool_manager is None, the alighting flow simply
    skips the seat release. There is no inline fallback — this
    is by design, single path, no drift risk.
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        cursor.execute("DROP TABLE IF EXISTS passenger_events")
        conn.commit()
        conn.close()

    def _alighting_track(self, track_id):
        return {
            "track_id": track_id,
            "previous_centroid": [400, 800],
            "current_centroid": [400, 200],
        }

    def test_alighting_calls_increment_with_alight_reason(self):
        """
        Every successful alighting must invoke
        seat_pool_manager.increment with reason='alight' so the
        audit log carries the cause of the seat release.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        mock_manager.get_current.return_value = 11
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 5

        counter.update_count(self._alighting_track(1))

        mock_manager.increment.assert_called_once_with(reason="alight")

    def test_alighting_refreshes_in_memory_available_seats(self):
        """
        After delegating to the manager, counter.available_seats
        must reflect the manager's new value so dashboards and
        UI components reading the attribute see fresh data without
        having to re-query SQLite themselves.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        mock_manager.get_current.return_value = 8
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 5
        counter.available_seats = 7  # stale

        counter.update_count(self._alighting_track(1))

        assert counter.available_seats == 8

    def test_ghost_alighting_does_not_release_seat(self):
        """
        Ghost alighting (alighting detected with count already at
        zero) is an AI false positive. The seat pool must NOT be
        incremented because no real passenger left the shuttle.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 0

        counter.update_count(self._alighting_track(1))

        mock_manager.increment.assert_not_called()

    def test_boarding_does_not_call_seat_pool_manager(self):
        """
        Boarding only confirms physical presence on the shuttle —
        the seat was already held at booking time. The manager
        must not be touched on boarding events.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        counter.initialize()
        counter.passenger_count = 0

        boarding_track = {
            "track_id": 1,
            "previous_centroid": [400, 200],
            "current_centroid": [400, 800],
        }
        counter.update_count(boarding_track)

        mock_manager.increment.assert_not_called()
        mock_manager.decrement.assert_not_called()

    def test_alighting_without_manager_skips_seat_release(self):
        """
        When seat_pool_manager is None, the alighting flow still
        decrements passenger_count but takes no action on the seat
        pool. No inline fallback — single path, by design. The
        seat release is simply omitted, and a real production
        wiring is expected to always provide the manager.
        """
        counter = CountingLogic(
            total_capacity=20, db_path=self.TEST_DB, seat_pool_manager=None
        )
        counter.initialize()
        counter.passenger_count = 5
        counter.available_seats = 7

        counter.update_count(self._alighting_track(1))

        # passenger_count still decrements -- that's the core
        # counting responsibility CountingLogic still owns.
        assert counter.passenger_count == 4
        # available_seats is unchanged because no manager mutated it
        assert counter.available_seats == 7


class TestCountingLogicSeatPoolConstructor:
    """
    Tests covering the optional seat_pool_manager constructor
    parameter on CountingLogic.
    """

    TEST_DB = "local_database/test_apcoms.db"

    def setup_method(self):
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(self.TEST_DB)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_state")
        conn.commit()
        conn.close()

    def test_counter_accepts_seat_pool_manager(self):
        """
        Constructor accepts an optional seat_pool_manager so
        production code can wire in a real SeatPoolManager
        instance while isolated tests pass mocks.
        """
        from unittest.mock import MagicMock
        mock_manager = MagicMock()
        counter = CountingLogic(
            total_capacity=20,
            db_path=self.TEST_DB,
            seat_pool_manager=mock_manager,
        )
        assert counter.seat_pool_manager is mock_manager

    def test_seat_pool_manager_defaults_to_none(self):
        """
        Without an explicit override, seat_pool_manager defaults
        to None so legacy callers and tests that don't care about
        seat releases continue to work unchanged.
        """
        counter = CountingLogic(total_capacity=20, db_path=self.TEST_DB)
        assert counter.seat_pool_manager is None
