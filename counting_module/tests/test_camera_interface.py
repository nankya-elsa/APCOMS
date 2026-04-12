import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from camera_interface import CameraInterface


class TestCameraInitialization:

    def test_camera_initializes_successfully_with_video(self):
        """
        Test that camera stores the given source so the system
        knows where to read video frames from
        """
        camera = CameraInterface(source="test_source")
        assert camera is not None
        assert camera.source == "test_source"

    def test_camera_initializes_with_webcam(self):
        """
        Test that camera accepts an integer source (0) to support
        webcam input as an alternative to video files via Strategy Pattern
        """
        camera = CameraInterface(source=0)
        assert camera.source == 0

    def test_camera_has_correct_default_resolution(self):
        """
        Test that camera defaults to 1080p to provide sufficient
        resolution for accurate person detection by YOLOv8n
        """
        camera = CameraInterface(source=0)
        assert camera.resolution == (1920, 1080)

    def test_camera_has_correct_default_framerate(self):
        """
        Test that camera defaults to 30 FPS to ensure no passengers
        are missed during simultaneous boarding and alighting events
        """
        camera = CameraInterface(source=0)
        assert camera.frame_rate == 30

    def test_camera_status_is_inactive_before_start(self):
        """
        Test that camera status is inactive before starting to confirm
        the system is not processing frames before it is explicitly started
        """
        camera = CameraInterface(source=0)
        assert camera.camera_status == "inactive"

    def test_invalid_source_raises_error(self):
        """
        Test that passing an invalid source raises a ValueError to prevent
        the system from starting with a source it cannot read frames from
        """
        with pytest.raises(ValueError):
            camera = CameraInterface(source=None)


class TestCameraStatus:

    def test_camera_status_active_after_start(self):
        """
        Test that camera status changes to active after start is called
        to confirm the system is ready to capture and process frames
        """
        camera = CameraInterface(source=0)
        camera.start()
        assert camera.camera_status == "active"
        camera.stop()

    def test_camera_status_inactive_after_stop(self):
        """
        Test that camera status returns to inactive after stop is called
        to confirm the system properly stops processing frames when shut down
        """
        camera = CameraInterface(source=0)
        camera.start()
        camera.stop()
        assert camera.camera_status == "inactive"


class TestCameraCleanup:

    def test_stop_releases_camera_properly(self):
        """
        Test that stop() sets cap to None to confirm all camera
        resources are released cleanly and not left hanging
        """
        camera = CameraInterface(source=0)
        camera.start()
        camera.stop()
        assert camera.cap is None

    def test_calling_stop_twice_does_not_crash(self):
        """
        Test that calling stop() twice does not raise any error to confirm
        the system handles redundant shutdown calls gracefully
        """
        camera = CameraInterface(source=0)
        camera.start()
        camera.stop()
        camera.stop()


class TestCameraFrameCapture:

    def test_camera_capture_returns_frame(self):
        """
        Test that capture_frame() returns a valid frame to confirm
        the system can successfully read frames from the video source
        """
        camera = CameraInterface(source="data/test_video.mp4")
        camera.start()
        frame = camera.capture_frame()
        assert frame is not None
        camera.stop()

    def test_captured_frame_has_correct_shape(self):
        """
        Test that returned frame has 3 dimensions to confirm it is a
        valid BGR color image that YOLOv8n can process for person detection
        """
        camera = CameraInterface(source="data/test_video.mp4")
        camera.start()
        frame = camera.capture_frame()
        assert len(frame.shape) == 3
        assert frame.shape[2] == 3
        camera.stop()

    def test_capture_frame_returns_none_when_video_ends(self):
        """
        Test that capture_frame() returns None when video source is exhausted
        to confirm the system handles end of video gracefully without crashing
        """
        camera = CameraInterface(source="data/test_video.mp4")
        camera.start()
        frame = None
        while True:
            result = camera.capture_frame()
            if result is None:
                frame = None
                break
        assert frame is None
        camera.stop()


class TestCameraHealthMonitoring:

    def test_invalid_frame_logs_warning(self, caplog):
        """
        Test that a warning is logged when an invalid frame is received
        to confirm the system reports feed issues for maintenance diagnosis
        """
        import logging
        camera = CameraInterface(source=0)
        camera.start()
        with caplog.at_level(logging.WARNING):
            camera._handle_invalid_frame()
        assert "Invalid frame received" in caplog.text
        camera.stop()

    def test_camera_status_set_to_error_on_invalid_frame(self):
        """
        Test that camera status is set to error when an invalid frame
        occurs so the System Monitor can detect and respond to feed issues
        """
        camera = CameraInterface(source=0)
        camera.start()
        camera._handle_invalid_frame()
        assert camera.camera_status == "error"
        camera.stop()

    def test_feed_lost_logs_error(self, caplog):
        """
        Test that an error is logged when camera feed is lost to confirm
        the system alerts the System Monitor for immediate action
        """
        import logging
        camera = CameraInterface(source=0)
        camera.start()
        with caplog.at_level(logging.ERROR):
            camera._handle_feed_lost()
        assert "Camera feed lost" in caplog.text
        camera.stop()
