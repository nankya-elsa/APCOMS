"""
Booking Dashboard Service Component for APCOMS

Aggregates booking data from Firebase to power the admin dashboard's
monitoring and analytics views. Unlike booking_validator,
booking_completer, and no_show_canceller — which mutate booking state —
this service is READ-ONLY. It exists to surface insights about the
booking lifecycle to operators without changing any data.

Four query methods are exposed:

  - get_pickups_expected(stop)
        Live count of reserved bookings whose pickup is the given
        stop. Drives the "Pickups Expected Here" card on the
        Monitoring tab.

  - get_boarded_from_stop(stop)
        Live count of bookings active or completed with the given
        stop as pickup. Drives the "Boarded from Here" card on
        the Monitoring tab.

  - get_booking_funnel()
        Aggregate counts across the full booking lifecycle since
        deployment. Drives the funnel chart on the Analytics tab.

  - get_no_show_rate_by_stop()
        Per-stop percentage of bookings that were cancelled with
        reason 'no_show_at_pickup'. Drives the bar chart on the
        Analytics tab.

The service reads Firebase directly because the dashboard is online
by definition — Flask runs alongside operations with network access.
No offline cache is needed for dashboard queries.
"""

import os
import logging
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BookingDashboardService:
    """
    Read-only Firebase booking query service for the admin dashboard.

    Firebase clients are loaded lazily so the service can be
    constructed and tested without an active Firebase connection.
    All queries filter by shuttle_id so multi-shuttle deployments
    do not show data from other shuttles.

    Attributes:
        shuttle_id: Identifier for this shuttle, used to filter
                    bookings. Read from SHUTTLE_ID env var with
                    fallback to 'shuttle_001'.
    """

    def __init__(self, shuttle_id=None, db_path=None):
        """
        Initialize the BookingDashboardService.

        Args:
            shuttle_id: Optional override for the shuttle ID.
                        Defaults to the SHUTTLE_ID environment
                        variable or 'shuttle_001' if unset.
            db_path:    Optional override for the SQLite database
                        path. Used by get_alighted_at_stop() to read
                        the current_stop_arrived_at_ms timestamp.
                        Defaults to the production database; tests
                        override this to isolate.
        """
        self.shuttle_id = shuttle_id or os.getenv(
            "SHUTTLE_ID", "shuttle_001"
        )
        self.db_path = db_path or "local_database/apcoms.db"
        self._firebase_ready = False

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK on first use.

        Idempotent — safe to call repeatedly; only the first call
        actually initializes. Mirrors the pattern used in
        BookingValidator, BookingCompleter, and NoShowCanceller
        so the whole counting module shares one Firebase app.
        """
        if self._firebase_ready:
            return

        if firebase_admin._apps:
            self._firebase_ready = True
            return

        cred_path = os.getenv(
            "FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json"
        )
        database_url = os.getenv("FIREBASE_DATABASE_URL")

        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(
                cred, {"databaseURL": database_url}
            )
            self._firebase_ready = True
            logger.info("Firebase initialized for BookingDashboardService")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def get_pickups_expected(self, stop):
        """
        Count reserved bookings whose pickup is the given stop.

        Queries /bookings/ in Firebase and counts entries where:
          - shuttle_key matches this shuttle
          - status is exactly 'reserved' (not active/completed/cancelled)
          - pickup_stop matches the given stop

        Returns 0 on any failure (empty database, network error,
        permission issue) so the dashboard never crashes — it just
        displays zero, which is the correct empty-state.

        Args:
            stop: The shuttle stop name to query for.

        Returns:
            Integer count of reserved bookings at this stop for
            this shuttle. Always non-negative.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return 0

        if not all_bookings:
            return 0

        count = 0
        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "reserved":
                continue
            if booking.get("pickup_stop") != stop:
                continue
            count += 1

        return count

    def get_boarded_from_stop(self, stop):
        """
        Count bookings currently active that scanned at the given stop.

        Queries /bookings/ in Firebase and counts entries where:
          - shuttle_key matches this shuttle
          - status is exactly 'active' (not completed/reserved/cancelled)
          - pickup_stop matches the given stop

        IMPORTANT: only 'active' bookings are counted, NOT 'completed'.
        This is intentional because the shuttle loops through stops
        repeatedly throughout the day. A booking that completed earlier
        (passenger boarded at CEDAT, alighted at Main Library) still has
        pickup_stop=CEDAT in Firebase. If we counted completed bookings
        when the shuttle returns to CEDAT later, we'd double-count
        previous trips' boardings.

        Counting only 'active' keeps this card scoped to the operator's
        mental model: "passengers currently onboard who boarded at this
        stop". As soon as the shuttle moves to the next stop, the
        dashboard's current_stop changes and this card refreshes for
        the new stop — the previous stop's count becomes irrelevant.

        Returns 0 on any failure so the dashboard never crashes.

        Args:
            stop: The shuttle stop name to query for.

        Returns:
            Integer count of active bookings with pickup_stop=stop
            for this shuttle. Always non-negative.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return 0

        if not all_bookings:
            return 0

        count = 0
        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "active":
                continue
            if booking.get("pickup_stop") != stop:
                continue
            count += 1

        return count

    def get_alightings_expected(self, stop):
        """
        Count active bookings whose destination is the given stop.

        Queries /bookings/ in Firebase and counts entries where:
          - shuttle_key matches this shuttle
          - status is exactly 'active' (not reserved/completed/cancelled)
          - destination_stop matches the given stop

        These are passengers currently onboard who chose this stop
        as their drop-off point. By counting only 'active' bookings,
        the count is self-resetting between shuttle visits — once
        passengers alight, their status flips to 'completed' and
        they're excluded from this count. So when the shuttle
        approaches the same stop on a later loop, only the new
        wave of passengers expecting to alight there is counted.

        Returns 0 on any failure (empty database, network error,
        permission issue) so the dashboard never crashes — it just
        displays zero, which is the correct empty-state.

        Args:
            stop: The shuttle stop name to query for.

        Returns:
            Integer count of active bookings with destination_stop=stop
            for this shuttle. Always non-negative.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return 0

        if not all_bookings:
            return 0

        count = 0
        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "active":
                continue
            if booking.get("destination_stop") != stop:
                continue
            count += 1

        return count

    def get_alighted_at_stop(self, stop):
        """
        Count bookings that have actually completed at the given
        stop DURING the current visit.

        The "current visit" boundary is critical because the shuttle
        loops through stops all day. A booking completed at CONAS
        in the morning trip must NOT be counted again when the
        shuttle returns to CONAS in the afternoon. Self-scoping is
        achieved by:

          1. Reading current_stop_arrived_at_ms from SQLite — the
             Unix timestamp recorded by advance_and_sync when the
             shuttle pulled up at this stop.
          2. Including only completions whose completed_at >=
             current_stop_arrived_at_ms (within this specific visit).
          3. As a belt-and-suspenders safety net, also requiring
             the completion's date to match current_stop_arrived_date
             (today's date). This guarantees yesterday's data never
             pollutes today's counts even if the timestamp logic
             somehow fails.

        Returns 0 when:
          - The arrival timestamp hasn't been written yet (fresh
            deployment, before any stop transition)
          - Firebase is unreachable
          - No completed bookings match the query

        Args:
            stop: The shuttle stop name to query for.

        Returns:
            Integer count of completed bookings with
            destination_stop=stop, completed during the current
            visit. Always non-negative.
        """
        import sqlite3
        import datetime

        # read the arrival timestamp + date from SQLite. if either
        # is missing, return 0 cleanly — the shuttle hasn't had
        # its first stop transition yet, so there are no in-visit
        # completions by definition.
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state "
                "WHERE key='current_stop_arrived_at_ms'"
            )
            row = cursor.fetchone()
            arrived_at_ms = int(row[0]) if row else None

            cursor.execute(
                "SELECT value FROM system_state "
                "WHERE key='current_stop_arrived_date'"
            )
            row = cursor.fetchone()
            arrived_date = row[0] if row else None
            conn.close()
        except Exception as e:
            logger.error(f"Error reading arrival state: {e}")
            return 0

        if arrived_at_ms is None or arrived_date is None:
            return 0

        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return 0

        if not all_bookings:
            return 0

        count = 0
        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue
            if booking.get("status") != "completed":
                continue
            if booking.get("destination_stop") != stop:
                continue

            completed_at = booking.get("completed_at")
            if completed_at is None:
                continue

            # current-visit guard: completed must be at or after the
            # shuttle's arrival at this stop
            if completed_at < arrived_at_ms:
                continue

            # date safety net: completion's calendar date must match
            # the arrival date. converts unix-ms to YYYY-MM-DD for
            # comparison.
            try:
                completed_date = datetime.datetime.fromtimestamp(
                    completed_at / 1000
                ).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                continue

            if completed_date != arrived_date:
                continue

            count += 1

        return count

    def list_all_bookings(self):
        """
        Return every booking belonging to this shuttle, sorted by
        created_at descending so the newest booking sits at the top
        of the table.

        Used by the Live Bookings demo tab to give the panel a
        real-time view of every reservation flowing through the
        system. The output is not used by mobile clients, only the
        demo dashboard.

        Each entry contains:
          booking_id            - the Firebase key (e.g. 'b1')
          pickup_stop           - origin stop name
          destination_stop      - destination stop name
          status                - 'reserved' / 'active' / 'completed' / 'cancelled'
          cancel_reason         - reason string if cancelled, empty string otherwise
          created_at_display    - human-readable timestamp string
                                  ('YYYY-MM-DD HH:MM:SS') or '-' if missing

        Bookings without a created_at field still appear in the
        list, sorted to the end (sort key treated as 0).

        Returns an empty list when the database is empty or
        Firebase is unreachable. Never crashes the dashboard.
        """
        import datetime

        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error listing bookings: {e}")
            return []

        if not all_bookings:
            return []

        result = []
        for booking_id, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue

            created_at = booking.get("created_at")
            if created_at:
                try:
                    created_at_display = datetime.datetime.fromtimestamp(
                        created_at / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, OSError):
                    created_at_display = "-"
            else:
                created_at_display = "-"

            status = booking.get("status", "unknown")
            cancel_reason = booking.get("cancel_reason", "") if status == "cancelled" else ""

            result.append({
                "booking_id": booking_id,
                "pickup_stop": booking.get("pickup_stop", "-"),
                "destination_stop": booking.get("destination_stop", "-"),
                "status": status,
                "cancel_reason": cancel_reason,
                "created_at_display": created_at_display,
                "_sort_key": created_at if created_at else 0,
            })

        # sort by created_at descending (newest first)
        result.sort(key=lambda b: b["_sort_key"], reverse=True)

        # strip the internal sort key before returning
        for b in result:
            del b["_sort_key"]

        return result

    def get_booking_funnel(self, start_date=None, end_date=None):
        """
        Cumulative booking funnel showing lifecycle drop-off.

        Uses CUMULATIVE counting where each step counts bookings
        that EVER REACHED that state, not bookings currently at
        that state. This is essential because 'active' is a
        transient status — a booking lives there only between
        scan and alight (typically 20 minutes). If we counted
        only currently-active bookings, the chart would mislead
        by showing near-zero 'active' at end of day even when
        many bookings successfully boarded earlier.

        Date filtering uses the booking's created_at field (Unix
        timestamp in milliseconds, set when the mobile app first
        created the booking). created_at represents when the user
        EXPRESSED INTENT — independent of when the booking later
        transitioned through its lifecycle. A booking created last
        Tuesday that completes today counts in last Tuesday's
        funnel, not today's.

        Bookings missing created_at are excluded from filtered
        queries (we can't place them on the timeline) but included
        in unfiltered queries (backward-compatible behaviour).

        The funnel reads as a story of the booking flow:

          Total Booked
              |
              v
            Boarded (active + completed)
                 |
                 v
              Completed Trips

          Cancelled (parallel exit branch, never boarded)

        Args:
            start_date: Optional 'YYYY-MM-DD' string. Bookings
                        created on or after this date count.
            end_date:   Optional 'YYYY-MM-DD' string. Bookings
                        created on or before this date count.

        Returns:
            Dict with four keys:
              total_booked: int   all matching bookings
              boarded:      int   count of (active + completed)
              completed:    int   count of completed only
              cancelled:    int   count of cancelled only
            Returns all zeros on Firebase failure.
        """
        empty_funnel = {
            "total_booked": 0,
            "boarded": 0,
            "completed": 0,
            "cancelled": 0,
        }

        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return empty_funnel

        if not all_bookings:
            return empty_funnel

        # convert filter dates to ms-timestamp bounds; None = unbounded
        start_ms = self._date_to_ms(start_date, end_of_day=False)
        end_ms = self._date_to_ms(end_date, end_of_day=True)
        filter_active = start_ms is not None or end_ms is not None

        funnel = dict(empty_funnel)
        valid_statuses = {"reserved", "active", "completed", "cancelled"}

        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue

            status = booking.get("status")
            if status not in valid_statuses:
                logger.warning(
                    f"Booking with unknown status '{status}' "
                    f"skipped in funnel aggregation"
                )
                continue

            # date filtering against created_at when filter is active
            if filter_active:
                created_at = booking.get("created_at")
                if created_at is None:
                    # can't place on timeline -- exclude when filtering
                    continue
                if start_ms is not None and created_at < start_ms:
                    continue
                if end_ms is not None and created_at > end_ms:
                    continue

            funnel["total_booked"] += 1

            # boarded = anyone who got past scan (active or completed)
            if status in ("active", "completed"):
                funnel["boarded"] += 1

            if status == "completed":
                funnel["completed"] += 1
            elif status == "cancelled":
                funnel["cancelled"] += 1

        return funnel

    def get_no_show_rate_by_stop(self, start_date=None, end_date=None):
        """
        Per-stop no-show rate as a percentage, optionally filtered
        to bookings created within a date range.

        Aggregates bookings by pickup_stop and calculates the
        percentage of bookings at each stop that became no-shows
        (auto-cancelled by NoShowCanceller when the shuttle left
        the stop without the passenger scanning).

        Only cancel_reason='no_show_at_pickup' counts as a no-show.
        User-initiated cancellations (different cancel_reason) are
        included in the total but excluded from the no-shows count
        — they represent users who actively decided not to take
        the trip, which is operationally different from ghosting.

        Date filtering uses the booking's created_at field, the
        same field used by the booking funnel. A rate calculated
        for a given window is the rate AMONG BOOKINGS MADE during
        that window — regardless of when the cancellation later
        happened. This gives the right answer for time-windowed
        analysis: "of the bookings made last week, what percentage
        no-showed?".

        Bookings missing created_at are excluded when a filter is
        active (can't place them on the timeline) but included
        when no filter is active.

        Used by the Analytics tab to surface stops with high
        no-show rates so operators can investigate:
          - Are passengers booking but realizing the shuttle isn't
            convenient from this stop?
          - Is the scheduled time wrong for this location?
          - Should this stop be removed from the route?

        Args:
            start_date: Optional 'YYYY-MM-DD' string. Bookings
                        created on or after this date count.
            end_date:   Optional 'YYYY-MM-DD' string. Bookings
                        created on or before this date count.

        Returns:
            List of dicts with keys:
              stop:      str   the pickup stop name
              total:     int   total bookings at this stop in window
              no_shows:  int   no-show count at this stop in window
              rate:      float no-show percentage rounded to 2 decimals
            Empty list on Firebase failure.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(f"Error querying bookings: {e}")
            return []

        if not all_bookings:
            return []

        # convert filter dates to ms-timestamp bounds
        start_ms = self._date_to_ms(start_date, end_of_day=False)
        end_ms = self._date_to_ms(end_date, end_of_day=True)
        filter_active = start_ms is not None or end_ms is not None

        # aggregate per stop: {stop_name: {"total": N, "no_shows": M}}
        by_stop = {}

        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue

            stop = booking.get("pickup_stop")
            if not stop:
                continue

            # date filtering against created_at when filter is active
            if filter_active:
                created_at = booking.get("created_at")
                if created_at is None:
                    continue
                if start_ms is not None and created_at < start_ms:
                    continue
                if end_ms is not None and created_at > end_ms:
                    continue

            if stop not in by_stop:
                by_stop[stop] = {"total": 0, "no_shows": 0}

            by_stop[stop]["total"] += 1

            # only auto-cancelled no-shows count toward the no-show metric
            if (
                booking.get("status") == "cancelled"
                and booking.get("cancel_reason") == "no_show_at_pickup"
            ):
                by_stop[stop]["no_shows"] += 1

        # flatten to list with rate calculated
        result = []
        for stop_name, stats in by_stop.items():
            total = stats["total"]
            no_shows = stats["no_shows"]
            rate = round((no_shows / total) * 100, 2) if total > 0 else 0.0
            result.append({
                "stop": stop_name,
                "total": total,
                "no_shows": no_shows,
                "rate": rate,
            })

        return result

    def _date_to_ms(self, date_str, end_of_day=False):
        """
        Convert a 'YYYY-MM-DD' date string to a Unix millisecond
        timestamp suitable for comparing against booking
        created_at values.

        Args:
            date_str:   The date string to parse, or None.
            end_of_day: When True, return 23:59:59 of the date so
                        end_date filters are inclusive of the last
                        day. When False, return 00:00:00.

        Returns:
            Integer milliseconds since epoch, or None if date_str
            is None or unparseable. None signals "no bound here"
            to the caller.
        """
        if not date_str:
            return None
        try:
            from datetime import datetime
            if end_of_day:
                dt = datetime.strptime(date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            return int(dt.timestamp() * 1000)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date string '{date_str}': {e}")
            return None
