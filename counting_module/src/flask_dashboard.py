import logging
import os
from flask import Flask
import sqlite3
import datetime
import sqlite3
import csv
import io

logger = logging.getLogger(__name__)

class FlaskDashboard:

    def __init__(self):
        # explicitly tell Flask where templates are
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.app = Flask(__name__, template_folder=template_dir)
        self.session_timeout = 30
        self.failed_login_attempts = 0
        self.account_locked = False
        self.ngrok_url = None

    def initialize(self):
        """
        Starts the Flask web server and configures ngrok tunnel
        to expose the dashboard publicly. Sets session timeout
        and logs success when dashboard is ready. Falls back to
        local access only if ngrok tunnel fails.
        """
        self.setup_routes()
        try:
            from pyngrok import ngrok
            token = os.getenv("NGROK_AUTH_TOKEN")
            if token:
                ngrok.set_auth_token(token)
            tunnel = ngrok.connect(5000)
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

        logger.info("Flask dashboard initialized successfully")

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

    def check_end_of_day(self):
        """
        Detects when the shuttle's service hours have ended for the day
        and performs end-of-day reset: clears passenger count, resets
        stop index, so the new service day starts fresh.
        Runs on every dashboard refresh but only resets once per day.
        """

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            # read day_end_time (default 24:00)
            cursor.execute("SELECT value FROM system_state WHERE key='day_end_time'")
            row = cursor.fetchone()
            day_end = row[0] if row else "24:00"

            # read last_reset_date
            cursor.execute("SELECT value FROM system_state WHERE key='last_reset_date'")
            row = cursor.fetchone()
            last_reset_date = row[0] if row else None

            # parse day_end
            end_h, end_m = map(int, day_end.split(":"))
            if end_h == 24:
                end_h = 23
                end_m = 59

            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            today_end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

            # figure out the most recent day_end that should have triggered a reset
            if now >= today_end:
                most_recent_end_date = today_str
            else:
                yesterday = now - datetime.timedelta(days=1)
                most_recent_end_date = yesterday.strftime("%Y-%m-%d")

            # if we haven't reset for that day yet, do it now
            if last_reset_date != most_recent_end_date:
                logger.info(f"End of day detected - performing reset for {most_recent_end_date}")

                # reset live state
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('current_count', '0')
                """)

                # read total_capacity to reset available_seats
                cursor.execute("SELECT value FROM system_state WHERE key='total_capacity'")
                cap_row = cursor.fetchone()
                total_capacity = cap_row[0] if cap_row else "20"
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('available_seats', ?)
                """, (total_capacity,))

                # reset stop index back to first stop
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('current_stop_index', '0')
                """)

                # mark that we've reset for this date
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('last_reset_date', ?)
                """, (most_recent_end_date,))

                conn.commit()
                logger.info("End of day reset completed successfully")

            conn.close()

        except Exception as e:
            logger.error(f"Error during end of day check: {e}")

    def render_dashboard(self):
        """
        Retrieves current occupancy data, system status, recent
        diagnostic logs and today's summary from SQLite and returns
        them as a dictionary for rendering on the monitoring dashboard.
        """

        # check if we need to perform end-of-day reset
        self.check_end_of_day()

        occupancy = {
            "current_count": 0,
            "available_seats": 20,
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
                occupancy["available_seats"] = int(row[0])

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

            # today's summary - use last_reset_date as cutoff so summary aligns with service day
            cursor.execute("SELECT value FROM system_state WHERE key='last_reset_date'")
            reset_row = cursor.fetchone()
            if reset_row:
                # use the day after last reset as the start of "today's" service day
                last_reset = datetime.datetime.strptime(reset_row[0], "%Y-%m-%d")
                cutoff = (last_reset + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
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

        return {
            "occupancy": occupancy,
            "system_status": system_status,
            "diagnostic_logs": diagnostic_logs,
            "today_summary": today_summary
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

    def setup_shuttle(self, shuttle_id, shuttle_name, total_capacity, designated_stops,
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
        if not any([shuttle_id, shuttle_name, total_capacity, designated_stops, day_start_time, day_end_time]):
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

            if designated_stops:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('designated_stops', ?)
                """, (json.dumps(designated_stops),))

            if shuttle_id:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value)
                    VALUES ('shuttle_id', ?)
                """, (shuttle_id,))

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
            # get list of stops for export dropdown
            import sqlite3, json
            stops = []
            try:
                conn = sqlite3.connect("local_database/apcoms.db")
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_state WHERE key='designated_stops'")
                row = cursor.fetchone()
                if row:
                    stops = json.loads(row[0])
                conn.close()
            except Exception:
                pass
            # fallback to default stops if not set in system_state
            if not stops:
                stops = [
                    "Western Gate", "CEDAT", "CONAS", "Main Library",
                    "Africa Hall", "Swimming Pool", "Mitchel Hall",
                    "COCIS", "Complex Hall", "CEES", "Lumumba Hall"
                ]
            return render_template("dashboard.html",
                                data=data,
                                analytics=analytics,
                                stops=stops)

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
            if "logged_in" not in session:
                return redirect(url_for("login"))
            from flask import jsonify
            logger.info("Count reset by administrator")
            return jsonify({"status": "success", "message": "Count reset successfully"})

        @app.route("/setup_shuttle", methods=["POST"])
        def setup_shuttle_route():
            if "logged_in" not in session:
                return redirect(url_for("login"))
            from flask import jsonify, request
            data = request.get_json()
            result = self.setup_shuttle(
                shuttle_id=data.get("shuttle_id"),
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


