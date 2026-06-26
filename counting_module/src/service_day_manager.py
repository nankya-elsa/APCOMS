"""
Service Day Manager Component for APCOMS

Resets the shuttle's live state to a fresh-day baseline at the
start of each service day (configurable, default 06:00). Lazy and
idempotent: the reset only happens when needed, and only once per
service day, regardless of how many times the manager is called.

This component exists because the shuttle's live state (current
passenger count, available seats, current stop, etc.) must reset
each morning so the dashboard reflects "fresh service day" rather
than "yesterday's last state". Without a reset, opening the
dashboard at 7am on day N would show count=20 because that's
where day N-1 ended.

The reset is performed from THREE places (each calls the same
manager so behaviour stays consistent):
  - flask_dashboard.render_dashboard() before serving data
  - main.py startup before initializing the counting pipeline
  - scanner_orchestrator.py startup before launching the queue

Lazy evaluation is used (rather than a background scheduler)
because:
  1. No threads or scheduled tasks needed — works whether or not
     any specific process is running.
  2. The cost is one SQLite read per call, negligible.
  3. The 'last_reset_date' marker tracks idempotency, so multiple
     callers can safely invoke the manager without coordination.

What is RESET (all live state):
  - current_count, available_seats
  - current_stop_index, current_stop (name)
  - system_status, camera_status
  - current_fps, current_latency
  - last_reset_date (marker)

What is NEVER touched:
  - passenger_events table (historical record)
  - diagnostic_logs table (forensic record)
  - pending_cancellations queue
  - Configuration keys (total_capacity, designated_stops,
    shuttle_id, day_start_time, day_end_time)
"""

import datetime
import logging
import sqlite3

from route_config import get_designated_stops, get_total_capacity

logger = logging.getLogger(__name__)


class ServiceDayManager:
    """
    Resets shuttle live state at the start of each service day.

    Idempotent — once a reset has been performed for a given
    service day, further calls within that day are no-ops. Safe
    to invoke from multiple callers in any order.

    Attributes:
        db_path: Path to the SQLite database holding system_state
                 and the historical tables that must NOT be touched
                 during reset. Defaults to the production path.
    """

    def __init__(self, db_path=None, firebase_sync=None, bookings_ref=None, shuttle_id=None):
        """
        Initialize the ServiceDayManager.

        Args:
            db_path:       Optional override for the SQLite path.
                           Defaults to 'local_database/apcoms.db'.
            firebase_sync: Optional FirebaseSyncComponent. When
                           provided, perform_reset pushes the fresh
                           baseline to Firebase too, keeping the
                           cloud state consistent with the local
                           reset. When None, only SQLite is reset.
            bookings_ref:  Optional Firebase Realtime Database
                           reference for /bookings. When provided,
                           perform_reset will also flip any
                           reserved/active bookings from a previous
                           service day to cancelled (reason
                           'stale_from_previous_day') so the new
                           day starts with a clean booking pool.
                           When None, stale-booking cancellation is
                           a no-op and legacy callers continue
                           working as before.
            shuttle_id:    The shuttle this manager is for; used to
                           filter bookings during the stale-cancel
                           sweep. Defaults to None — when paired with
                           bookings_ref the caller MUST supply it
                           or no bookings will match.
        """
        self.db_path = db_path or "local_database/apcoms.db"
        self.firebase_sync = firebase_sync
        self.bookings_ref = bookings_ref
        self.shuttle_id = shuttle_id

    def should_reset(self):
        """
        Decide whether a service-day reset is needed right now.

        Reads day_start_time (default 06:00) and last_reset_date
        from system_state, computes the most recent service start
        that should have triggered a reset, and reports whether
        we've already recorded a reset for that day.

        The boundary at exactly day_start_time uses >= so that a
        dashboard load at 06:00:00 sharp targets today's reset,
        not yesterday's. Anything before today's start (e.g. 03:00
        in the morning hours) targets YESTERDAY's reset, because
        from the system's perspective the most-recent service day
        is still the one that started yesterday morning.

        Returns a (needed, target_date) tuple so callers can both
        decide whether to act AND log/use the target date string.

        Returns:
            Tuple of:
              needed:      bool - True if a reset should happen
              target_date: str  - YYYY-MM-DD of the service day
                                  whose reset is/was due
        """
        # read day_start_time setting (default 06:00)
        day_start_str = self._read_state("day_start_time") or "06:00"

        # parse HH:MM
        try:
            start_h, start_m = map(int, day_start_str.split(":"))
        except (ValueError, AttributeError):
            logger.warning(
                f"Invalid day_start_time '{day_start_str}' - using 06:00"
            )
            start_h, start_m = 6, 0

        now = datetime.datetime.now()
        today_start = now.replace(
            hour=start_h, minute=start_m, second=0, microsecond=0
        )

        # which service day's reset is "the most recent due"?
        if now >= today_start:
            # today's service start has already passed
            target_dt = now
        else:
            # we're in the wee hours before today's service starts;
            # the most-recent service day is yesterday
            target_dt = now - datetime.timedelta(days=1)

        target_date = target_dt.strftime("%Y-%m-%d")
        last_reset_date = self._read_state("last_reset_date")

        needed = last_reset_date != target_date
        return needed, target_date

    def _read_state(self, key):
        """
        Read a single value from system_state.

        Internal helper. Returns None if the key is missing so
        callers can apply their own defaults.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state WHERE key=?", (key,)
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error reading state '{key}': {e}")
            return None

    STALE_REASON = "stale_from_previous_day"

    def cancel_stale_bookings(self, shuttle_id=None):
        """
        Cancel every reserved or active booking left over from a
        previous service day.

        Called by perform_reset at the service-day boundary. By the
        time this runs, the local SQLite live state (count,
        available_seats) has already been reset to fresh-day
        baseline. Stale bookings in Firebase would otherwise
        desync the system: has_pickups_here() would see phantom
        pickups, the scanner queue would open for passengers who
        never come, and the dashboard would show expected boardings
        that won't happen.

        The cancellation does NOT touch the seat pool. available_seats
        is already at total_capacity from the reset — incrementing
        for each stale booking would push it above capacity. The
        BookingFirebaseListener must also recognise this cancel
        reason and skip its own increment (mirroring the existing
        'no_show_at_pickup' skip).

        Args:
            shuttle_id: Filter bookings to this shuttle only. If
                        omitted, falls back to self.shuttle_id.

        Returns:
            The count of bookings cancelled (0 if none, or if
            bookings_ref is not configured, or if Firebase errored).
        """
        if self.bookings_ref is None:
            return 0

        target_shuttle = shuttle_id or self.shuttle_id

        try:
            all_bookings = self.bookings_ref.get()
        except Exception as e:
            logger.error(
                f"Stale-booking cancel failed reading /bookings: {e}"
            )
            return 0

        if not all_bookings or not isinstance(all_bookings, dict):
            return 0

        # collect every booking that needs cancelling
        timestamp = datetime.datetime.now().isoformat()
        update_payload = {}
        cancel_count = 0

        for booking_id, booking_data in all_bookings.items():
            if not isinstance(booking_data, dict):
                continue
            if booking_data.get("shuttle_key") != target_shuttle:
                continue
            status = booking_data.get("status")
            if status not in ("reserved", "active"):
                continue

            update_payload[f"{booking_id}/status"] = "cancelled"
            update_payload[f"{booking_id}/cancel_reason"] = self.STALE_REASON
            update_payload[f"{booking_id}/cancelled_at"] = timestamp
            cancel_count += 1

        if cancel_count == 0:
            return 0

        # one atomic multi-path update -- either all stale bookings
        # flip together or none do, preventing partial state.
        try:
            self.bookings_ref.update(update_payload)
            logger.info(
                f"Cancelled {cancel_count} stale booking(s) "
                f"from previous service day"
            )
            return cancel_count
        except Exception as e:
            logger.error(
                f"Stale-booking cancel failed writing update: {e}"
            )
            return 0

    def perform_reset(self, target_date):
        """
        Reset all live state to a fresh service-day baseline.

        Writes new values for every live-state key in system_state
        in a single transaction. Reads configuration keys
        (total_capacity, designated_stops) to populate sensible
        derived values like available_seats and current_stop name.

        Falls back to defaults when configuration is missing:
          - total_capacity -> 20 (typical campus shuttle)
          - first stop    -> 'Western Gate' (the route's first stop)

        Historical tables (passenger_events, diagnostic_logs) are
        never touched here. The reset only clears the LIVE state
        snapshot. Configuration keys are never touched either.

        Args:
            target_date: 'YYYY-MM-DD' string identifying the
                         service day this reset covers. Stored as
                         last_reset_date so subsequent should_reset
                         calls see this day as already handled.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # ensure system_state exists before reading/writing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            total_capacity = get_total_capacity(
                db_path=self.db_path,
                default=20,
            )

            # read designated_stops to get the first stop name; default Western Gate
            stops = get_designated_stops(self.db_path)
            first_stop = stops[0] if stops else "Western Gate"

            # apply all live-state writes in a single batch
            resets = [
                ("current_count", "0"),
                ("available_seats", total_capacity),
                ("current_stop_index", "0"),
                ("current_stop", first_stop),
                ("system_status", "Active"),
                ("camera_status", "unknown"),
                ("current_fps", "0"),
                ("current_latency", "0"),
                ("last_reset_date", target_date),
            ]
            for key, value in resets:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES (?, ?)
                    """,
                    (key, value),
                )

            conn.commit()
            conn.close()

            logger.info(
                f"Service-day reset completed for {target_date} "
                f"(count=0, capacity={total_capacity}, "
                f"first_stop={first_stop})"
            )
        except sqlite3.Error as e:
            logger.error(f"Error performing reset: {e}")
            return

        # flip any reserved/active bookings from the previous service
        # day to cancelled. The local seat pool has already been
        # reset to total_capacity above so we explicitly do NOT
        # increment for each cancellation -- the seat math is already
        # correct. The BookingFirebaseListener also knows to skip
        # increments for the STALE_REASON.
        self.cancel_stale_bookings()

        # push the fresh baseline to Firebase so the dashboard and
        # mobile app see the reset immediately. firebase_sync is
        # optional -- if missing, we skip cloud sync rather than
        # crashing. Failures are logged but never block the local
        # reset (offline-first principle).
        if self.firebase_sync is None:
            return

        try:
            # compute next_stop with wraparound. Fall back to the
            # same default stops list CountingLogic uses when
            # designated_stops is absent from SQLite — keeps Firebase
            # consistent even on a fresh deployment where the
            # operator hasn't saved a stops configuration yet.
            stops_list = get_designated_stops(self.db_path)
            next_stop = stops_list[1] if len(stops_list) > 1 else first_stop

            payload = {
                "passenger_count": 0,
                "available_seats": int(total_capacity),
                "occupancy_status": "Available",
                "current_stop": first_stop,
                "next_stop": next_stop,
            }
            self.firebase_sync.sync_to_firebase(payload)
            logger.info(
                f"Service-day reset pushed to Firebase ({target_date})"
            )
        except Exception as e:
            logger.error(f"Failed to push reset to Firebase: {e}")

    def reset_if_needed(self):
        """
        Perform the service-day reset if one is due.

        This is the public method callers should invoke. It
        combines should_reset (decide) and perform_reset (act) into
        a single idempotent operation. Safe to call repeatedly
        from any component — only the first call within a service
        day actually does work.

        Used from:
          - flask_dashboard.render_dashboard() before serving data
          - main.py startup before initializing the pipeline
          - scanner_orchestrator.py startup before launching scans

        Returns:
            The target_date string ('YYYY-MM-DD') that was reset,
            or None if no reset was needed. Callers can use the
            return value for logging or downstream signalling.
        """
        needed, target_date = self.should_reset()
        if not needed:
            return None

        self.perform_reset(target_date)
        return target_date

