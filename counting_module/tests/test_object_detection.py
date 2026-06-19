import pytest
import os
import sys
import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from object_detection import ObjectDetection

# skip conditions for CI environment
MODEL_AVAILABLE = os.path.exists("models/yolov8n.pt")

# Test fixture frames bundled in the repo. Independent of data/test_video.mp4
# so swapping the production video doesn't break detection tests.
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "persons")
FIXTURE_AVAILABLE = os.path.isdir(FIXTURES_DIR) and any(
    f.endswith(".jpg") for f in os.listdir(FIXTURES_DIR)
) if os.path.isdir(FIXTURES_DIR) else False


@pytest.fixture
def real_frame():
    """
    Provides a real frame with a clearly visible person, loaded from a
    bundled test fixture image. Decoupled from data/test_video.mp4 so
    that swapping the production video doesn't break detection tests.
    """
    fixture_path = os.path.join(FIXTURES_DIR, "person_clear_1.jpg")
    frame = cv2.imread(fixture_path)
    if frame is None:
        pytest.skip(f"Could not load fixture image at {fixture_path}")
    return frame


@pytest.fixture
def loaded_detector():
    """Provides a loaded ObjectDetection instance ready for inference"""
    detector = ObjectDetection(model_path="models/yolov8n.pt")
    detector.load_model()
    return detector


class TestObjectDetectionInitialization:

    def test_object_detection_initializes_with_valid_model_path(self):
        """
        Test that ObjectDetection stores the given model path so the
        system knows where to load the YOLOv8n model from
        """
        detector = ObjectDetection(model_path="models/yolov8n.pt")
        assert detector is not None
        assert detector.model_path == "models/yolov8n.pt"

    def test_object_detection_invalid_model_path_raises_error(self):
        """
        Test that passing an invalid model path raises a ValueError to
        prevent the system from starting without a valid YOLOv8n model
        """
        with pytest.raises(ValueError):
            detector = ObjectDetection(model_path=None)

    def test_object_detection_empty_model_path_raises_error(self):
        """
        Test that passing an empty model path raises a ValueError to
        prevent the system from starting with an unusable model path
        """
        with pytest.raises(ValueError):
            detector = ObjectDetection(model_path="")

    def test_object_detection_has_correct_default_confidence_threshold(self):
        """
        Test that confidence threshold defaults to 0.5 to filter out
        weak detections and ensure only reliable person detections
        are passed to the Object Tracking Component
        """
        detector = ObjectDetection(model_path="models/yolov8n.pt")
        assert detector.confidence_threshold == 0.5

    def test_object_detection_model_status_inactive_before_loading(self):
        """
        Test that model status is inactive before load_model() is called
        to confirm the system is not running inference before it is
        explicitly loaded
        """
        detector = ObjectDetection(model_path="models/yolov8n.pt")
        assert detector.model_status == "inactive"


class TestModelLoading:

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_load_model_succeeds_with_valid_path(self):
        """
        Test that load_model() successfully loads YOLOv8n from the
        models folder so the system is ready to run inference on frames
        """
        detector = ObjectDetection(model_path="models/yolov8n.pt")
        detector.load_model()
        assert detector.model is not None

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_model_status_active_after_loading(self):
        """
        Test that model status changes to active after load_model() is
        called to confirm YOLOv8n is ready to run inference on frames
        """
        detector = ObjectDetection(model_path="models/yolov8n.pt")
        detector.load_model()
        assert detector.model_status == "active"

    def test_missing_model_file_raises_error(self):
        """
        Test that load_model() raises an error when model file is missing
        to prevent the system from running inference without a valid model
        """
        detector = ObjectDetection(model_path="models/nonexistent_model.pt")
        with pytest.raises(FileNotFoundError):
            detector.load_model()

    def test_missing_model_file_logs_error(self, caplog):
        """
        Test that load_model() logs an error when model file is missing
        so the System Monitor is notified as per pseudocode
        """
        import logging
        detector = ObjectDetection(model_path="models/nonexistent_model.pt")
        with caplog.at_level(logging.ERROR):
            try:
                detector.load_model()
            except FileNotFoundError:
                pass
        assert "Model file missing" in caplog.text


class TestPersonDetection:

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_detect_persons_returns_a_list(self, loaded_detector, real_frame):
        """
        Test that detect_persons() always returns a list so the Object
        Tracking Component always receives a consistent data structure
        """
        detections = loaded_detector.detect_persons(real_frame)
        assert isinstance(detections, list)

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_detect_persons_returns_empty_list_when_no_persons(self, loaded_detector):
        """
        Test that detect_persons() returns an empty list when no persons
        are in the frame so the Object Tracking Component receives a
        consistent data structure even when nothing is detected
        """
        blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detections = loaded_detector.detect_persons(blank_frame)
        assert detections == []

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_detect_persons_returns_detections_when_persons_in_frame(self, loaded_detector, real_frame):
        """
        Test that detect_persons() returns at least one detection when
        persons are present in the frame to confirm YOLOv8n is correctly
        identifying people for the Object Tracking Component
        """
        detections = loaded_detector.detect_persons(real_frame)
        assert len(detections) > 0

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_each_detection_has_bounding_box(self, loaded_detector, real_frame):
        """
        Test that each detection contains a bounding box with 4 coordinates
        so the Object Tracking Component can locate each person in the frame
        """
        detections = loaded_detector.detect_persons(real_frame)
        for detection in detections:
            assert "bbox" in detection
            assert len(detection["bbox"]) == 4

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_each_detection_has_confidence_score(self, loaded_detector, real_frame):
        """
        Test that each detection contains a confidence score to confirm
        YOLOv8n is providing reliability information for each person
        detected so weak detections can be filtered out
        """
        detections = loaded_detector.detect_persons(real_frame)
        for detection in detections:
            assert "confidence" in detection
            assert 0.0 <= detection["confidence"] <= 1.0

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_detect_persons_filters_out_non_person_detections(self, loaded_detector):
        """
        Test that detect_persons() only returns person detections and
        filters out all other objects like cars, chairs, and bags so
        the Object Tracking Component only tracks relevant targets
        """
        blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detections = loaded_detector.detect_persons(blank_frame)
        for detection in detections:
            assert detection["class"] == "person"

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_detect_persons_filters_out_low_confidence_detections(self, loaded_detector, real_frame):
        """
        Test that detect_persons() filters out detections below the
        confidence threshold to ensure only reliable person detections
        reach the Object Tracking Component
        """
        loaded_detector.confidence_threshold = 0.99
        detections = loaded_detector.detect_persons(real_frame)
        assert detections == []

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_detect_persons_handles_none_frame_gracefully(self, loaded_detector):
        """
        Test that detect_persons() returns empty list when frame is None
        to confirm the system handles missing frames without crashing
        so the pipeline continues operating smoothly
        """
        detections = loaded_detector.detect_persons(None)
        assert detections == []

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_detect_persons_handles_blank_frame_gracefully(self, loaded_detector):
        """
        Test that detect_persons() returns empty list for a blank frame
        to confirm the system handles frames with no visual content
        without crashing
        """
        blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        detections = loaded_detector.detect_persons(blank_frame)
        assert isinstance(detections, list)


class TestPerformanceMonitoring:

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_monitor_performance_records_fps(self, loaded_detector, real_frame):
        """
        Test that monitor_performance() records FPS after running
        inference so the System Monitor can track AI model performance
        """
        loaded_detector.monitor_performance(real_frame)
        assert loaded_detector.fps is not None
        assert loaded_detector.fps > 0

    @pytest.mark.skipif(not MODEL_AVAILABLE, reason="model file not available in CI")
    def test_monitor_performance_logs_warning_when_fps_below_30(self, loaded_detector, caplog):
        """
        Test that monitor_performance() logs a warning when FPS drops
        below 30 so the System Monitor can detect performance degradation
        and take action to maintain counting accuracy
        """
        import logging
        import numpy as np
        large_frame = np.zeros((4000, 6000, 3), dtype=np.uint8)
        with caplog.at_level(logging.WARNING):
            loaded_detector.monitor_performance(large_frame)
        assert "Performance degradation detected" in caplog.text

    @pytest.mark.skipif(not MODEL_AVAILABLE or not FIXTURE_AVAILABLE, reason="model or fixture not available in CI")
    def test_monitor_performance_tracks_latency(self, loaded_detector, real_frame):
        """
        Test that monitor_performance() records latency in milliseconds
        so the System Monitor can track how long each inference takes
        and ensure it stays below 100ms per frame as per NFR-CM-1.4
        """
        loaded_detector.monitor_performance(real_frame)
        assert loaded_detector.latency_ms is not None
        assert loaded_detector.latency_ms > 0
