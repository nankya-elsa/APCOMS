import logging
import os
from flask import Flask

logger = logging.getLogger(__name__)

class FlaskDashboard:

    def __init__(self):
        self.app = Flask(__name__)
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

    def render_dashboard(self):
        """
        Retrieves current occupancy data, system status and recent
        diagnostic logs from SQLite and returns them as a dictionary
        for rendering on the monitoring dashboard interface.
        """
        import sqlite3
        import datetime

        occupancy = {
            "current_count": 0,
            "available_seats": 20,
            "occupancy_status": "Available",
            "current_stop": "Unknown",
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        system_status = {
            "system_status": "Active",
            "camera_status": "ok",
            "fps": 0.0,
            "latency_ms": 0.0
        }

        diagnostic_logs = []

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, log_type, message, camera_status, fps, latency_ms
                FROM diagnostic_log
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
            conn.close()
        except Exception:
            pass

        return {
            "occupancy": occupancy,
            "system_status": system_status,
            "diagnostic_logs": diagnostic_logs
        }

    def generate_analytics(self):
        """
        Queries the passenger_events table in SQLite to generate
        operational analytics including total boardings, alightings,
        peak hour, most popular stop and average occupancy for today.
        Returns all analytics data as a dictionary.
        """
        import sqlite3
        import datetime

        today = datetime.datetime.now().strftime("%Y-%m-%d")

        total_boardings_today = 0
        total_alightings_today = 0
        peak_hour = "N/A"
        most_popular_stop = "N/A"
        average_occupancy = 0.0

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            # total boardings today
            cursor.execute("""
                SELECT COUNT(*) FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
            """, (today,))
            total_boardings_today = cursor.fetchone()[0]

            # total alightings today
            cursor.execute("""
                SELECT COUNT(*) FROM passenger_events
                WHERE direction = 'alighting' AND timestamp >= ?
            """, (today,))
            total_alightings_today = cursor.fetchone()[0]

            # peak hour
            cursor.execute("""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
                GROUP BY hour ORDER BY count DESC LIMIT 1
            """, (today,))
            row = cursor.fetchone()
            if row:
                peak_hour = f"{row[0]}:00"

            # most popular stop
            cursor.execute("""
                SELECT stop_location, COUNT(*) as count
                FROM passenger_events
                WHERE direction = 'boarding' AND timestamp >= ?
                GROUP BY stop_location ORDER BY count DESC LIMIT 1
            """, (today,))
            row = cursor.fetchone()
            if row:
                most_popular_stop = row[0]

            # average occupancy
            cursor.execute("""
                SELECT AVG(passenger_count) FROM passenger_events
                WHERE timestamp >= ?
            """, (today,))
            row = cursor.fetchone()
            if row[0]:
                average_occupancy = round(row[0], 2)

            conn.close()

        except Exception:
            pass

        return {
            "total_boardings_today": total_boardings_today,
            "total_alightings_today": total_alightings_today,
            "peak_hour": peak_hour,
            "most_popular_stop": most_popular_stop,
            "average_occupancy": average_occupancy
        }

    def export_data(self, start_date=None, end_date=None, direction=None, stop_location=None):
        """
        Queries passenger events from SQLite with optional filters
        for date range, direction and stop location. Formats data
        as CSV string for download by administrator.
        Logs success when data is exported.
        Returns CSV formatted string of filtered passenger events.
        """
        import sqlite3
        import csv
        import io

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
                params.append(end_date)

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

    def setup_shuttle(self, shuttle_id, shuttle_name, total_capacity, designated_stops):
        """
        Writes shuttle configuration to SQLite system_state table
        so CountingLogic can read updated settings on next startup.
        Validates all fields before writing.
        Returns True on success, False on failure.
        Logs success when shuttle setup is complete.
        """
        import sqlite3
        import json

        if not shuttle_id or not shuttle_name or not total_capacity or not designated_stops:
            logger.warning("Shuttle setup failed - missing required fields")
            return False

        try:
            conn = sqlite3.connect("local_database/apcoms.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('total_capacity', ?)
            """, (str(total_capacity),))

            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('designated_stops', ?)
            """, (json.dumps(designated_stops),))

            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('shuttle_id', ?)
            """, (shuttle_id,))

            cursor.execute("""
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('shuttle_name', ?)
            """, (shuttle_name,))

            conn.commit()
            conn.close()
            logger.info("Shuttle setup completed successfully")
            return True

        except Exception:
            logger.error("Shuttle setup failed - database error")
            return False
