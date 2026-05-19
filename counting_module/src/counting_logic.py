import sqlite3
import logging
import os

logger = logging.getLogger(__name__)


class CountingLogic:

    def __init__(self, total_capacity=None, db_path=None, data_logger=None):
        import json

        self.db_path = db_path or "local_database/apcoms.db"
        self.virtual_entry_zone = "upper"
        self.virtual_exit_zone = "lower"
        self.data_logger = data_logger
        self.counted_tracks = []
        self.current_stop_index = 0
        self.passenger_count = 0

        # ensure tables exist
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass

        # read total_capacity from SQLite if not provided
        if total_capacity is None:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_state WHERE key='total_capacity'")
                row = cursor.fetchone()
                self.total_capacity = int(row[0]) if row else 20
                conn.close()
            except Exception:
                self.total_capacity = 20
        else:
            self.total_capacity = total_capacity

        self.available_seats = self.total_capacity

        # read stops from SQLite if available
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_state WHERE key='designated_stops'")
            row = cursor.fetchone()
            if row:
                self.designated_stops_list = json.loads(row[0])
            else:
                self.designated_stops_list = [
                    "Western Gate", "CEDAT", "CONAS", "Main Library",
                    "Africa Hall", "Swimming Pool", "Mitchel Hall",
                    "COCIS", "Complex Hall", "CEES", "Lumumba Hall"
                ]
            conn.close()
        except Exception:
            self.designated_stops_list = [
                "Western Gate", "CEDAT", "CONAS", "Main Library",
                "Africa Hall", "Swimming Pool", "Mitchel Hall",
                "COCIS", "Complex Hall", "CEES", "Lumumba Hall"
            ]

    def initialize(self):
        """
        Reads last passenger count and stop index from SQLite so
        counting and stop tracking continues from where it left off.
        Creates tables if they don't exist.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS passenger_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shuttle_id TEXT,
                timestamp TEXT,
                direction TEXT,
                passenger_count INTEGER,
                available_seats INTEGER,
                stop_location TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()

        # read the LIVE passenger count from system_state, NOT from
        # the last passenger_events row.
        cursor.execute(
            "SELECT value FROM system_state WHERE key='current_count'"
        )
        result = cursor.fetchone()
        if result:
            self.passenger_count = int(result[0])

        # read available_seats from system_state — stored field, not derived
        cursor.execute(
            "SELECT value FROM system_state WHERE key='available_seats'"
        )
        seats_result = cursor.fetchone()
        if seats_result:
            self.available_seats = int(seats_result[0])
        # If no entry exists (fresh deployment), available_seats keeps
        # its default value of total_capacity set in __init__.

        cursor.execute("SELECT value FROM system_state WHERE key='current_stop_index'")
        stop_result = cursor.fetchone()
        if stop_result:
            self.current_stop_index = int(stop_result[0])

        conn.close()
        logger.info("Counting Logic initialized successfully")

    def determine_direction(self, track):
        """
        Determines if a tracked person is boarding or alighting based
        on their movement through the virtual entry and exit zones.
        Returns boarding, alighting, or undetermined.
        """
        if track is None:
            return "undetermined"

        frame_midpoint = 1080 / 2

        previous_y = track["previous_centroid"][1]
        current_y = track["current_centroid"][1]

        previous_in_upper = previous_y < frame_midpoint
        current_in_lower = current_y >= frame_midpoint

        previous_in_lower = previous_y >= frame_midpoint
        current_in_upper = current_y < frame_midpoint

        if previous_in_upper and current_in_lower:
            return "boarding"
        elif previous_in_lower and current_in_upper:
            return "alighting"
        else:
            return "undetermined"

    def update_count(self, track):
        """
        Updates passenger count based on direction of movement.
        Prevents double counting by tracking already counted track IDs.
        Logs boarding and alighting events for the Data Logger Component.

        When the AI detects a boarding while the shuttle is already at
        capacity, the boarding is REFUSED (passenger_count not bumped,
        no passenger_event logged) AND a diagnostic alert is raised
        through the optional DataLogger. This surfaces possible safety
        risks (overloading attempts) and AI false positives to the
        operator's dashboard. The track_id is still marked as counted
        so the alert doesn't re-fire on every subsequent frame for
        the same detection.

        When alighting is detected with count already at zero, a less
        severe warning is logged through the same mechanism. This is
        usually an AI false positive but still worth surfacing.
        """
        if track is None:
            return

        if track["track_id"] in self.counted_tracks:
            return

        direction = self.determine_direction(track)

        if direction == "boarding":
            if self.passenger_count < self.total_capacity:
                self.passenger_count += 1
                self.counted_tracks.append(track["track_id"])
                logger.info(f"Boarding event - passenger count: {self.passenger_count}")
            else:
                # ILLEGAL BOARDING: shuttle at capacity but AI sees someone
                # boarding. Mark track_id so we don't re-alert every frame.
                self.counted_tracks.append(track["track_id"])
                logger.warning(
                    "Illegal boarding attempt: shuttle at full capacity"
                )
                if self.data_logger:
                    try:
                        self.data_logger.log_diagnostic({
                            "log_type": "error",
                            "message": (
                                "Illegal boarding attempt: shuttle at full capacity"
                            ),
                        })
                    except Exception as e:
                        logger.error(
                            f"Failed to log illegal-boarding alert: {e}"
                        )

        elif direction == "alighting":
            if self.passenger_count > 0:
                self.passenger_count -= 1
                self.available_seats += 1
                self.counted_tracks.append(track["track_id"])
                logger.info(f"Alighting event - passenger count: {self.passenger_count}")
            else:
                # GHOST ALIGHTING: AI sees someone exit but count is
                # already zero. Likely an AI false positive but worth
                # surfacing for diagnostics.
                self.counted_tracks.append(track["track_id"])
                logger.warning("Ghost alighting: count already at zero")
                if self.data_logger:
                    try:
                        self.data_logger.log_diagnostic({
                            "log_type": "warning",
                            "message": (
                                "Ghost alighting: Model exit detected but count is zero"
                            ),
                        })
                    except Exception as e:
                        logger.error(
                            f"Failed to log ghost-alighting alert: {e}"
                        )

    def calculate_occupancy(self):
        """
        Calculates current occupancy status based on available seats.
        Returns Available when seats > 5, Nearly Full when 1-5 seats,
        and Full when no seats are available.
        """
        if self.available_seats > 5:
            occupancy_status = "Available"
        elif self.available_seats >= 1:
            occupancy_status = "Nearly Full"
        else:
            occupancy_status = "Full"

        return {
            "passenger_count": self.passenger_count,
            "available_seats": self.available_seats,
            "occupancy_status": occupancy_status
        }

    def get_current_stop(self):
        """
        Returns the current shuttle stop from the designated stops list
        based on the current stop index so the mobile app and Firebase
        can display accurate shuttle location to students
        """
        return self.designated_stops_list[self.current_stop_index]

    def advance_stop(self):
        """
        Advances to the next stop in the designated stops list.
        Saves new stop index to SQLite for persistence across runs.
        """
        self.current_stop_index = (self.current_stop_index + 1) % len(self.designated_stops_list)
        logger.info(f"Advanced to next stop: {self.designated_stops_list[self.current_stop_index]}")

        if os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # write both the index AND the stop name to keep them
            # in lock-step. Other components read 'current_stop'
            # (the name) for display/Firebase, so it must stay
            # consistent with the index that advance_stop owns.
            current_stop_name = self.designated_stops_list[
                self.current_stop_index
            ]
            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('current_stop_index', ?)
            """, (str(self.current_stop_index),))
            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('current_stop', ?)
            """, (current_stop_name,))
            conn.commit()
            conn.close()

    def reset_count(self):
        """
        Resets passenger count, available seats and counted tracks
        back to initial values. Called on system startup, crash
        recovery, or manually by administrator via Flask dashboard.
        Logs reset timestamp for audit trail.
        """
        import datetime
        self.passenger_count = 0
        self.available_seats = self.total_capacity
        self.counted_tracks = []
        self.current_stop_index = 0
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Passenger count reset at: {timestamp}")
