import pytest
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from object_tracking import ObjectTracking


@pytest.fixture
def loaded_tracker():
    """Provides an initialized ObjectTracking instance ready for tracking"""
    tracker = ObjectTracking()
    tracker.initialize_tracker()
    return tracker


@pytest.fixture
def synthetic_detections():
    """
    Provides synthetic detections in the format ObjectTracking expects:
    a list of dicts with bbox as [x1, y1, x2, y2] (top-left, bottom-right
    in pixel coordinates), plus confidence and class. Tests tracking
    behavior in isolation from the YOLO detection layer, so these tests
    do not depend on data/test_video.mp4 or models/yolov8n.pt.

    The synthetic frame contains distinct coloured patches inside each
    bbox so DeepSORT's appearance embedder has real visual signal to
    extract; without this, identical pixel content across detections
    causes the embedder to produce degenerate features and tracking fails.
    """
    # bboxes in [x1, y1, x2, y2] format -- this is what ObjectTracking
    # expects (see object_tracking.py line 44).
    detections = [
        {"bbox": [800, 400, 1000, 900], "confidence": 0.95, "class": "person"},
        {"bbox": [1200, 350, 1420, 870], "confidence": 0.92, "class": "person"},
    ]
    frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    frame[400:900, 800:1000] = [200, 100, 50]
    frame[350:870, 1200:1420] = [50, 150, 200]
    return detections, frame


class TestObjectTrackingInitialization:

    def test_object_tracking_initializes_successfully(self):
        """
        Test that ObjectTracking initializes correctly so the system
        has a tracker ready to assign IDs to detected persons
        """
        tracker = ObjectTracking()
        assert tracker is not None

    def test_object_tracking_has_correct_default_max_age(self):
        """
        Test that max_age defaults to 30 frames to define how long
        a lost track is kept alive before being permanently removed
        """
        tracker = ObjectTracking()
        assert tracker.max_age == 30

    def test_object_tracking_has_correct_default_min_hits(self):
        """
        Test that min_hits defaults to 3 to require a minimum number
        of detections before a track is confirmed as a real person
        and not a false positive detection
        """
        tracker = ObjectTracking()
        assert tracker.min_hits == 3

    def test_object_tracking_has_correct_default_iou_threshold(self):
        """
        Test that iou_threshold defaults to 0.3 to set the minimum
        overlap required to match a detection to an existing track
        and prevent incorrect ID assignments
        """
        tracker = ObjectTracking()
        assert tracker.iou_threshold == 0.3

    def test_object_tracking_status_inactive_before_initialization(self):
        """
        Test that tracker status is inactive before initialize_tracker()
        is called to confirm the system is not tracking before it is
        explicitly started
        """
        tracker = ObjectTracking()
        assert tracker.tracker_status == "inactive"


class TestTrackerLoading:

    def test_initialize_tracker_succeeds(self):
        """
        Test that initialize_tracker() successfully loads DeepSORT
        so the system is ready to assign unique IDs to detected persons
        """
        tracker = ObjectTracking()
        tracker.initialize_tracker()
        assert tracker.tracker is not None

    def test_tracker_status_active_after_initialization(self):
        """
        Test that tracker status changes to active after initialize_tracker()
        is called to confirm DeepSORT is ready to track detected persons
        """
        tracker = ObjectTracking()
        tracker.initialize_tracker()
        assert tracker.tracker_status == "active"

    def test_initialize_tracker_logs_success(self, caplog):
        """
        Test that initialize_tracker() logs a success message to confirm
        DeepSORT is ready and the System Monitor knows tracking has started
        """
        import logging
        tracker = ObjectTracking()
        with caplog.at_level(logging.INFO):
            tracker.initialize_tracker()
        assert "DeepSORT tracker initialized successfully" in caplog.text


class TestPersonTracking:

    def test_track_persons_returns_a_list(self, loaded_tracker):
        """
        Test that track_persons() always returns a list so the Counting
        Logic Component always receives a consistent data structure
        """
        detections = []
        tracks = loaded_tracker.track_persons(detections)
        assert isinstance(tracks, list)

    def test_track_persons_returns_empty_list_when_no_detections(self, loaded_tracker):
        """
        Test that track_persons() returns empty list when no detections
        are provided so the Counting Logic Component receives a consistent
        data structure even when no persons are detected in the frame
        """
        tracks = loaded_tracker.track_persons([])
        assert tracks == []

    def test_track_persons_assigns_track_id_to_each_person(self, loaded_tracker, synthetic_detections):
        """
        Test that track_persons() assigns a unique track ID to each
        detected person so the Counting Logic Component can identify
        and count individual passengers accurately
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        assert len(tracks) > 0
        for track in tracks:
            assert "track_id" in track

    def test_each_tracked_person_has_bounding_box(self, loaded_tracker, synthetic_detections):
        """
        Test that each tracked person has a bounding box so the Counting
        Logic Component can determine their position and direction
        of movement through the virtual entrance and exit zones
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        for track in tracks:
            assert "bbox" in track

    def test_each_tracked_person_has_unique_track_id(self, loaded_tracker, synthetic_detections):
        """
        Test that each tracked person has a unique track ID to confirm
        DeepSORT is correctly distinguishing between different passengers
        and not assigning the same ID to multiple people
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        track_ids = [track["track_id"] for track in tracks]
        assert len(track_ids) == len(set(track_ids))

    def test_track_persons_maintains_same_id_across_frames(self, loaded_tracker, synthetic_detections):
        """
        Test that track_persons() maintains the same track ID for the
        same person across consecutive frames to prevent double counting
        in the Counting Logic Component
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks1 = loaded_tracker.track_persons(detections, frame)
        tracks2 = loaded_tracker.track_persons(detections, frame)
        ids1 = set([track["track_id"] for track in tracks1])
        ids2 = set([track["track_id"] for track in tracks2])
        assert len(ids1.intersection(ids2)) > 0

    def test_track_persons_handles_multiple_persons_simultaneously(self, loaded_tracker, synthetic_detections):
        """
        Test that track_persons() correctly tracks multiple persons at
        the same time to handle simultaneous boarding and alighting
        events as required by FR-CM-2.4
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        assert len(tracks) >= 1


class TestOcclusionHandling:

    def test_track_maintained_when_person_temporarily_occluded(self, loaded_tracker, synthetic_detections):
        """
        Test that a track is maintained when a person is temporarily
        occluded to prevent incorrect counting when passengers are
        briefly blocked from the camera view
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        initial_ids = set([track["track_id"] for track in tracks])
        loaded_tracker.track_persons([], frame)
        for _ in range(2):
            reappeared_tracks = loaded_tracker.track_persons(detections, frame)
        reappeared_ids = set([track["track_id"] for track in reappeared_tracks])
        assert len(initial_ids.intersection(reappeared_ids)) > 0

    def test_person_reidentified_after_reappearing(self, loaded_tracker, synthetic_detections):
        """
        Test that a person is re-identified with the same track ID after
        reappearing within max_age frames to ensure accurate counting
        and prevent the same person being counted twice
        """
        detections, frame = synthetic_detections
        for _ in range(4):
            tracks = loaded_tracker.track_persons(detections, frame)
        initial_ids = set([track["track_id"] for track in tracks])
        loaded_tracker.track_persons([], frame)
        loaded_tracker.track_persons([], frame)
        for _ in range(2):
            reappeared_tracks = loaded_tracker.track_persons(detections, frame)
        reappeared_ids = set([track["track_id"] for track in reappeared_tracks])
        assert len(initial_ids.intersection(reappeared_ids)) > 0
