"""
Tests for the QRScanner component.

The QRScanner is responsible for opening a webcam, capturing frames,
and decoding any QR codes present in each frame. It does not perform
any business logic — validation and Firebase integration are handled
by the surrounding orchestration script. These tests verify the
QR-reading machinery in isolation.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from qr_scanner import QRScanner


class TestQRScannerInitialization:
    """Tests covering QRScanner construction and defaults."""

    def test_qr_scanner_initializes_with_defaults(self):
        """
        QRScanner should instantiate without arguments and set sensible
        defaults for camera source and capture state. We verify the
        instance exists and core attributes are present.
        """
        scanner = QRScanner()
        assert scanner is not None
        assert hasattr(scanner, "camera_source")
        assert hasattr(scanner, "capture")
        assert scanner.capture is None


class TestQRScannerCameraSource:
    """Tests covering how QRScanner resolves the camera source."""

    def test_camera_source_defaults_to_zero(self):
        """
        When no QR_CAMERA_SOURCE is set in environment and no
        explicit camera_source argument is passed, the scanner
        should default to camera index 0 (the system's default
        webcam). This ensures the scanner works out of the box
        on most laptops.
        """
        with patch.dict(os.environ, {}, clear=True):
            scanner = QRScanner()
            assert scanner.camera_source == 0

    def test_camera_source_reads_from_env(self):
        """
        When QR_CAMERA_SOURCE is set in the environment as a
        numeric string, the scanner should convert it to an int
        and use it as the camera index. This allows admins to
        select a specific camera via .env without code changes.
        """
        with patch.dict(os.environ, {"QR_CAMERA_SOURCE": "1"}, clear=True):
            scanner = QRScanner()
            assert scanner.camera_source == 1

    def test_camera_source_accepts_explicit_argument(self):
        """
        An explicit camera_source argument should override any
        environment value. This is useful for tests and for
        callers that already know which camera to use.
        """
        with patch.dict(os.environ, {"QR_CAMERA_SOURCE": "1"}, clear=True):
            scanner = QRScanner(camera_source=2)
            assert scanner.camera_source == 2

    def test_camera_source_accepts_file_path(self):
        """
        For testing and development, the camera source can be a
        file path to a video containing QR codes rather than a
        live webcam. The scanner should accept the path as a
        string and not attempt to convert it to int.
        """
        with patch.dict(os.environ, {"QR_CAMERA_SOURCE": "data/qr_test.mp4"}, clear=True):
            scanner = QRScanner()
            assert scanner.camera_source == "data/qr_test.mp4"


class TestCameraInitialization:
    """Tests covering camera open/close behaviour."""

    @patch("qr_scanner.cv2")
    def test_initialize_camera_opens_capture(self, mock_cv2):
        """
        initialize_camera() should call cv2.VideoCapture with the
        configured camera source and store the resulting handle.
        We mock cv2 to avoid actually opening hardware during tests.
        """
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        scanner = QRScanner(camera_source=0)
        result = scanner.initialize_camera()

        assert result is True
        mock_cv2.VideoCapture.assert_called_once_with(0)
        assert scanner.capture is mock_capture

    @patch("qr_scanner.cv2")
    def test_initialize_camera_returns_false_when_camera_fails(self, mock_cv2):
        """
        If cv2.VideoCapture cannot open the camera (e.g. no webcam
        attached), initialize_camera() should return False and
        leave the capture in a safe unopened state rather than
        crashing the scanner.
        """
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_capture

        scanner = QRScanner(camera_source=0)
        result = scanner.initialize_camera()

        assert result is False

    @patch("qr_scanner.cv2")
    def test_release_camera_closes_capture(self, mock_cv2):
        """
        release_camera() should release the underlying capture
        handle and reset the capture attribute to None so the
        scanner can be safely shut down without leaving the
        webcam locked.
        """
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        scanner = QRScanner(camera_source=0)
        scanner.initialize_camera()
        scanner.release_camera()

        mock_capture.release.assert_called_once()
        assert scanner.capture is None

    def test_release_camera_safe_when_capture_is_none(self):
        """
        Calling release_camera() before initialize_camera()
        should be a safe no-op — it must not raise an exception
        even if there's nothing to release. This guards against
        cleanup code being called in error paths.
        """
        scanner = QRScanner()
        # should not raise
        scanner.release_camera()
        assert scanner.capture is None


class TestScanForQR:
    """Tests covering decoding QR codes from video frames."""

    @patch("qr_scanner.pyzbar")
    def test_scan_for_qr_returns_empty_when_no_qr_in_frame(self, mock_pyzbar):
        """
        When pyzbar finds no QR codes in the given frame, scan_for_qr
        should return an empty list. This is the steady state — most
        frames during normal scanning won't contain a QR code, so the
        empty-list path must be cheap and predictable.
        """
        mock_pyzbar.decode.return_value = []

        scanner = QRScanner()
        result = scanner.scan_for_qr(frame="dummy_frame")

        assert result == []
        mock_pyzbar.decode.assert_called_once_with("dummy_frame")

    @patch("qr_scanner.pyzbar")
    def test_scan_for_qr_decodes_single_qr_code(self, mock_pyzbar):
        """
        When a single QR code is found, scan_for_qr should decode
        its data bytes into a string and return a list with that
        one payload. The string is what callers will then JSON-parse
        for booking validation.
        """
        mock_qr = MagicMock()
        mock_qr.data = b'{"v":1,"bookingId":"abc123"}'
        mock_pyzbar.decode.return_value = [mock_qr]

        scanner = QRScanner()
        result = scanner.scan_for_qr(frame="dummy_frame")

        assert result == ['{"v":1,"bookingId":"abc123"}']

    @patch("qr_scanner.pyzbar")
    def test_scan_for_qr_decodes_multiple_qr_codes(self, mock_pyzbar):
        """
        When the frame contains multiple QR codes (e.g. two passengers
        hold up their phones at once), scan_for_qr should return all
        of them. Upstream orchestration decides how to handle this —
        the scanner itself doesn't restrict.
        """
        qr1, qr2 = MagicMock(), MagicMock()
        qr1.data = b'payload_one'
        qr2.data = b'payload_two'
        mock_pyzbar.decode.return_value = [qr1, qr2]

        scanner = QRScanner()
        result = scanner.scan_for_qr(frame="dummy_frame")

        assert result == ['payload_one', 'payload_two']

    @patch("qr_scanner.pyzbar")
    def test_scan_for_qr_returns_payloads_as_strings(self, mock_pyzbar):
        """
        Pyzbar returns the QR data as bytes. scan_for_qr must decode
        these to UTF-8 strings before returning so callers don't have
        to handle byte/string conversion themselves. This keeps the
        contract clean: scan_for_qr in, string list out.
        """
        mock_qr = MagicMock()
        mock_qr.data = b'hello world'
        mock_pyzbar.decode.return_value = [mock_qr]

        scanner = QRScanner()
        result = scanner.scan_for_qr(frame="dummy_frame")

        assert isinstance(result[0], str)
        assert result[0] == 'hello world'

    def test_scan_for_qr_handles_none_frame(self):
        """
        If a None frame is passed (e.g. camera returned no frame
        on a given read), scan_for_qr should return an empty list
        rather than crashing. This makes the scanner resilient to
        intermittent camera glitches without complicating callers.
        """
        scanner = QRScanner()
        result = scanner.scan_for_qr(frame=None)

        assert result == []


class TestRunLoop:
    """
    Tests covering the run() orchestration loop.

    The loop itself is an infinite read-decode cycle, which is
    impractical to test exhaustively. These tests verify the
    setup and teardown contract — that run() initializes the
    camera, invokes the user's callback when QR codes appear,
    and cleans up on shutdown.
    """

    @patch("qr_scanner.cv2")
    def test_run_returns_early_when_camera_fails_to_open(self, mock_cv2):
        """
        If the camera cannot be initialized (e.g. no webcam, or
        another process holding the device), run() should return
        immediately without entering the read loop. This keeps
        the scanner from busy-waiting against a broken camera.
        """
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_capture

        scanner = QRScanner()
        callback = MagicMock()

        scanner.run(on_qr_detected=callback)

        callback.assert_not_called()

    @patch("qr_scanner.pyzbar")
    @patch("qr_scanner.cv2")
    def test_run_invokes_callback_once_on_qr_detection(self, mock_cv2, mock_pyzbar):
        """
        When a QR code appears in the camera feed, run() must
        invoke the callback EXACTLY ONCE with the decoded payload
        and then exit the loop. This single-scan-per-run contract
        prevents flipping a booking active dozens of times per
        second when the QR sits in front of the camera.
        """
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        # simulate frames continuously available - run() should exit
        # after the first detection regardless
        mock_frame = MagicMock()
        mock_frame.shape = (480, 640, 3)  # height, width, channels
        mock_capture.read.return_value = (True, mock_frame)
        mock_cv2.VideoCapture.return_value = mock_capture
        mock_cv2.waitKey.return_value = -1

        mock_qr = MagicMock()
        mock_qr.data = b'{"bookingId":"test123"}'
        mock_pyzbar.decode.return_value = [mock_qr]

        scanner = QRScanner()
        callback = MagicMock()
        scanner.run(on_qr_detected=callback)

        callback.assert_called_once_with('{"bookingId":"test123"}')
