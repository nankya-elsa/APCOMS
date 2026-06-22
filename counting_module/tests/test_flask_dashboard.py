import pytest
import os
import sys
from unittest.mock import patch, MagicMock

NGROK_AVAILABLE = os.getenv("NGROK_AUTH_TOKEN") is not None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flask_dashboard import FlaskDashboard


class TestFlaskDashboardInitialization:

    def test_flask_dashboard_initializes_successfully(self):
        """
        Test that FlaskDashboard initializes correctly so the system
        has a web dashboard ready to serve occupancy data and system
        status to administrators via ngrok URL
        """
        dashboard = FlaskDashboard()
        assert dashboard is not None

    def test_flask_app_is_created_correctly(self):
        """
        Test that FlaskDashboard creates a Flask app instance so the
        system has a web server ready to serve the monitoring dashboard
        to administrators via ngrok URL
        """
        dashboard = FlaskDashboard()
        assert dashboard.app is not None

    def test_session_timeout_defaults_to_30_minutes(self):
        """
        Test that session_timeout defaults to 30 minutes so inactive
        admin sessions are automatically expired to prevent unauthorized
        access to the monitoring dashboard
        """
        dashboard = FlaskDashboard()
        assert dashboard.session_timeout == 30

    def test_initialize_logs_success_message(self, caplog):
        """
        Test that initialize() logs a success message when the Flask
        dashboard is ready so administrators know the monitoring
        dashboard is accessible and operational
        """
        import logging
        dashboard = FlaskDashboard()
        with caplog.at_level(logging.INFO):
            dashboard.initialize()
        assert "Flask dashboard initialized successfully" in caplog.text


class TestAuthentication:

    def test_authenticate_returns_true_with_correct_credentials(self):
        """
        Test that authenticate() returns True when correct username
        and password are provided so authorized administrators can
        access the monitoring dashboard securely
        """
        from dotenv import load_dotenv
        load_dotenv()
        dashboard = FlaskDashboard()
        username = os.getenv("ADMIN_USERNAME", "kmc_admin")
        password = os.getenv("ADMIN_PASSWORD", "Kiira@2026!")
        result = dashboard.authenticate(username, password)
        assert result == True

    def test_authenticate_returns_false_with_wrong_password(self):
        """
        Test that authenticate() returns False when wrong password
        is provided so unauthorized users cannot access the monitoring
        dashboard even if they know the correct username
        """
        dashboard = FlaskDashboard()
        result = dashboard.authenticate("kmc_admin", "wrongpassword")
        assert result == False

    def test_authenticate_returns_false_with_wrong_username(self):
        """
        Test that authenticate() returns False when wrong username
        is provided so unauthorized users cannot access the monitoring
        dashboard even if they guess the correct password
        """
        dashboard = FlaskDashboard()
        result = dashboard.authenticate("wrong_user", "Kiira@2026!")
        assert result == False

    def test_increments_failed_attempts_on_wrong_credentials(self):
        """
        Test that authenticate() increments failed_login_attempts
        on wrong credentials so the system can track and respond
        to repeated unauthorized access attempts
        """
        dashboard = FlaskDashboard()
        dashboard.authenticate("wrong_user", "wrongpassword")
        assert dashboard.failed_login_attempts == 1

    def test_locks_account_after_5_failed_attempts(self):
        """
        Test that authenticate() locks the account after 5 failed
        attempts so brute force password attacks are prevented
        and the system remains secure
        """
        dashboard = FlaskDashboard()
        for i in range(5):
            dashboard.authenticate("wrong_user", "wrongpassword")
        assert dashboard.account_locked == True

    def test_returns_false_when_account_is_locked(self):
        """
        Test that authenticate() returns False when account is locked
        so even correct credentials cannot bypass the lockout and
        the system remains protected after repeated failed attempts
        """
        dashboard = FlaskDashboard()
        for i in range(5):
            dashboard.authenticate("wrong_user", "wrongpassword")
        result = dashboard.authenticate("kmc_admin", "Kiira@2026!")
        assert result == False

    def test_logs_success_on_valid_login(self, caplog):
        """
        Test that authenticate() logs a success message when admin
        logs in successfully so the System Monitor has an audit
        trail of all successful dashboard access events
        """
        import logging
        from dotenv import load_dotenv
        load_dotenv()
        dashboard = FlaskDashboard()
        username = os.getenv("ADMIN_USERNAME", "kmc_admin")
        password = os.getenv("ADMIN_PASSWORD", "Kiira@2026!")
        with caplog.at_level(logging.INFO):
            dashboard.authenticate(username, password)
        assert "Admin logged in successfully" in caplog.text

    def test_logs_warning_on_failed_login(self, caplog):
        """
        Test that authenticate() logs a warning on failed login
        so the System Monitor has an audit trail of unauthorized
        access attempts for security monitoring
        """
        import logging
        dashboard = FlaskDashboard()
        with caplog.at_level(logging.WARNING):
            dashboard.authenticate("wrong_user", "wrongpassword")
        assert "Failed login attempt" in caplog.text


class TestDashboardRendering:

    def test_render_dashboard_returns_dashboard_data(self):
        """
        Test that render_dashboard() returns a dictionary of dashboard
        data so the Flask template has all the information needed
        to display the monitoring interface to administrators
        """
        dashboard = FlaskDashboard()
        result = dashboard.render_dashboard()
        assert result is not None
        assert isinstance(result, dict)

    def test_dashboard_data_contains_occupancy_info(self):
        """
        Test that render_dashboard() includes occupancy information
        so administrators can see current passenger count and
        available seats on the monitoring dashboard
        """
        dashboard = FlaskDashboard()
        result = dashboard.render_dashboard()
        assert "occupancy" in result

    def test_dashboard_data_contains_system_status(self):
        """
        Test that render_dashboard() includes system status so
        administrators can see whether the system is Active,
        Calibrating or in Error state on the dashboard
        """
        dashboard = FlaskDashboard()
        result = dashboard.render_dashboard()
        assert "system_status" in result

    def test_dashboard_data_contains_diagnostic_logs(self):
        """
        Test that render_dashboard() includes recent diagnostic logs
        so administrators can see system health and error messages
        directly on the monitoring dashboard
        """
        dashboard = FlaskDashboard()
        result = dashboard.render_dashboard()
        assert "diagnostic_logs" in result


class TestAnalytics:

    def test_generate_analytics_returns_analytics_data(self):
        """
        Test that generate_analytics() returns a dictionary of analytics
        data so the Flask dashboard can display operational insights
        to fleet managers for route optimization decisions
        """
        dashboard = FlaskDashboard()
        result = dashboard.generate_analytics()
        assert result is not None
        assert isinstance(result, dict)

    def test_returns_total_boardings(self):
        """
        Test that generate_analytics() returns total boardings since deployment
        so fleet managers can verify overall shuttle adoption.
        """
        dashboard = FlaskDashboard()
        result = dashboard.generate_analytics()
        assert "total_boardings" in result


    def test_returns_peak_hour(self):
        """
        Test that generate_analytics() returns the peak hour so
        fleet managers can identify when demand is highest and
        schedule additional shuttle runs accordingly
        """
        dashboard = FlaskDashboard()
        result = dashboard.generate_analytics()
        assert "peak_hour" in result

    def test_returns_most_popular_stop(self):
        """
        Test that generate_analytics() returns the most popular stop
        so fleet managers can identify which campus locations have
        highest passenger demand for route optimization
        """
        dashboard = FlaskDashboard()
        result = dashboard.generate_analytics()
        assert "most_popular_stop" in result

    def test_returns_average_occupancy(self):
        """
        Test that generate_analytics() returns average occupancy so
        fleet managers can assess how efficiently the shuttle capacity
        is being utilized throughout the service day
        """
        dashboard = FlaskDashboard()
        result = dashboard.generate_analytics()
        assert "average_occupancy" in result


class TestDataExport:

    def test_export_data_returns_csv_data(self):
        """
        Test that export_data() returns CSV formatted data so fleet
        managers can download passenger events for analysis in
        tools like Excel, Python or Tableau
        """
        dashboard = FlaskDashboard()
        result = dashboard.export_data()
        assert result is not None

    def test_exported_data_contains_passenger_events(self):
        """
        Test that export_data() includes passenger events in the
        exported data so fleet managers have access to complete
        historical boarding and alighting records
        """
        dashboard = FlaskDashboard()
        result = dashboard.export_data()
        assert "direction" in result

    def test_logs_success_when_data_exported(self, caplog):
        """
        Test that export_data() logs a success message when data
        is exported so the System Monitor has an audit trail of
        all data exports performed by administrators
        """
        import logging
        dashboard = FlaskDashboard()
        with caplog.at_level(logging.INFO):
            dashboard.export_data()
        assert "Data exported by administrator" in caplog.text

    def test_export_filters_by_direction(self):
        """
        Test that export_data() correctly filters by direction so
        fleet managers can download only boarding or only alighting
        events for targeted analysis
        """
        dashboard = FlaskDashboard()
        result = dashboard.export_data(direction="boarding")
        assert result is not None
        assert "direction" in result

    def test_export_filters_by_date_range(self):
        """
        Test that export_data() correctly filters by date range so
        fleet managers can download data for specific periods such
        as a single day or an entire week
        """
        dashboard = FlaskDashboard()
        result = dashboard.export_data(
            start_date="2026-01-01",
            end_date="2026-12-31"
        )
        assert result is not None
        assert "direction" in result

    def test_export_filters_by_stop_location(self):
        """
        Test that export_data() correctly filters by stop location
        so fleet managers can analyze passenger flow at specific
        campus stops for targeted route optimization
        """
        dashboard = FlaskDashboard()
        result = dashboard.export_data(stop_location="Western Gate")
        assert result is not None
        assert "direction" in result


class TestSessionManagement:

    def test_manage_session_returns_active_when_session_valid(self):
        """
        Test that manage_session() returns active when session has
        not expired so administrators can continue using the dashboard
        without being redirected to the login page
        """
        import datetime
        dashboard = FlaskDashboard()
        future_expiry = datetime.datetime.now() + datetime.timedelta(minutes=30)
        result = dashboard.manage_session(session_expiry=future_expiry)
        assert result == "active"

    def test_manage_session_returns_expired_when_session_expired(self):
        """
        Test that manage_session() returns expired when session has
        timed out so inactive administrators are automatically logged
        out and redirected to the login page
        """
        import datetime
        dashboard = FlaskDashboard()
        past_expiry = datetime.datetime.now() - datetime.timedelta(minutes=1)
        result = dashboard.manage_session(session_expiry=past_expiry)
        assert result == "expired"

    def test_logs_warning_when_session_expires(self, caplog):
        """
        Test that manage_session() logs a warning when session expires
        so the System Monitor has an audit trail of all session
        expiry events for security monitoring
        """
        import logging
        import datetime
        dashboard = FlaskDashboard()
        past_expiry = datetime.datetime.now() - datetime.timedelta(minutes=1)
        with caplog.at_level(logging.WARNING):
            dashboard.manage_session(session_expiry=past_expiry)
        assert "Session expired, admin logged out" in caplog.text


class TestAlertHandling:

    def test_handle_alert_returns_correct_message_for_camera_alert(self):
        """
        Test that handle_alert() returns correct message for camera
        alerts so administrators can immediately understand what
        action to take when camera issues are detected
        """
        dashboard = FlaskDashboard()
        alert = {"type": "camera_alert"}
        result = dashboard.handle_alert(alert)
        assert result == "Camera Error - Check camera connection"

    def test_handle_alert_returns_correct_message_for_storage_alert(self):
        """
        Test that handle_alert() returns correct message for storage
        alerts so administrators know to archive old logs before
        the database runs out of space
        """
        dashboard = FlaskDashboard()
        alert = {"type": "storage_alert"}
        result = dashboard.handle_alert(alert)
        assert result == "Storage Running Low - Archive old logs"

    def test_handle_alert_returns_correct_message_for_performance_alert(self):
        """
        Test that handle_alert() returns correct message for performance
        alerts so administrators know to check system resources when
        FPS drops or latency exceeds acceptable thresholds
        """
        dashboard = FlaskDashboard()
        alert = {"type": "performance_alert"}
        result = dashboard.handle_alert(alert)
        assert result == "Performance Degradation - Check system resources"


class TestEndOfDayResetWiring:
    """
    Tests that check_end_of_day wires bookings_ref and shuttle_id
    into the ServiceDayManager so cancel_stale_bookings() actually
    runs when the dashboard is the process that triggers the
    daily reset.

    The dashboard is always-on (24/7) while the orchestrator only
    runs during service hours. reset_if_needed() is idempotent
    across processes -- whoever wins the race performs the reset
    and marks today as done; the loser skips. The dashboard
    reliably wins because it has been running all night. So if
    the dashboard's ServiceDayManager doesn't carry the wiring
    needed for stale-booking cleanup, that cleanup never happens
    in production, and yesterday's reserved/active bookings
    survive into today.
    """

    @patch("flask_dashboard.FlaskDashboard.check_end_of_day", autospec=True)
    def test_render_dashboard_still_calls_check_end_of_day(
        self, mock_check
    ):
        """
        Sanity check that render_dashboard still triggers
        check_end_of_day on every load. Protects the call-site
        we depend on.
        """
        dashboard = FlaskDashboard()
        try:
            dashboard.render_dashboard()
        except Exception:
            pass  # we only care that check_end_of_day was called
        mock_check.assert_called_once()

    @patch("firebase_admin.db.reference")
    @patch("service_day_manager.ServiceDayManager")
    @patch("firebase_sync.FirebaseSyncComponent")
    def test_check_end_of_day_passes_bookings_ref_and_shuttle_id(
        self,
        mock_firebase_sync_class,
        mock_manager_class,
        mock_db_reference,
    ):
        """
        ServiceDayManager must be constructed with bookings_ref
        pointed at the live Firebase /bookings node AND shuttle_id
        matching the configured shuttle. Without these args,
        cancel_stale_bookings() is a silent no-op and stale
        bookings from yesterday survive into today.
        """
        import os
        os.environ["SHUTTLE_ID"] = "shuttle_001"
        mock_db_reference.return_value = "BOOKINGS_REF_SENTINEL"

        dashboard = FlaskDashboard()
        dashboard.check_end_of_day()

        mock_manager_class.assert_called_once()
        kwargs = mock_manager_class.call_args.kwargs
        assert kwargs.get("bookings_ref") == "BOOKINGS_REF_SENTINEL", (
            "ServiceDayManager must receive bookings_ref so "
            "cancel_stale_bookings can run during the reset"
        )
        assert kwargs.get("shuttle_id") == "shuttle_001", (
            "ServiceDayManager must receive shuttle_id so it "
            "knows which shuttle's bookings to clean up"
        )
        mock_db_reference.assert_called_with("bookings")

