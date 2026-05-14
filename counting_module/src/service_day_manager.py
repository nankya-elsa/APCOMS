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

    def __init__(self, db_path=None):
        """
        Initialize the ServiceDayManager.

        Args:
            db_path: Optional override for the SQLite path. When
                     omitted, defaults to the production path
                     'local_database/apcoms.db' so callers that
                     just want default behaviour need no setup.
        """
        self.db_path = db_path or "local_database/apcoms.db"

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

            # read total_capacity for available_seats; default 20
            cursor.execute(
                "SELECT value FROM system_state WHERE key='total_capacity'"
            )
            row = cursor.fetchone()
            total_capacity = row[0] if row else "20"

            # read designated_stops to get the first stop name; default Western Gate
            cursor.execute(
                "SELECT value FROM system_state WHERE key='designated_stops'"
            )
            row = cursor.fetchone()
            first_stop = "Western Gate"
            if row and row[0]:
                try:
                    import json
                    stops = json.loads(row[0])
                    if isinstance(stops, list) and len(stops) > 0:
                        first_stop = stops[0]
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "designated_stops not valid JSON list; "
                        "using default first stop 'Western Gate'"
                    )

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

