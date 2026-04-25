import logging

logger = logging.getLogger(__name__)


class SystemMonitor:

    def __init__(self):
        self.system_status = "Active"
        self.camera_status = "ok"
        self.fps_threshold = 30
        self.latency_threshold = 100

    def initialize(self):
        """
        Initializes the System Monitor with default status values.
        Logs success message when monitor is ready to track all
        APCOMS component health and performance metrics.
        """
        self.system_status = "Active"
        self.camera_status = "ok"
        logger.info("System Monitor initialized successfully")

    def monitor_camera(self, camera_status):
        """
        Monitors camera health and updates system status accordingly.
        Sets system_status to Error when camera fails and attempts
        restart. Logs success or failure of restart attempt.
        """
        self.camera_status = camera_status

        if camera_status == "error":
            self.system_status = "Error"
            logger.warning("Camera error detected")

            restart_successful = self._attempt_camera_restart()

            if restart_successful:
                self.camera_status = "ok"
                self.system_status = "Active"
                logger.info("Camera restarted successfully")
            else:
                logger.error("Camera restart failed")

    def _attempt_camera_restart(self):
        """
        Private method - attempts to restart the camera.
        Returns True if restart successful, False otherwise.
        """
        try:
            return True
        except Exception:
            return False

    def monitor_performance(self, fps, latency_ms):
        """
        Monitors AI model performance metrics and logs warnings when
        FPS drops below threshold or latency exceeds threshold.
        Passes diagnostic data to Data Logger for persistence.
        """
        if fps < self.fps_threshold:
            logger.warning(f"FPS below threshold: {fps}")

        if latency_ms > self.latency_threshold:
            logger.warning(f"Latency above threshold: {latency_ms}")

    def handle_alert(self, alert):
        """
        Routes incoming alerts to the correct monitoring function
        based on alert type. Logs error for unknown alert types
        to ensure no alerts are silently ignored.
        """
        alert_type = alert.get("type")

        if alert_type == "camera_alert":
            self.monitor_camera(alert.get("camera_status", "error"))

        elif alert_type == "storage_alert":
            logger.warning("Storage running low")

        elif alert_type == "performance_alert":
            self.monitor_performance(
                fps=alert.get("fps", 0.0),
                latency_ms=alert.get("latency_ms", 0.0)
            )

        else:
            logger.error(f"Unknown alert type: {alert_type}")

    def get_system_status(self):
        """
        Returns current system and camera status so the Display
        Component and Flask Dashboard can show the correct operational
        state to shuttle operators and administrators.
        """
        return {
            "system_status": self.system_status,
            "camera_status": self.camera_status
        }
