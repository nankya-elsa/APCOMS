import cv2
import logging

logger = logging.getLogger(__name__)

class CameraInterface:

    def __init__(self, source):
        if source is None:
            raise ValueError("Camera source cannot be None")
        self.source = source
        self.resolution = (1920, 1080)
        self.frame_rate = 30
        self.camera_status = "inactive"
        self.cap = None

    def start(self):
        self.cap = cv2.VideoCapture(self.source)
        self.camera_status = "active"

    def stop(self):
        if self.cap is not None:
            self.cap.release()
        self.cap = None
        self.camera_status = "inactive"

    def capture_frame(self):
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret: # Check if frame was read successfully
                return frame
        return None

    def _handle_invalid_frame(self):
        # private method - called internally when cap.read() returns False
        # not meant to be called from outside this class
        logger.warning("Invalid frame received")
        self.camera_status = "error"

    def _handle_feed_lost(self):
        # private method - called internally when no frames received for 5 seconds
        # not meant to be called from outside this class
        logger.error("Camera feed lost")
        self.camera_status = "error"
