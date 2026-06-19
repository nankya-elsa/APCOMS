"""
QR Scanner Component for APCOMS

Responsible for opening a webcam, capturing video frames, and
decoding any QR codes present. This module handles only the
QR-reading machinery — validation against Firebase, booking
status transitions, and main.py orchestration live in the
surrounding scanner runtime, not in this class.

The QRScanner is intentionally focused: it knows how to find
QR codes in frames, nothing more. This keeps the component
testable in isolation and easy to swap out if the underlying
QR library changes.
"""

import os
import logging
import cv2
from pyzbar import pyzbar
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class QRScanner:
    """
    Reads QR codes from a webcam feed.

    Attributes:
        camera_source: Index or path of the camera to read from.
                       Defaults to 0 (system default webcam).
        capture:       The active video capture handle, or None
                       when the camera has not been opened yet.
    """

    def __init__(self, camera_source=None):
        """
        Initialize the QRScanner with default values for camera
        source and capture state.

        Args:
            camera_source: Optional override for the camera source.
                           If not provided, reads QR_CAMERA_SOURCE
                           from the environment, falling back to 0.
        """
        if camera_source is None:
            camera_source = os.getenv("QR_CAMERA_SOURCE", "0")
            # convert numeric strings to int so OpenCV uses webcam index
            if camera_source.isdigit():
                camera_source = int(camera_source)

        self.camera_source = camera_source
        self.capture = None

    def initialize_camera(self):
        """
        Open the configured camera source for reading.

        Uses OpenCV's VideoCapture to acquire a handle on either
        a webcam (when camera_source is an int) or a video file
        (when camera_source is a path). The handle is stored on
        self.capture for subsequent frame reads.

        Returns:
            True if the camera opened successfully, False otherwise.
            Callers should check the return value and fall back to
            an error state rather than assuming success.
        """
        self.capture = cv2.VideoCapture(self.camera_source)
        if not self.capture.isOpened():
            logger.error(f"Failed to open camera source: {self.camera_source}")
            return False

        logger.info(f"Camera opened successfully: {self.camera_source}")
        return True

    def release_camera(self):
        """
        Release the camera handle and reset capture state.

        Safe to call multiple times or before initialize_camera()
        has been called — does nothing if there is no active
        capture. This makes it suitable for cleanup paths and
        signal handlers where the camera state may be uncertain.
        """
        if self.capture is not None:
            self.capture.release()
            self.capture = None
            logger.info("Camera released")

    def scan_for_qr(self, frame):
        """
        Decode any QR codes present in the given video frame.

        Uses pyzbar to find and decode QR codes. Returns a list of
        decoded payload strings (one per QR code found). Empty list
        if no codes are present or the frame is invalid.

        Each payload is decoded from bytes to a UTF-8 string before
        return, so callers can JSON-parse it directly without
        worrying about byte handling. The decoder is resilient to
        None frames so intermittent camera glitches don't crash
        the scanner loop.

        Args:
            frame: A video frame from cv2.VideoCapture.read(), or
                   None if the most recent read failed.

        Returns:
            List of decoded QR payloads as strings. Empty if no
            QR codes were found or the frame was None.
        """
        if frame is None:
            return []

        detections = pyzbar.decode(frame)
        return [d.data.decode("utf-8") for d in detections]

    def run(self, on_qr_detected):
        """
        Start the scanning loop until the first QR code is detected.

        Opens the camera, reads frames continuously, and decodes any
        QR codes found. The loop exits as soon as the first QR is
        detected — at which point the callback is invoked once with
        the payload, the captured frame is held on screen for a
        brief moment with the payload overlaid (the snapshot feel),
        then the camera is released.

        This single-scan-per-run contract makes the scanner easy to
        orchestrate: callers invoke run() once per boarding event,
        then validate the payload and decide whether to scan again.

        The loop also exits without detection if the camera read
        fails, the user presses 'q' in the preview window, or the
        camera cannot be opened in the first place.

        Args:
            on_qr_detected: A callable that takes a single string
                            argument — the decoded QR payload.
                            Invoked at most once per run() call.
        """
        if not self.initialize_camera():
            logger.error("Cannot start scanner — camera failed to open")
            return

        logger.info("Scanner running. Press 'q' to quit.")

        try:
            while True:
                ret, frame = self.capture.read()
                if not ret:
                    logger.warning("Camera read failed, exiting scanner loop")
                    break

                payloads = self.scan_for_qr(frame)
                if payloads:
                    payload = payloads[0]
                    on_qr_detected(payload)
                    self._show_capture_snapshot(frame, payload)
                    break

                cv2.imshow("APCOMS QR Scanner", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("User pressed 'q' — exiting scanner loop")
                    break
        finally:
            self.release_camera()
            cv2.destroyAllWindows()

    def _show_capture_snapshot(self, frame, payload, hold_ms=3000):
        """
        Display the captured frame with the decoded payload overlaid
        for a brief moment, giving the user visual confirmation that
        the scan succeeded — like a snapshot being taken.

        The frame is shown for `hold_ms` milliseconds (default 1.5s)
        before control returns. Keeps the user interface intuitive
        and forgiving: people see what was captured, not just text
        in a terminal.

        Args:
            frame:   The captured video frame containing the QR code.
            payload: The decoded payload string to overlay.
            hold_ms: How long to hold the snapshot, in milliseconds.
        """
        # green banner across the top to make the success obvious
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 60), (0, 200, 0), -1)
        cv2.putText(
            frame, "SCAN CAPTURED", (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
        )
        # payload text below the banner
        cv2.putText(
            frame, payload[:60], (20, 90),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2,
        )
        cv2.imshow("APCOMS QR Scanner", frame)
        cv2.waitKey(hold_ms)
