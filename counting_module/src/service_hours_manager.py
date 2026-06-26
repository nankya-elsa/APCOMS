"""
Service Hours Manager Component for APCOMS

Manages service start/end times stored in SQLite and syncs them to Firebase
so the mobile app can enforce booking hour restrictions.

The app listens to /shuttles/{shuttle_id}/service_start_time and 
/shuttles/{shuttle_id}/service_end_time and adjusts booking restrictions
dynamically. If the admin changes hours in the dashboard, Firebase
automatically updates and the app picks up the new restriction instantly.

Service hours are stored in the SQLite system_state table:
  - day_start_time (default: "06:00")
  - day_end_time (default: "24:00")
"""

import sqlite3
import logging
import datetime
import os

logger = logging.getLogger(__name__)


class ServiceHoursManager:
    """
    Manages service hours from SQLite and syncs to Firebase.
    
    Attributes:
        db_path: Path to the SQLite database
        shuttle_id: Identifier for this shuttle
        firebase_ref: Reference to /shuttles/{shuttle_id}
        _cached_hours: Last known hours (start_time, end_time, timestamp)
    """

    def __init__(self, shuttle_id, db_path=None):
        """
        Initialize the ServiceHoursManager.

        Args:
            shuttle_id: The shuttle identifier (e.g., 'shuttle_001')
            db_path: Optional override for the SQLite database path.
                    Defaults to 'local_database/apcoms.db'.
        """
        self.db_path = db_path or "local_database/apcoms.db"
        self.shuttle_id = shuttle_id
        self.firebase_ref = None
        self._cached_hours = None
        self._last_sync_time = None

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK on first use if not already done.
        """
        if self.firebase_ref is None:
            try:
                import firebase_admin
                from firebase_admin import credentials, db

                if not firebase_admin._apps:
                    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
                    db_url = os.getenv("FIREBASE_DATABASE_URL")
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred, {"databaseURL": db_url})

                self.firebase_ref = db.reference(f"/shuttles/{self.shuttle_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize Firebase: {e}")
                self.firebase_ref = None

    def _read_hours_from_db(self):
        """
        Read service hours from the SQLite system_state table.

        Returns a tuple: (start_time, end_time) as strings (e.g., "06:00", "24:00")
        Returns defaults ("06:00", "24:00") if not found in database.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT value FROM system_state WHERE key='day_start_time'")
            row = cursor.fetchone()
            start_time = row[0] if row else "06:00"

            cursor.execute("SELECT value FROM system_state WHERE key='day_end_time'")
            row = cursor.fetchone()
            end_time = row[0] if row else "24:00"

            conn.close()
            return (start_time, end_time)
        except Exception as e:
            logger.warning(f"Failed to read service hours from database: {e}")
            return ("06:00", "24:00")

    def _validate_time_format(self, time_str):
        """
        Validate that a time string is in HH:MM format.

        Args:
            time_str: Time string to validate (e.g., "06:00")

        Returns:
            True if valid, False otherwise
        """
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return False
            h, m = int(parts[0]), int(parts[1])
            # Allow 24:00 for end_time (represents end of day)
            return (0 <= h <= 24) and (0 <= m <= 59)
        except (ValueError, AttributeError):
            return False

    def check_and_sync(self):
        """
        Check if service hours have changed since last sync, and if so,
        push the new hours to Firebase.

        This method is designed to be called periodically (e.g., every 5 minutes)
        from the dashboard background thread.

        Returns:
            True if sync was successful (or no change needed), False on error.
        """
        try:
            # Read current hours from database
            current_hours = self._read_hours_from_db()
            current_start, current_end = current_hours

            # Validate format
            if not self._validate_time_format(current_start):
                logger.warning(f"Invalid start time format: {current_start}, skipping sync")
                return False

            if not self._validate_time_format(current_end):
                logger.warning(f"Invalid end time format: {current_end}, skipping sync")
                return False

            # Check if hours changed since last cache
            if self._cached_hours == current_hours:
                # No change, no need to sync
                return True

            # Hours changed, update cache and sync to Firebase
            self._cached_hours = current_hours
            return self._sync_to_firebase(current_start, current_end)

        except Exception as e:
            logger.error(f"Error checking and syncing service hours: {e}")
            return False

    def _sync_to_firebase(self, start_time, end_time):
        """
        Push service hours to Firebase.

        Args:
            start_time: Start time as string (e.g., "06:00")
            end_time: End time as string (e.g., "24:00")

        Returns:
            True on success, False on failure.
        """
        try:
            self._ensure_firebase()
            if self.firebase_ref is None:
                logger.warning("Firebase not available, cannot sync service hours")
                return False

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            payload = {
                "service_start_time": start_time,
                "service_end_time": end_time,
                "last_service_hours_updated": timestamp,
            }

            # Update Firebase with service hours
            self.firebase_ref.update(payload)
            
            self._last_sync_time = datetime.datetime.now()
            logger.info(
                f"Service hours synced to Firebase: {start_time} - {end_time}"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to sync service hours to Firebase: {e}")
            return False

    def get_current_hours(self):
        """
        Get the currently configured service hours.

        Returns:
            A dict with:
              - start_time: Start time string (e.g., "06:00")
              - end_time: End time string (e.g., "24:00")
        """
        start_time, end_time = self._read_hours_from_db()
        return {
            "start_time": start_time,
            "end_time": end_time,
        }
