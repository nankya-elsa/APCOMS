"""
SeatPoolManager component for APCOMS

Owns the available_seats stored field in SQLite system_state. In
the soft-hold reservation model, available_seats is maintained
explicitly on every event that affects it rather than derived
from total_capacity minus passenger_count:

    Book        -> decrement (seat held by reservation)
    Cancel      -> increment (user released their hold)
    No-show     -> increment (canceller released the hold)
    Alight      -> increment (passenger left, seat returns to pool)

This component is the single source of truth for those mutations.
Other components (NoShowCanceller, CountingLogic, the Firebase
booking listener) call increment/decrement here rather than
writing to system_state directly.

Each mutation also pushes the full occupancy payload to Firebase
via the optional FirebaseSyncComponent so the dashboard, OLED,
and mobile app stay consistent with the local source of truth.
"""

import sqlite3
import json
import logging
import os

from route_config import get_designated_stops, get_total_capacity

logger = logging.getLogger(__name__)


class SeatPoolManager:
    """
    Manages the available_seats stored field.

    Attributes:
        total_capacity: Maximum seats on the shuttle. Increment is
                        capped at this value so available_seats
                        cannot exceed the physical seat limit.
        db_path:        Path to the SQLite database file containing
                        the system_state table.
        firebase_sync:  Optional FirebaseSyncComponent. When present,
                        every mutation pushes the full occupancy
                        payload to Firebase. When None, mutations
                        only update SQLite (offline-first).
    """

    def __init__(self, total_capacity, db_path, firebase_sync=None):
        self.total_capacity = total_capacity
        self.db_path = db_path
        self.firebase_sync = firebase_sync

    def get_current(self):
        """
        Read available_seats from system_state.

        Returns the stored value, or total_capacity as a safe
        default when no entry exists (fresh deployment) or the
        stored value is corrupt (non-integer).
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state WHERE key='available_seats'"
            )
            row = cursor.fetchone()
            conn.close()
            if row is None:
                return self.total_capacity
            return int(row[0])
        except (sqlite3.Error, ValueError, TypeError):
            return self.total_capacity

    def _get_effective_available_seats(self, current_count=0):
        """
        Resolve the seat count to push to Firebase.

        When TOTAL_CAPACITY is set in the environment, treat stale
        SQLite values above the new capacity as outdated and clamp
        the payload to the new effective capacity minus the current
        passenger count.
        """
        env_capacity = os.getenv("TOTAL_CAPACITY")
        if env_capacity is None or not str(env_capacity).strip():
            return self.get_current()

        try:
            env_capacity_value = int(str(env_capacity).strip())
        except (TypeError, ValueError):
            return self.get_current()

        stored_value = self.get_current()
        if stored_value > env_capacity_value:
            return max(env_capacity_value - int(current_count), 0)

        return stored_value

    def increment(self, reason):
        """
        Release a seat back to the pool (cap at total_capacity).

        Called on cancel, no-show, or alight events. After the
        SQLite write, syncs the new state to Firebase.
        """
        current = self.get_current()
        new_value = min(current + 1, self.total_capacity)
        self._write(new_value)
        logger.info(f"Seat released ({reason}) -- available_seats now {new_value}")
        self._sync_to_firebase(available_seats_override=new_value)

    def decrement(self, reason):
        """
        Hold a seat from the pool (cap at 0).

        Called on book events. After the SQLite write, syncs the
        new state to Firebase.
        """
        current = self.get_current()
        new_value = max(current - 1, 0)
        self._write(new_value)
        logger.info(f"Seat held ({reason}) -- available_seats now {new_value}")
        self._sync_to_firebase(available_seats_override=new_value)

    def _write(self, new_value):
        """Persist the new available_seats value to system_state."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('available_seats', ?)
            """, (str(new_value),))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to write available_seats: {e}")

    def _sync_to_firebase(self, available_seats_override=None):
        """
        Push the full occupancy payload to Firebase.

        FirebaseSyncComponent.sync_to_firebase() does a full
        overwrite of shuttles/{id} so we must include every
        downstream-relevant field, not just available_seats.
        Reads current_count, current_stop, current_stop_index,
        and designated_stops from SQLite to assemble the payload.
        """
        if self.firebase_sync is None:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT value FROM system_state WHERE key='current_count'"
            )
            row = cursor.fetchone()
            current_count = int(row[0]) if row else 0

            cursor.execute(
                "SELECT value FROM system_state WHERE key='current_stop'"
            )
            row = cursor.fetchone()
            current_stop = row[0] if row else "Unknown"

            cursor.execute(
                "SELECT value FROM system_state WHERE key='current_stop_index'"
            )
            row = cursor.fetchone()
            current_stop_index = int(row[0]) if row else 0

            conn.close()
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Failed to read state for Firebase sync: {e}")
            return

        stops = get_designated_stops(self.db_path)

        if available_seats_override is not None:
            available_seats = available_seats_override
        elif os.getenv("TOTAL_CAPACITY") is not None and str(os.getenv("TOTAL_CAPACITY")).strip():
            available_seats = self._get_effective_available_seats(current_count)
        else:
            available_seats = max(
                int(get_total_capacity(db_path=self.db_path, default=self.total_capacity)) - current_count,
                0,
            )

        # compute next_stop with wraparound
        if stops:
            next_index = (current_stop_index + 1) % len(stops)
            next_stop = stops[next_index]
        else:
            next_stop = "Unknown"

        # compute occupancy_status from available_seats — matches
        # CountingLogic.calculate_occupancy thresholds
        if available_seats > 5:
            occupancy_status = "Available"
        elif available_seats >= 1:
            occupancy_status = "Nearly Full"
        else:
            occupancy_status = "Full"

        payload = {
            "passenger_count": current_count,
            "available_seats": available_seats,
            "occupancy_status": occupancy_status,
            "current_stop": current_stop,
            "next_stop": next_stop,
        }

        try:
            self.firebase_sync.sync_to_firebase(payload)
        except Exception as e:
            logger.error(f"Firebase sync failed: {e}")
