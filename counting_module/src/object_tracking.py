import logging
from deep_sort_realtime.deepsort_tracker import DeepSort

logger = logging.getLogger(__name__)


class ObjectTracking:

    def __init__(self):
        self.max_age = 30
        self.min_hits = 3
        self.iou_threshold = 0.3
        self.tracker_status = "inactive"
        self.tracker = None

    def initialize_tracker(self):
        """
        Initializes the DeepSORT tracker with configured parameters.
        Sets tracker status to active on success.
        Logs success message when tracker is ready.
        """
        self.tracker = DeepSort(
            max_age=self.max_age,          # frames to keep lost track alive before removing, nn- neural networks
            nn_budget=100,                 # max number of appearance features stored per track
            nms_max_overlap=self.iou_threshold  # Non-Maximum Suppression - minimum overlap to match detection to track
        )
        self.tracker_status = "active"
        logger.info("DeepSORT tracker initialized successfully")

    def track_persons(self, detections, frame=None):
        """
        Receives detections from Object Detection Component and updates
        DeepSORT tracker to assign and maintain unique IDs for each person.
        Returns list of tracked persons with track ID, bounding box and trajectory.
        Returns empty list if no detections provided.
        """
        if not detections:
            return []

        # convert detections to DeepSORT format
        # DeepSORT expects: [([x1,y1,w,h], confidence, class), ...]
        deepsort_detections = []
        for detection in detections:
            x1, y1, x2, y2 = detection["bbox"]
            w = x2 - x1
            h = y2 - y1
            confidence = detection["confidence"]
            deepsort_detections.append(([x1, y1, w, h], confidence, "person"))

        # update tracker with new detections
        tracks = self.tracker.update_tracks(deepsort_detections, frame=frame)

        # build output list
        tracked_persons = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            tracked_persons.append({
                "track_id": track.track_id,
                "bbox": track.to_ltrb(),
                "trajectory": track.get_det_class()
            })

        return tracked_persons
