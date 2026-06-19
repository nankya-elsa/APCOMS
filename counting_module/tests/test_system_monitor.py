import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from system_monitor import SystemMonitor


class TestSystemMonitorInitialization:

    def test_system_monitor_initializes_successfully(self):
        """
        Test that SystemMonitor initializes correctly so the system
        has a monitor ready to track health and performance of all
        APCOMS components
        """
        monitor = SystemMonitor()
        assert monitor is not None

    def test_system_status_defaults_to_active(self):
        """
        Test that system_status defaults to Active on initialization
        to confirm the system assumes everything is working correctly
        until a component reports an error
        """
        monitor = SystemMonitor()
        assert monitor.system_status == "Active"

    def test_camera_status_defaults_to_ok(self):
        """
        Test that camera_status defaults to ok on initialization to
        confirm the system assumes the camera is working correctly
        until the Camera Interface reports an error
        """
        monitor = SystemMonitor()
        assert monitor.camera_status == "ok"

    def test_fps_threshold_defaults_to_5(self):
        """
        Test that fps_threshold defaults to 5 FPS to match what is
        realistic for CPU-based laptop deployment of YOLOv8n. The
        original SRS specified 30 FPS assuming GPU acceleration; on
        a CPU the achievable rate sits around 7-15 FPS during normal
        operation, so a 30 FPS threshold flooded the diagnostic log
        with false-positive warnings. 5 FPS is a real floor -- if
        the model genuinely cannot maintain 5 FPS, something is
        wrong (model lag, swap thrashing, hardware failure).
        """
        monitor = SystemMonitor()
        assert monitor.fps_threshold == 5

    def test_latency_threshold_defaults_to_250(self):
        """
        Test that latency_threshold defaults to 250ms to match what
        is realistic for CPU-based laptop deployment of YOLOv8n. The
        original NFR-CM-1.4 specified 100ms assuming GPU acceleration;
        on a CPU normal per-frame inference takes 100-180ms. 250ms
        is the realistic ceiling for our deployment -- anything above
        that signals a real problem.
        """
        monitor = SystemMonitor()
        assert monitor.latency_threshold == 250

    def test_initialize_logs_success_message(self, caplog):
        """
        Test that initialize() logs a success message to confirm
        the System Monitor is ready to track health and performance
        of all APCOMS components
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.INFO):
            monitor.initialize()
        assert "System Monitor initialized successfully" in caplog.text


class TestCameraMonitoring:

    def test_sets_system_status_to_error_when_camera_fails(self):
        """
        Test that monitor_camera() sets system_status to Error when
        camera_status is error so the Display Component shows the
        correct error state to shuttle operators
        """
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: False
        monitor.monitor_camera("error")
        assert monitor.system_status == "Error"

    def test_logs_warning_when_camera_error_detected(self, caplog):
        """
        Test that monitor_camera() logs a warning when camera error
        is detected so the System Monitor has an audit trail of
        camera failures for maintenance analysis
        """
        import logging
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: False
        with caplog.at_level(logging.WARNING):
            monitor.monitor_camera("error")
        assert "Camera error detected" in caplog.text

    def test_sets_system_status_to_active_after_successful_restart(self):
        """
        Test that monitor_camera() sets system_status back to Active
        after a successful camera restart so the system resumes normal
        operation without manual intervention
        """
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: True
        monitor.monitor_camera("error")
        assert monitor.system_status == "Active"

    def test_sets_camera_status_to_ok_after_successful_restart(self):
        """
        Test that monitor_camera() sets camera_status back to ok after
        a successful restart so all components know the camera is
        operational again
        """
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: True
        monitor.monitor_camera("error")
        assert monitor.camera_status == "ok"

    def test_logs_success_when_camera_restarted(self, caplog):
        """
        Test that monitor_camera() logs success when camera restarts
        successfully so the System Monitor has an audit trail of
        camera recovery events for maintenance analysis
        """
        import logging
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: True
        with caplog.at_level(logging.INFO):
            monitor.monitor_camera("error")
        assert "Camera restarted successfully" in caplog.text


class TestPerformanceMonitoring:

    def test_logs_warning_when_fps_below_threshold(self, caplog):
        """
        Test that monitor_performance() logs a warning when FPS drops
        below the new 5 FPS threshold so the System Monitor can alert
        maintenance personnel of performance degradation affecting
        counting accuracy.
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.WARNING):
            monitor.monitor_performance(fps=3.0, latency_ms=200.0)
        assert "FPS below threshold" in caplog.text

    def test_logs_warning_when_latency_above_threshold(self, caplog):
        """
        Test that monitor_performance() logs a warning when latency
        exceeds the new 250ms threshold so the System Monitor can
        alert maintenance personnel of performance degradation.
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.WARNING):
            monitor.monitor_performance(fps=10.0, latency_ms=300.0)
        assert "Latency above threshold" in caplog.text

    def test_does_not_log_warning_when_performance_is_normal(self, caplog):
        """
        Test that monitor_performance() does not log warnings when
        FPS and latency are within acceptable limits to avoid
        unnecessary alerts during normal system operation
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.WARNING):
            monitor.monitor_performance(fps=30.0, latency_ms=35.0)
        assert "FPS below threshold" not in caplog.text
        assert "Latency above threshold" not in caplog.text

    def test_fps_warning_is_rate_limited(self, caplog):
        """
        Test that repeated FPS-below-threshold warnings within the
        rate-limit window only produce ONE log entry, not one per
        call. Previously the terminal flooded with 100+ FPS warnings
        per minute during a single main.py run, drowning out
        meaningful diagnostic signal. The rate limit was already
        applied to the SQLite write but not to the in-memory logger
        -- this test ensures the logger gate kicks in too.
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.WARNING):
            # fire the warning condition five times back-to-back
            for _ in range(5):
                monitor.monitor_performance(fps=2.0, latency_ms=50.0)
        # exactly one warning -- subsequent calls within the
        # rate-limit window must be suppressed
        warning_count = caplog.text.count("FPS below threshold")
        assert warning_count == 1, (
            f"Expected 1 FPS warning within rate-limit window, "
            f"got {warning_count}"
        )

    def test_latency_warning_is_rate_limited(self, caplog):
        """
        Mirror of test_fps_warning_is_rate_limited but for the
        latency-above-threshold warning. Same problem, same fix.
        """
        import logging
        monitor = SystemMonitor()
        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                monitor.monitor_performance(fps=10.0, latency_ms=400.0)
        warning_count = caplog.text.count("Latency above threshold")
        assert warning_count == 1, (
            f"Expected 1 latency warning within rate-limit window, "
            f"got {warning_count}"
        )


class TestAlertHandling:

    def test_routes_camera_alert_to_monitor_camera(self, caplog):
        """
        Test that handle_alert() correctly routes camera alerts to
        monitor_camera() so camera errors are handled by the right
        function without manual intervention
        """
        import logging
        monitor = SystemMonitor()
        monitor._attempt_camera_restart = lambda: False
        alert = {"type": "camera_alert", "camera_status": "error"}
        with caplog.at_level(logging.WARNING):
            monitor.handle_alert(alert)
        assert "Camera error detected" in caplog.text

    def test_routes_storage_alert_correctly(self, caplog):
        """
        Test that handle_alert() correctly handles storage alerts
        so administrators are notified when storage is running low
        """
        import logging
        monitor = SystemMonitor()
        alert = {"type": "storage_alert"}
        with caplog.at_level(logging.WARNING):
            monitor.handle_alert(alert)
        assert "Storage running low" in caplog.text

    def test_routes_performance_alert_to_monitor_performance(self, caplog):
        """
        Test that handle_alert() correctly routes performance alerts
        to monitor_performance() so FPS and latency issues are handled
        by the right function
        """
        import logging
        monitor = SystemMonitor()
        alert = {"type": "performance_alert", "fps": 3.0, "latency_ms": 35.0}
        with caplog.at_level(logging.WARNING):
            monitor.handle_alert(alert)
        assert "FPS below threshold" in caplog.text

    def test_logs_error_for_unknown_alert_type(self, caplog):
        """
        Test that handle_alert() logs an error for unknown alert types
        so the System Monitor never silently ignores unexpected alerts
        from any APCOMS component
        """
        import logging
        monitor = SystemMonitor()
        alert = {"type": "unknown_alert"}
        with caplog.at_level(logging.ERROR):
            monitor.handle_alert(alert)
        assert "Unknown alert type" in caplog.text


class TestGetSystemStatus:

    def test_get_system_status_returns_system_status(self):
        """
        Test that get_system_status() returns the current system_status
        so the Display Component and Flask Dashboard can show the
        correct operational state to operators and administrators
        """
        monitor = SystemMonitor()
        status = monitor.get_system_status()
        assert status["system_status"] == "Active"

    def test_get_system_status_returns_camera_status(self):
        """
        Test that get_system_status() returns the current camera_status
        so the Display Component can show operators whether the camera
        is functioning correctly
        """
        monitor = SystemMonitor()
        status = monitor.get_system_status()
        assert status["camera_status"] == "ok"


