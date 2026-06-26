import logging
import os
import signal
import sys
from flask import Flask
import sqlite3
import datetime
import sqlite3
import csv
import io
import threading

from route_config import get_designated_stops, get_total_capacity
from service_hours_manager import ServiceHoursManager

logger = logging.getLogger(__name__)

class FlaskDashboard:

    def __init__(self):
        # explicitly tell Flask where templates are
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        self.app = Flask(
            __name__,
            template_folder=template_dir,
            static_folder=static_dir,
        )
        self.session_timeout = 30
        self.failed_login_attempts = 0
        self.account_locked = False
        self.ngrok_url = None
        self._ngrok_tunnel = None
        self._shutdown_requested = False
        self._last_published_capacity = None
        self._last_published_count = None

        # Initialize Service Hours Manager for Firebase sync
        shuttle_id = os.getenv("SHUTTLE_ID", "shuttle_001")
        self.service_hours_manager = ServiceHoursManager(shuttle_id=shuttle_id)
        self._service_hours_sync_thread = None
        self._service_hours_sync_stop = False

    def initialize(self):
        """
        Starts the Flask web server and configures ngrok tunnel
        to expose the dashboard publicly. Sets session timeout
        and logs success when dashboard is ready. Falls back to
        local access only if ngrok tunnel fails.

        Also starts a background thread to sync service hours to Firebase
        every 5 minutes, so the mobile app can enforce booking restrictions.
        """
        self.setup_routes()
        try:
            from pyngrok import ngrok
            token = os.getenv("NGROK_AUTH_TOKEN")
            if token:
                ngrok.set_auth_token(token)
            tunnel = ngrok.connect(5000)
            self._ngrok_tunnel = tunnel
            self.ngrok_url = tunnel.public_url
            logger.info("=" * 60)
            logger.info(f"DASHBOARD URL: {self.ngrok_url}")
            logger.info("=" * 60)
        except Exception:
            self.ngrok_url = None
            logger.warning("ngrok tunnel failed, dashboard only accessible locally")
            logger.info("=" * 60)
            logger.info("LOCAL URL: http://localhost:5000")
            logger.info("=" * 60)

        self._sync_current_state_to_firebase(force=False)

        # Start background thread to sync service hours to Firebase
        self._start_service_hours_sync_thread()

        logger.info("Flask dashboard initialized successfully")

    def _start_service_hours_sync_thread(self):
        """
        Start a background thread that periodically syncs service hours
        from the database to Firebase every 5 minutes.
        """
        if self._service_hours_sync_thread is not None:
            return  # Already running

        self._service_hours_sync_stop = False
        self._service_hours_sync_thread = threading.Thread(
            target=self._service_hours_sync_loop,
            daemon=True,
            name="ServiceHoursSyncThread"
        )
        self._service_hours_sync_thread.start()
        logger.info("Service hours sync thread started")

    def _service_hours_sync_loop(self):
        """
        Background loop that checks and syncs service hours to Firebase
        every 5 minutes (300 seconds). Runs until _service_hours_sync_stop
        is set to True or the dashboard shuts down.
        """
        sync_interval = 300  # 5 minutes
        while not self._service_hours_sync_stop:
            try:
                self.service_hours_manager.check_and_sync()
            except Exception as e:
                logger.error(f"Error in service hours sync loop: {e}")

            # Sleep in small increments so we can respond to stop signal quickly
            for _ in range(int(sync_interval / 5)):
                if self._service_hours_sync_stop:
                    break
                threading.Event().wait(5)  # Sleep 5 seconds at a time

    def shutdown(self):
        """
        Stop the Flask app and any active ngrok tunnel so Ctrl+C
        exits cleanly instead of hanging on the tunnel teardown.
        Also stops the service hours sync background thread.
        """
        # Stop service hours sync thread
        self._service_hours_sync_stop = True
        if self._service_hours_sync_thread is not None:
            self._service_hours_sync_thread.join(timeout=5)

        if self._shutdown_requested:
            return
        self._shutdown_requested = True

        try:
            if self._ngrok_tunnel is not None:
                from pyngrok import ngrok
                ngrok.disconnect(self._ngrok_tunnel.public_url)
                self._ngrok_tunnel = None
        except Exception as exc:
            logger.warning(f"Failed to disconnect ngrok tunnel: {exc}")

        try:
            if hasattr(self.app, "server") and self.app.server is not None:
                self.app.server.shutdown()
        except Exception as exc:
            logger.warning(f"Failed to shut down Flask server: {exc}")

    def authenticate(self, username, password):
        """
        Validates admin credentials and creates a session on success.
        Increments failed attempts on wrong credentials and locks
        account after 5 failed attempts for security protection.
        Returns True on success, False on failure.
        """
        admin_username = os.getenv("ADMIN_USERNAME", "kmc_admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "Kiira@2026!")

        if self.account_locked:
            logger.warning("Account locked due to multiple failed attempts")
            return False

        if username == admin_username and password == admin_password:
            self.failed_login_attempts = 0
            logger.info("Admin logged in successfully")
            return True
        else:
            self.failed_login_attempts += 1
            if self.failed_login_attempts >= 5:
                self.account_locked = True
                logger.warning("Account locked due to multiple failed attempts")
            else:
                logger.warning("Failed login attempt")
            return False

    def _cancel_live_bookings_for_reset(self, bookings_ref=None, shuttle_id=None):
        """
        Cancel any live reserved/active bookings during an admin reset.

        This keeps the booking stream consistent with the cleared
        live counts: reserved seats disappear from the dashboard and
        the mobile app instead of lingering as phantom holds.
        """
        if bookings_ref is None:
            try:
                from firebase_admin import db
                bookings_ref = db.reference("bookings")
            except Exception:
                return 0

        target_shuttle = shuttle_id or os.getenv("SHUTTLE_ID", "shuttle_001")

        try:
            all_bookings = bookings_ref.get()
        except Exception as exc:
            logger.error(f"Admin reset booking cancellation failed: {exc}")
            return 0

        if not all_bookings or not isinstance(all_bookings, dict):
            return 0

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

            user_uid = booking_data.get("user_uid")

            update_payload[f"bookings/{booking_id}/status"] = "cancelled"
            update_payload[f"bookings/{booking_id}/cancel_reason"] = "reset_by_admin"
            update_payload[f"bookings/{booking_id}/cancelled_at"] = timestamp

            if user_uid:
                update_payload[f"user_bookings/{user_uid}/{booking_id}/status"] = "cancelled"
                update_payload[f"user_bookings/{user_uid}/{booking_id}/cancel_reason"] = "reset_by_admin"
                update_payload[f"user_bookings/{user_uid}/{booking_id}/cancelled_at"] = timestamp

            cancel_count += 1

        if cancel_count == 0:
            return 0

        try:
            from firebase_admin import db as _fb_db
            _fb_db.reference("/").update(update_payload)
            logger.info(
                f"Cancelled {cancel_count} live booking(s) during admin reset"
            )
            return cancel_count
        except Exception as exc:
            logger.error(f"Admin reset booking cancellation failed: {exc}")
            return 0

    def check_end_of_day(self):
        """
        Triggers the daily service-day reset if one is due.

        Delegates entirely to ServiceDayManager which encapsulates
        the decision (should_reset) and the action (perform_reset).
        Called from render_dashboard on every dashboard load so the
        reset fires the moment a new service day begins, regardless
        of whether main.py has run yet.

        The method name 'check_end_of_day' is preserved for backward
        compatibility with existing callers, but the underlying
        logic now resets at the START of the service day (default
        06:00), not at the end. ServiceDayManager owns the full
        semantics — see its module docstring for details.
        """
        from service_day_manager import ServiceDayManager
        from firebase_sync import FirebaseSyncComponent
        import os as _os

        try:
            from firebase_admin import db
        except Exception:
            db = None

        try:
            shuttle_id = _os.getenv("SHUTTLE_ID", "shuttle_001")

            # firebase_sync wired so the service-day reset also
            # propagates to Firebase, not just SQLite.
            firebase_sync = FirebaseSyncComponent(shuttle_id=shuttle_id)
            firebase_sync.initialize()

            # bookings_ref + shuttle_id wired so that when the
            # dashboard wins the daily reset race (which it
            # reliably does, since it has been running all night
            # while the orchestrator is asleep), cancel_stale_bookings
            # has the Firebase reference it needs to actually clean
            # up yesterday's reserved/active bookings. Without these
            # args the stale-cancel step silently no-ops and stale
            # bookings survive into today.
            bookings_ref = db.reference("bookings") if db is not None else None
            manager = ServiceDayManager(
                db_path="local_database/apcoms.db",
                firebase_sync=firebase_sync,
                bookings_ref=bookings_ref,
                shuttle_id=shuttle_id,
            )
            reset_date = manager.reset_if_needed()
            if reset_date:
                logger.info(
                    f"Service-day reset performed for {reset_date}"
                )
        except Exception as e:
            logger.error(f"Error during service-day check: {e}")

    def _sync_current_state_to_firebase(self, total_capacity=None, force=False):
        """
        Publish the current occupancy snapshot to Firebase immediately.
        This keeps the mobile app and dashboard in sync even when the
        capacity changes without a booking/cancel event firing.
        """
        from firebase_sync import FirebaseSyncComponent
        import os as _os

        if total_capacity is None:
            total_capacity = self._get_total_capacity()

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
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

            cursor.execute(
                "SELECT value FROM system_state WHERE key='available_seats'"
            )
            row = cursor.fetchone()
            sqlite_available_seats = int(row[0]) if row else None

            conn.close()
        except Exception as exc:
            logger.warning(f"Could not read live state for Firebase sync: {exc}")
            return False

        if not force and (
            self._last_published_capacity == total_capacity and
            self._last_published_count == current_count
        ):
            return True

        stops = get_designated_stops("local_database/apcoms.db")
        next_index = (current_stop_index + 1) % len(stops) if stops else 0
        next_stop = stops[next_index] if stops else "Unknown"
        if sqlite_available_seats is not None:
            available_seats = min(sqlite_available_seats, int(total_capacity))
        else:
            available_seats = max(int(total_capacity) - current_count, 0)

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
            firebase_sync = FirebaseSyncComponent(
                shuttle_id=_os.getenv("SHUTTLE_ID", "shuttle_001")
            )
            firebase_sync.initialize()
            firebase_sync.sync_to_firebase(payload)
            self._last_published_capacity = total_capacity
            self._last_published_count = current_count
            return True
        except Exception as exc:
            logger.error(f"Failed to push occupancy snapshot to Firebase: {exc}")
            return False

    def _get_total_capacity(self, db_path="local_database/apcoms.db"):
        """
        Resolve the shuttle total capacity using the same precedence
        as the counting logic: explicit caller value, environment,
        SQLite, then default.
        """
        return get_total_capacity(db_path=db_path, default=20)

    def render_dashboard(self):
        """
        Retrieves current occupancy data, system status, recent
        diagnostic logs and today's summary from SQLite and returns
        them as a dictionary for rendering on the monitoring dashboard.
        """

        # check if we need to perform end-of-day reset
        self.check_end_of_day()

        capacity = self._get_total_capacity()
        self._sync_current_state_to_firebase(total_capacity=capacity, force=False)
        occupancy = {
            "current_count": 0,
            "available_seats": capacity,
            "occupancy_status": "Available",
            "current_stop": "Unknown",
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        system_status = {
            "system_status": "Offline",
            "camera_status": "unknown",
            "fps": 0.0,
            "latency_ms": 0.0
        }

        diagnostic_logs = []

        today_summary = {
            "boardings": 0,
            "alightings": 0,
            "peak_hour": "N/A",
            "most_active_stop": "N/A"
        }

        # Initialize service-hour defaults BEFORE the try block so
        # they're guaranteed to be bound even if the SQLite query
        # path inside the try fails. Without these, an exception in
        # the try silently passes but day_start and day_end are
        # never bound, causing UnboundLocalError when accessed below.
        day_start = "06:00"
        day_end = "24:00"

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            # read system status from system_state
            cursor.execute("SELECT value FROM system_state WHERE key='system_status'")
            row = cursor.fetchone()
            if row:
                system_status["system_status"] = row[0]

            cursor.execute("SELECT value FROM system_state WHERE key='camera_status'")
            row = cursor.fetchone()
            if row:
                system_status["camera_status"] = row[0]

            cursor.execute("SELECT value FROM system_state WHERE key='current_fps'")
            row = cursor.fetchone()
            if row:
                system_status["fps"] = float(row[0])

            cursor.execute("SELECT value FROM system_state WHERE key='current_latency'")
            row = cursor.fetchone()
            if row:
                system_status["latency_ms"] = float(row[0])

            cursor.execute("SELECT value FROM system_state WHERE key='current_count'")
            row = cursor.fetchone()
            if row:
                occupancy["current_count"] = int(row[0])

            cursor.execute("SELECT value FROM system_state WHERE key='available_seats'")
            row = cursor.fetchone()
            if row:
                occupancy["available_seats"] = min(int(row[0]), capacity)
            else:
                occupancy["available_seats"] = capacity

            cursor.execute("SELECT value FROM system_state WHERE key='current_stop'")
            row = cursor.fetchone()
            if row:
                occupancy["current_stop"] = row[0]

            # recalculate occupancy status from actual values
            seats = occupancy["available_seats"]
            if seats > 5:
                occupancy["occupancy_status"] = "Available"
            elif seats >= 1:
                occupancy["occupancy_status"] = "Nearly Full"
            else:
                occupancy["occupancy_status"] = "Full"

            # ── service hours override ──────────────────────────
            # read service hours (default: 06:00 to 24:00)
            cursor.execute("SELECT value FROM system_state WHERE key='day_start_time'")
            row = cursor.fetchone()
            day_start = row[0] if row else "06:00"

            cursor.execute("SELECT value FROM system_state WHERE key='day_end_time'")
            row = cursor.fetchone()
            day_end = row[0] if row else "24:00"

            # parse times
            now = datetime.datetime.now().time()
            start_h, start_m = map(int, day_start.split(":"))
            end_h, end_m = map(int, day_end.split(":"))

            # handle "24:00" as end-of-day (just before midnight)
            if end_h == 24:
                end_h = 23
                end_m = 59

            start_time = datetime.time(start_h, start_m)
            end_time = datetime.time(end_h, end_m)

            in_service = start_time <= now <= end_time

            # override system_status based on service hours
            current_status = system_status["system_status"]

            if not in_service:
                # outside service hours - day is over
                system_status["system_status"] = "Offline"
            elif current_status == "Offline":
                # inside service hours but main.py is not running
                # shuttle is paused at a stop or on a break
                system_status["system_status"] = "At a stop"

            # read diagnostic logs
            cursor.execute("""
                SELECT timestamp, log_type, message, camera_status, fps, latency_ms
                FROM diagnostic_log
                WHERE message != '' AND message IS NOT NULL
                ORDER BY log_id DESC LIMIT 10
            """)
            rows = cursor.fetchall()
            for row in rows:
                diagnostic_logs.append({
                    "timestamp": row[0],
                    "log_type": row[1],
                    "message": row[2],
                    "camera_status": row[3],
                    "fps": row[4],
                    "latency_ms": row[5]
                })

            # today's summary - use last_reset_date as the cutoff so
            # the summary aligns with the current service day.
            cursor.execute(
                "SELECT value FROM system_state WHERE key='last_reset_date'"
            )
            reset_row = cursor.fetchone()
            if reset_row:
                cutoff = reset_row[0]
            else:
                cutoff = datetime.datetime.now().strftime("%Y-%m-%d")

            cursor.execute("""
                SELECT COUNT(*) FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
            """, (cutoff,))
            today_summary["boardings"] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM passenger_events
                WHERE direction = 'alighting' AND timestamp >= ?
            """, (cutoff,))
            today_summary["alightings"] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
                GROUP BY hour ORDER BY count DESC LIMIT 1
            """, (cutoff,))
            peak_row = cursor.fetchone()
            today_summary["peak_hour"] = f"{peak_row[0]}:00" if peak_row else "N/A"

            cursor.execute("""
                SELECT stop_location, COUNT(*) as count
                FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
                GROUP BY stop_location ORDER BY count DESC LIMIT 1
            """, (cutoff,))
            stop_row = cursor.fetchone()
            today_summary["most_active_stop"] = stop_row[0] if stop_row else "N/A"

            conn.close()

        except Exception:
            pass

        display_end = "23:59" if day_end == "24:00" else day_end

        return {
            "occupancy": occupancy,
            "system_status": system_status,
            "diagnostic_logs": diagnostic_logs,
            "today_summary": today_summary,
            "service_hours": {
                "start": day_start,
                "end": display_end,
            },
        }

    def generate_analytics(self, start_date=None, end_date=None, start_time=None, end_time=None):
        """
        Queries the passenger_events table in SQLite to generate
        operational analytics. When date range is provided, filters
        accordingly. Otherwise returns all historical data since
        deployment. Returns summary metrics plus chart-ready datasets
        for shuttle adoption, peak hours, and stop popularity.
        """
        import sqlite3

        total_boardings = 0
        peak_hour = "N/A"
        most_popular_stop = "N/A"
        average_occupancy = 0.0
        adoption_data = {"labels": [], "values": []}
        peak_hours_data = {"labels": [], "values": []}
        stop_popularity_data = {"labels": [], "values": []}
        day_of_week_data = {"labels": [], "values": []}

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            # build optional date filter
            date_filter = ""
            params = []
            if start_date:
                date_filter += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                # add a full day so end_date is inclusive
                date_filter += " AND timestamp <= ?"
                params.append(end_date + " 23:59:59")
                # time-of-day filter applied to EACH day in the range
            if start_time:
                date_filter += " AND strftime('%H:%M', timestamp) >= ?"
                params.append(start_time)
            if end_time:
                date_filter += " AND strftime('%H:%M', timestamp) <= ?"
                params.append(end_time)

            # total boardings (filtered or all-time)
            query = f"SELECT COUNT(*) FROM passenger_events WHERE direction='boarding' {date_filter}"
            cursor.execute(query, params)
            total_boardings = cursor.fetchone()[0]

            # average occupancy
            query = f"SELECT AVG(passenger_count) FROM passenger_events WHERE 1=1 {date_filter}"
            cursor.execute(query, params)
            row = cursor.fetchone()
            average_occupancy = round(row[0], 2) if row[0] else 0.0

            # peak hour
            query = f"""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY hour ORDER BY count DESC LIMIT 1
            """
            cursor.execute(query, params)
            row = cursor.fetchone()
            peak_hour = f"{row[0]}:00" if row else "N/A"

            # most popular stop
            query = f"""
                SELECT stop_location, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY stop_location ORDER BY count DESC LIMIT 1
            """
            cursor.execute(query, params)
            row = cursor.fetchone()
            most_popular_stop = row[0] if row else "N/A"

            #  Graph 1: Shuttle Adoption (boardings per day)
            query = f"""
                SELECT DATE(timestamp) as day, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY day ORDER BY day ASC
            """
            cursor.execute(query, params)
            for day, count in cursor.fetchall():
                adoption_data["labels"].append(day)
                adoption_data["values"].append(count)

            # Graph 2: Peak Hours (boardings per hour)
            # initialize all 24 hours so chart shows full day
            hourly = {f"{h:02d}:00": 0 for h in range(24)}
            query = f"""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY hour
            """
            cursor.execute(query, params)
            for hour, count in cursor.fetchall():
                hourly[f"{hour}:00"] = count
            peak_hours_data["labels"] = list(hourly.keys())
            peak_hours_data["values"] = list(hourly.values())

            # Graph 3: Stop Popularity (boardings per stop)
            query = f"""
                SELECT stop_location, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY stop_location ORDER BY count DESC
            """
            cursor.execute(query, params)
            for stop, count in cursor.fetchall():
                stop_popularity_data["labels"].append(stop)
                stop_popularity_data["values"].append(count)

            # Graph 4: Day-of-Week Pattern (boardings per weekday)
            weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            weekday_counts = {name: 0 for name in weekday_names}

            # SQLite strftime('%w') returns 0=Sunday, 1=Monday, ..., 6=Saturday
            query = f"""
                SELECT strftime('%w', timestamp) as weekday, COUNT(*) as count
                FROM passenger_events
                WHERE direction='boarding' {date_filter}
                GROUP BY weekday
            """
            cursor.execute(query, params)
            sqlite_to_name = {"1": "Monday", "2": "Tuesday", "3": "Wednesday",
                            "4": "Thursday", "5": "Friday", "6": "Saturday", "0": "Sunday"}
            for weekday, count in cursor.fetchall():
                name = sqlite_to_name.get(weekday)
                if name:
                    weekday_counts[name] = count

            day_of_week_data["labels"] = weekday_names
            day_of_week_data["values"] = [weekday_counts[name] for name in weekday_names]

            conn.close()

        except Exception as e:
            logger.error(f"Error generating analytics: {e}")

        return {
            "total_boardings": total_boardings,
            "average_occupancy": average_occupancy,
            "peak_hour": peak_hour,
            "most_popular_stop": most_popular_stop,
            "adoption_data": adoption_data,
            "peak_hours_data": peak_hours_data,
            "stop_popularity_data": stop_popularity_data,
            "day_of_week_data": day_of_week_data
        }

    def export_data(self, start_date=None, end_date=None, start_time=None, end_time=None,
                direction=None, stop_location=None):
        """
        Queries passenger events from SQLite with optional filters
        for date range, time-of-day range, direction and stop location.
        Time filters apply to each day in the date range so admins can
        isolate patterns like morning rush across multiple days.
        Formats data as CSV string for download by administrator.
        Logs success when data is exported.
        Returns CSV formatted string of filtered passenger events.
        """

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "event_id", "shuttle_id", "timestamp",
            "direction", "passenger_count",
            "available_seats", "stop_location"
        ])

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            query = """
                SELECT event_id, shuttle_id, timestamp, direction,
                passenger_count, available_seats, stop_location
                FROM passenger_events WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date + " 23:59:59")

            if start_time:
                query += " AND strftime('%H:%M', timestamp) >= ?"
                params.append(start_time)

            if end_time:
                query += " AND strftime('%H:%M', timestamp) <= ?"
                params.append(end_time)

            if direction:
                query += " AND direction = ?"
                params.append(direction)

            if stop_location:
                query += " AND stop_location = ?"
                params.append(stop_location)

            query += " ORDER BY timestamp ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                writer.writerow(row)
            conn.close()

        except Exception:
            pass

        logger.info("Data exported by administrator")
        return output.getvalue()

    def manage_session(self, session_expiry):
        """
        Checks if the current admin session has expired based on
        the session expiry time. Logs warning and returns expired
        when session times out after 30 minutes of inactivity.
        Returns active if session is still valid.
        """
        import datetime

        if datetime.datetime.now() > session_expiry:
            logger.warning("Session expired, admin logged out")
            return "expired"
        else:
            return "active"

    def handle_alert(self, alert):
        """
        Receives alerts from System Monitor and returns appropriate
        message for display on the monitoring dashboard so administrators
        know exactly what action to take for each alert type.
        """
        alert_type = alert.get("type")

        if alert_type == "camera_alert":
            message = "Camera Error - Check camera connection"
        elif alert_type == "storage_alert":
            message = "Storage Running Low - Archive old logs"
        elif alert_type == "performance_alert":
            message = "Performance Degradation - Check system resources"
        else:
            message = f"Unknown alert: {alert_type}"

        logger.info(f"Alert displayed on dashboard: {message}")
        return message

    def setup_shuttle(self, shuttle_name, total_capacity, designated_stops,
                  day_start_time=None, day_end_time=None):
        """
        Writes shuttle configuration to SQLite system_state table
        so CountingLogic can read updated settings on next startup.
        Validates all fields before writing.
        Service hours (day_start_time, day_end_time) are optional and
        determine when the shuttle is in service for status tracking.
        Returns True on success, False on failure.
        Logs success when shuttle setup is complete.
        """
        import sqlite3
        import json

        # require at least ONE field to be provided (so admin can update partial settings)
        if not any([shuttle_name, total_capacity, designated_stops, day_start_time, day_end_time]):
            logger.warning("Shuttle setup failed - no fields provided")
            return False

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            # only save fields that were actually provided
            if total_capacity:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('total_capacity', ?)
                """, (str(total_capacity),))

                current_count = 0
                try:
                    cursor.execute(
                        "SELECT value FROM system_state WHERE key='current_count'"
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        current_count = int(row[0])
                except Exception:
                    current_count = 0

                available_seats = max(int(str(total_capacity).strip()) - current_count, 0)
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('available_seats', ?)
                """, (str(available_seats),))

            if designated_stops:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('designated_stops', ?)
                """, (json.dumps(designated_stops),))

            if shuttle_name:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('shuttle_name', ?)
                """, (shuttle_name,))

            # save service hours if provided
            if day_start_time:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('day_start_time', ?)
                """, (day_start_time,))

            if day_end_time:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('day_end_time', ?)
                """, (day_end_time,))

            conn.commit()
            conn.close()

            resolved_capacity = None
            if total_capacity is not None and str(total_capacity).strip():
                try:
                    resolved_capacity = int(str(total_capacity).strip())
                except (TypeError, ValueError):
                    resolved_capacity = None
            if resolved_capacity is None:
                resolved_capacity = self._get_total_capacity()

            self._sync_current_state_to_firebase(
                total_capacity=resolved_capacity,
                force=True,
            )
            logger.info("Shuttle setup completed successfully")
            return True

        except Exception:
            logger.error("Shuttle setup failed - database error")
            return False

    def setup_routes(self):
        """
        Configures all Flask URL routes for the dashboard.
        Sets up login, logout, dashboard, analytics and settings routes.
        """
        from flask import render_template, request, redirect, url_for, session

        app = self.app
        app.secret_key = os.getenv("FLASK_SECRET_KEY", "apcoms_secret_key_2026")

        @app.route("/")
        def index():
            if "logged_in" in session:
                return redirect(url_for("dashboard"))
            return redirect(url_for("login"))

        @app.route("/login", methods=["GET", "POST"])
        def login():
            error = None
            if request.method == "POST":
                username = request.form.get("username")
                password = request.form.get("password")
                if self.authenticate(username, password):
                    session["logged_in"] = True
                    session["expiry"] = (
                        __import__("datetime").datetime.now() +
                        __import__("datetime").timedelta(minutes=self.session_timeout)
                    ).isoformat()
                    return redirect(url_for("dashboard"))
                else:
                    if self.account_locked:
                        error = "Account locked. Restart system to unlock."
                    else:
                        error = "Invalid credentials. Please try again."
            return render_template("login.html", error=error)

        @app.route("/logout")
        def logout():
            session.clear()
            return redirect(url_for("login"))

        @app.route("/dashboard")
        def dashboard():
            if "logged_in" not in session:
                return redirect(url_for("login"))
            data = self.render_dashboard()
            analytics = self.generate_analytics()
            # get list of stops for export dropdown and total_capacity
            # for the Settings tab display-only fields
            import sqlite3
            stops = []
            total_capacity = self._get_total_capacity()
            stops = get_designated_stops("local_database/apcoms.db")
            return render_template("dashboard.html",
                                data=data,
                                analytics=analytics,
                                stops=stops,
                                total_capacity=total_capacity)

        @app.route("/export")
        def export():
            if "logged_in" not in session:
                return redirect(url_for("login"))
            from flask import Response
            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")
            direction = request.args.get("direction")
            stop_location = request.args.get("stop_location")
            csv_data = self.export_data(
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                direction=direction,
                stop_location=stop_location
            )
            return Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=apcoms_data.csv"}
            )

        @app.route("/reset_count", methods=["POST"])
        def reset_count():
            """
            Emergency reset of the live passenger count to zero.

            Writes current_count=0 and available_seats=total_capacity
            back to SQLite system_state. Also syncs the new state to
            Firebase so the mobile app reflects the reset immediately.

            Logs a diagnostic entry of severity 'warning' because a
            manual count reset is an operational override worth
            keeping in the audit trail — operators should be able to
            look back later and see when/why a reset happened.

            Historical tables (passenger_events, diagnostic_log) are
            never wiped — those are sacred records.
            """
            if "logged_in" not in session:
                return redirect(url_for("login"))
            from flask import jsonify
            import sqlite3

            try:
                conn = sqlite3.connect("local_database/apcoms.db")
                cursor = conn.cursor()

                total_capacity = self._get_total_capacity()

                # write fresh count + seats
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('current_count', '0')
                    """
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('available_seats', ?)
                    """,
                    (str(total_capacity),),
                )
                conn.commit()
                conn.close()

                # cancel any live reserved/active bookings so the
                # booking stream matches the cleared live counts.
                try:
                    from firebase_admin import db
                    bookings_ref = db.reference("bookings")
                    self._cancel_live_bookings_for_reset(
                        bookings_ref=bookings_ref,
                        shuttle_id=os.getenv("SHUTTLE_ID", "shuttle_001"),
                    )
                except Exception as reset_booking_err:
                    logger.error(
                        f"Failed to cancel live bookings during admin reset: {reset_booking_err}"
                    )

                # write a diagnostic audit log via DataLogger so the
                # reset shows up in the Recent Diagnostic Logs panel
                try:
                    from data_logger import DataLogger
                    import os as _os
                    data_logger = DataLogger(
                        shuttle_id=_os.getenv("SHUTTLE_ID", "shuttle_001")
                    )
                    data_logger.initialize()
                    data_logger.log_diagnostic({
                        "log_type": "warning",
                        "message": (
                            "Manual count reset performed by administrator"
                        ),
                    })
                except Exception as audit_err:
                    logger.error(
                        f"Failed to log reset audit entry: {audit_err}"
                    )

                # push new occupancy to Firebase so mobile app updates.
                # read current_stop from SQLite and compute next_stop
                # from the designated_stops list so Firebase reflects
                # the shuttle's actual location, not a "Unknown" stub.
                try:
                    conn = sqlite3.connect("local_database/apcoms.db")
                    cursor = conn.cursor()

                    cursor.execute(
                        "SELECT value FROM system_state "
                        "WHERE key='current_stop'"
                    )
                    row = cursor.fetchone()
                    current_stop = row[0] if row else "Western Gate"

                    cursor.execute(
                        "SELECT value FROM system_state "
                        "WHERE key='current_stop_index'"
                    )
                    row = cursor.fetchone()
                    current_stop_index = int(row[0]) if row else 0

                    conn.close()

                    stops = get_designated_stops("local_database/apcoms.db")
                    next_index = (current_stop_index + 1) % len(stops)
                    next_stop = stops[next_index]

                    from firebase_sync import FirebaseSyncComponent
                    import os as _os
                    firebase = FirebaseSyncComponent(
                        shuttle_id=_os.getenv("SHUTTLE_ID", "shuttle_001")
                    )
                    firebase.initialize()
                    firebase.sync_to_firebase({
                        "passenger_count": 0,
                        "available_seats": total_capacity,
                        "occupancy_status": "Available",
                        "current_stop": current_stop,
                        "next_stop": next_stop,
                    })
                except Exception as fb_err:
                    logger.error(
                        f"Failed to push reset to Firebase: {fb_err}"
                    )

                logger.info(
                    "Count reset to zero by administrator "
                    f"(available_seats={total_capacity})"
                )
                return jsonify({
                    "status": "success",
                    "message": "Count reset successfully",
                })
            except Exception as e:
                logger.error(f"Reset count failed: {e}")
                return jsonify({
                    "status": "error",
                    "message": str(e),
                }), 500

        @app.route("/setup_shuttle", methods=["POST"])
        def setup_shuttle_route():
            if "logged_in" not in session:
                return redirect(url_for("login"))
            from flask import jsonify, request
            data = request.get_json()
            result = self.setup_shuttle(
                shuttle_name=data.get("shuttle_name"),
                total_capacity=data.get("total_capacity"),
                designated_stops=data.get("designated_stops"),
                day_start_time=data.get("day_start_time"),
                day_end_time=data.get("day_end_time")
            )
            if result:
                return jsonify({"status": "success"})
            return jsonify({"status": "error"})

        @app.route("/api/status")
        def api_status():
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            data = self.render_dashboard()
            return __import__("flask").jsonify(data)

        @app.route("/api/analytics")
        def api_analytics():
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            from flask import request, jsonify
            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")
            analytics = self.generate_analytics(
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time
                )
            return jsonify(analytics)

        @app.route("/api/passenger_events")
        def api_passenger_events():
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            from flask import request, jsonify
            import sqlite3

            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")
            direction = request.args.get("direction")
            stop_location = request.args.get("stop_location")

            events = []
            try:
                conn = sqlite3.connect("local_database/apcoms.db")
                cursor = conn.cursor()

                query = """
                    SELECT event_id, shuttle_id, timestamp, direction,
                        passenger_count, available_seats, stop_location
                    FROM passenger_events WHERE 1=1
                """
                params = []

                if start_date:
                    query += " AND timestamp >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND timestamp <= ?"
                    params.append(end_date + " 23:59:59")
                if start_time:
                    query += " AND strftime('%H:%M', timestamp) >= ?"
                    params.append(start_time)
                if end_time:
                    query += " AND strftime('%H:%M', timestamp) <= ?"
                    params.append(end_time)
                if direction:
                    query += " AND direction = ?"
                    params.append(direction)
                if stop_location:
                    query += " AND stop_location = ?"
                    params.append(stop_location)

                query += " ORDER BY timestamp DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()
                for row in rows:
                    events.append({
                        "event_id": row[0],
                        "shuttle_id": row[1],
                        "timestamp": row[2],
                        "direction": row[3],
                        "passenger_count": row[4],
                        "available_seats": row[5],
                        "stop_location": row[6]
                    })
                conn.close()
            except Exception as e:
                logger.error(f"Error fetching passenger events: {e}")

            return jsonify({"events": events, "total": len(events)})

        @app.route("/api/all_bookings")
        def api_all_bookings():
            """
            Lists every booking belonging to this shuttle for the
            Live Bookings demo tab. Sorted newest-first. Returns
            an empty list if Firebase is unreachable so the tab
            renders gracefully even during outages.

            This route powers a DEMO-ONLY view of bookings and is
            not part of the production dashboard intended for
            shuttle operators. It exists to give a panel viewer
            an at-a-glance window into the booking flow during
            the live demo without needing to open Firebase
            console mid-presentation.
            """
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            from flask import jsonify
            from booking_dashboard_service import BookingDashboardService

            service = BookingDashboardService()
            bookings = service.list_all_bookings()
            return jsonify({"bookings": bookings})

        @app.route("/api/booking_stats")
        def api_booking_stats():
            """
            Live booking statistics for the Monitoring tab cards.
            Returns four booking-activity counts for the shuttle's
            current stop:

              - pickups_expected: count of reserved bookings at
                the current stop (passengers about to scan)
              - boarded_from_here: count of active bookings with
                pickup_stop matching the current stop (passengers
                who have already scanned and boarded)
              - alightings_expected: count of active bookings with
                destination_stop matching the current stop
                (passengers currently onboard expecting to alight)
              - alighted_here: count of completed bookings with
                destination_stop matching the current stop,
                completed during this visit (passengers who have
                actually disembarked at this stop on the current
                shuttle arrival)

            Current stop is read from SQLite system_state where
            it is kept in sync by main.py and the orchestrator.
            Defaults to 'Western Gate' if the shuttle hasn't been
            initialised yet so the dashboard never crashes on a
            fresh deployment.
            """
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            from flask import jsonify
            import sqlite3
            from booking_dashboard_service import BookingDashboardService

            current_stop = "Western Gate"
            try:
                conn = sqlite3.connect("local_database/apcoms.db")
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM system_state WHERE key='current_stop'"
                )
                row = cursor.fetchone()
                if row:
                    current_stop = row[0]
                conn.close()
            except Exception as e:
                logger.error(f"Error reading current_stop: {e}")

            service = BookingDashboardService()
            return jsonify({
                "current_stop": current_stop,
                "pickups_expected": service.get_pickups_expected(current_stop),
                "boarded_from_here": service.get_boarded_from_stop(current_stop),
                "alightings_expected": service.get_alightings_expected(current_stop),
                "alighted_here": service.get_alighted_at_stop(current_stop),
            })

        @app.route("/api/booking_analytics")
        def api_booking_analytics():
            """
            Aggregate booking analytics for the Analytics tab charts:
              - funnel: cumulative booking lifecycle counts
                (total_booked, boarded, completed, cancelled)
              - no_show_rates: per-stop list of total bookings,
                no-show counts, and no-show rate percentage

            Both accept optional start_date and end_date query params
            (YYYY-MM-DD format) which filter bookings by created_at.
            Without filters, all bookings since deployment are counted.

            Both come from the BookingDashboardService which reads
            Firebase directly. The dashboard is online by definition
            so no caching layer is needed for these queries.
            """
            if "logged_in" not in session:
                return __import__("flask").jsonify({"error": "unauthorized"}), 401
            from flask import jsonify, request
            from booking_dashboard_service import BookingDashboardService

            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")

            service = BookingDashboardService()
            return jsonify({
                "funnel": service.get_booking_funnel(
                    start_date=start_date, end_date=end_date
                ),
                "no_show_rates": service.get_no_show_rate_by_stop(
                    start_date=start_date, end_date=end_date
                ),
            })


