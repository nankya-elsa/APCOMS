import logging
from ultralytics import YOLO
import os
import time

logger = logging.getLogger(__name__)


class ObjectDetection:

    def __init__(self, model_path):
        if not model_path:
            raise ValueError("Model path cannot be None or empty.")
        self.model_path = model_path
        self.confidence_threshold = 0.5
        self.model_status = "inactive"
        self.model = None
        self.fps = None
        self.latency_ms = None

    def load_model(self):
        """
        Loads the YOLOv8n model from the given model path.
        Sets model status to active on success.
        Logs error and raises exception if model file is missing.
        """
        if not os.path.exists(self.model_path):
            logger.error("Model file missing")
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        self.model = YOLO(self.model_path)
        self.model_status = "active"
        logger.info("YOLOv8n model loaded successfully")

    def detect_persons(self, frame):
        """
        Runs YOLOv8n inference on the given frame and returns a list
        of detections filtered to persons above confidence threshold.
        Returns empty list if no persons detected or frame is invalid.
        """
        if frame is None:
            return []

        detections = []
        results = self.model(frame, verbose=False)

        for result in results:
            for box in result.boxes:
                if int(box.cls[0]) == 0:  # class 0 = person
                    confidence = float(box.conf[0])
                    if confidence >= self.confidence_threshold:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": confidence,
                            "class": "person"
                        })

        return detections

    def monitor_performance(self, frame):
        """
        Records inference time, calculates FPS and latency for the frame.
        Logs a warning if FPS drops below 30 to alert System Monitor
        of performance degradation.
        """
        start_time = time.time()
        self.detect_persons(frame)
        end_time = time.time()

        inference_time = end_time - start_time
        self.latency_ms = inference_time * 1000
        self.fps = 1 / inference_time

        if self.fps < 30:
            logger.warning("Performance degradation detected")
