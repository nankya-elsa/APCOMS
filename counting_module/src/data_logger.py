import sqlite3
import logging
import os

logger = logging.getLogger(__name__)


class DataLogger:

    def __init__(self, shuttle_id, db_path=None):
        self.shuttle_id = shuttle_id
        self.db_path = db_path or "local_database/apcoms.db"

    def initialize(self):
        """
        Connects to SQLite database and creates tables if they don't
        exist. Creates PASSENGER_EVENT, DIAGNOSTIC_LOG and SYSTEM_STATE
        tables. Logs success message when database is ready.
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
            CREATE TABLE IF NOT EXISTS diagnostic_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shuttle_id TEXT,
                timestamp TEXT,
                log_type TEXT,
                message TEXT,
                camera_status TEXT,
                fps REAL,
                latency_ms REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()
        conn.close()
        logger.info("SQLite database connected successfully")

    def log_event(self, event_data):
        """
        Writes a passenger boarding or alighting event to the
        passenger_events table in SQLite with timestamp and stop location.
        Returns True on success, False on failure.
        Logs success or error message accordingly.
        """
        try:
            import datetime
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO passenger_events
                (shuttle_id, timestamp, direction, passenger_count,
                available_seats, stop_location)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.shuttle_id,
                timestamp,
                event_data["direction"],
                event_data["passenger_count"],
                event_data["available_seats"],
                event_data.get("stop_location", "Unknown")
            ))
            conn.commit()
            conn.close()
            logger.info("Event logged successfully")
            return True
        except Exception:
            logger.error("Failed to write event to database")
            return False

    def log_diagnostic(self, diagnostic_data):
        """
        Writes system diagnostic data to the diagnostic_log table
        in SQLite including message, camera status, FPS and latency.
        Returns True on success, False on failure.
        Logs success or error message accordingly.
        """
        try:
            import datetime
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO diagnostic_log
                (shuttle_id, timestamp, log_type, message, camera_status, fps, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                self.shuttle_id,
                timestamp,
                diagnostic_data["log_type"],
                diagnostic_data.get("message", ""),
                diagnostic_data.get("camera_status", "ok"),
                diagnostic_data.get("fps", 0.0),
                diagnostic_data.get("latency_ms", 0.0)
            ))
            conn.commit()
            conn.close()
            logger.info("Diagnostic entry logged successfully")
            return True
        except Exception:
            logger.error("Failed to write diagnostic to database")
            return False

    def monitor_storage(self, available_gb=None):
        """
        Checks available storage space and warns if below minimum
        threshold of 1GB. Logs warning and writes diagnostic entry
        with message when storage is running low.
        Returns storage info dictionary.
        """
        minimum_threshold_gb = 1.0

        if available_gb is None:
            import shutil
            import platform
            if platform.system() == "Windows":
                path = "C:\\"
            else:
                path = "/"
            total, used, free = shutil.disk_usage(path)
            available_gb = free / (1024 ** 3)

        if available_gb < minimum_threshold_gb:
            logger.warning("Storage running low")
            self.log_diagnostic({
                "log_type": "warning",
                "message": "Storage running low",
                "camera_status": "ok",
                "fps": 0.0,
                "latency_ms": 0.0
            })

        return {"available_gb": available_gb}
