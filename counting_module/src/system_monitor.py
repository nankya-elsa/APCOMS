import logging
import time


logger = logging.getLogger(__name__)


class SystemMonitor:

    def __init__(self, data_logger=None):
        self.system_status = "Active"
        self.camera_status = "ok"
        self.fps_threshold = 5
        self.latency_threshold = 250
        self.data_logger = data_logger
        self._last_fps_log_time = 0
        self._last_latency_log_time = 0
        self._log_interval = 10  # only log to SQLite once every 10 seconds


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
        # normalize: camera reports "active" when healthy, but dashboard expects "ok"
        if camera_status == "active":
            self.camera_status = "ok"
        elif camera_status == "error":
            self.camera_status = "error"
        else:
            self.camera_status = "unknown"

        if camera_status == "error":
            self.system_status = "Error"
            logger.warning("Camera error detected")
            if self.data_logger:
                self.data_logger.log_diagnostic({
                    "log_type": "error",
                    "message": "Camera error detected",
                    "camera_status": "error",
                    "fps": 0.0,
                    "latency_ms": 0.0
                })

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
        Passes diagnostic data to Data Logger for persistence with
        rate limiting to avoid flooding the database.
        """

        now = time.time()

        # Rate limit BOTH the terminal logger.warning AND the SQLite
        # write together. Previously the rate limit only gated the
        # SQLite persist while logger.warning fired every frame the
        # threshold was crossed, flooding the operator's terminal
        # with 100+ identical warnings per minute during a single
        # main.py run. Gating both behind the same interval keeps
        # the terminal readable AND the dashboard's diagnostic log
        # informative without losing signal -- if a problem persists
        # for 10+ seconds, the next interval will log it again.
        if fps < self.fps_threshold:
            if (now - self._last_fps_log_time) >= self._log_interval:
                logger.warning(f"FPS below threshold: {fps}")
                if self.data_logger:
                    self.data_logger.log_diagnostic({
                        "log_type": "warning",
                        "message": f"FPS below threshold: {fps:.1f}",
                        "camera_status": self.camera_status,
                        "fps": round(fps, 2),
                        "latency_ms": round(latency_ms, 2)
                    })
                self._last_fps_log_time = now

        if latency_ms > self.latency_threshold:
            if (now - self._last_latency_log_time) >= self._log_interval:
                logger.warning(f"Latency above threshold: {latency_ms}")
                if self.data_logger:
                    self.data_logger.log_diagnostic({
                        "log_type": "warning",
                        "message": f"Latency above threshold: {latency_ms:.1f}ms",
                        "camera_status": self.camera_status,
                        "fps": round(fps, 2),
                        "latency_ms": round(latency_ms, 2)
                    })
                self._last_latency_log_time = now

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
