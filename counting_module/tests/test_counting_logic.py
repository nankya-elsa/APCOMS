import pytest
import os
import sys

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
        assert "Shuttle at full capacity" in caplog.text

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
        assert "Count already at zero" in caplog.text


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
