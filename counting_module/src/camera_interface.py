import cv2
import logging
import time

logger = logging.getLogger(__name__)


class CameraInterface:
    """
    Manages video capture from either a video file or webcam source.
    Provides frame capture, health monitoring, and status tracking
    for the APCOMS passenger counting pipeline.
    """

    def __init__(self, source):
        """
        Initializes the camera with the given source.
        Source can be a video file path (str) or webcam index (int).
        Raises ValueError if source is None.
        """
        if source is None:
            raise ValueError("Camera source cannot be None")
        self.source = source
        self.resolution = (1920, 1080)
        self.frame_rate = 30
        self.camera_status = "inactive"
        self.cap = None
        self.last_frame_time = time.time()

    def start(self):
        """
        Opens the video source and applies resolution and FPS settings.
        Sets camera status to active when successful.
        """
        self.cap = cv2.VideoCapture(self.source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.cap.set(cv2.CAP_PROP_FPS, self.frame_rate)
        self.camera_status = "active"

    def stop(self):
        """
        Releases the video capture resource and sets camera status
        back to inactive. Safe to call multiple times without crashing.
        """
        if self.cap is not None:
            self.cap.release()
        self.cap = None
        self.camera_status = "inactive"

    def capture_frame(self):
        """
        Reads and returns the next frame from the video source.
        Always resizes output to 1920x1080 for consistent YOLOv8n input.
        Returns None if frame cannot be read or video has ended.
        """
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (1920, 1080))
                self.last_frame_time = time.time()
                return frame
        return None

    def _handle_invalid_frame(self):
        """
        Private method - called internally when cap.read() returns False.
        Logs a warning and sets camera status to error for System Monitor.
        Not meant to be called from outside this class.
        """
        logger.warning("Invalid frame received")
        self.camera_status = "error"

    def _handle_feed_lost(self):
        """
        Private method - called internally when no frames received for 5 seconds.
        Logs an error and sets camera status to error for System Monitor.
        Not meant to be called from outside this class.
        """
        logger.error("Camera feed lost")
        self.camera_status = "error"

    def _attempt_reconnection(self):
        """
        Private method - attempts to reopen the video source after a failure.
        Logs success or failure and updates camera status accordingly.
        Not meant to be called from outside this class.
        """
        logger.info("Attempting camera reconnection")
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.source)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.frame_rate)
            self.camera_status = "active"
            logger.info("Camera reconnected successfully")
        else:
            self.camera_status = "error"
            logger.error("Camera reconnection failed")

    def monitor_health(self):
        """
        Checks if no frames have been received for 5 seconds.
        If feed has been lost, triggers _handle_feed_lost() to alert
        the System Monitor for immediate action.
        """
        if time.time() - self.last_frame_time > 5:
            self._handle_feed_lost()
