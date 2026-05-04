import sys
import os
import cv2
import time
import logging
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from camera_interface import CameraInterface
from object_detection import ObjectDetection
from object_tracking import ObjectTracking
from counting_logic import CountingLogic
from display import DisplayComponent
from firebase_sync import FirebaseSyncComponent
from data_logger import DataLogger
from system_monitor import SystemMonitor

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("APCOMS - AI-Powered Passenger Counting System")
    logger.info("Makerere University Driverless E-Shuttle")
    logger.info("BSE26-8 | Nankya Elsa & Musiimenta Cissylyn")
    logger.info("=" * 60)

    # ── STEP 1: Initialize all components ──────────────────────
    logger.info("Initializing system components...")

    # Data Logger - initialize first so database exists
    data_logger = DataLogger(shuttle_id=os.getenv("SHUTTLE_ID", "shuttle_001"))
    data_logger.initialize()

    # System Monitor
    system_monitor = SystemMonitor(data_logger=data_logger)
    system_monitor.initialize()

    # Counting Logic
    counting_logic = CountingLogic()
    counting_logic.initialize()

    # Camera Interface
    camera_source = os.getenv("CAMERA_SOURCE", "data/test_video.mp4")
    camera = CameraInterface(source=camera_source)
    camera.start()

    # Object Detection
    model_path = os.getenv("MODEL_PATH", "models/yolov8n.pt")
    detector = ObjectDetection(model_path=model_path)
    detector.load_model()

    # Object Tracking
    tracker = ObjectTracking()
    tracker.initialize_tracker()

    # Display Component
    display = DisplayComponent()
    display.initialize_display()

    # Firebase Sync
    firebase_sync = FirebaseSyncComponent(
        shuttle_id=os.getenv("SHUTTLE_ID", "shuttle_001")
    )
    firebase_sync.initialize()

    logger.info("=" * 60)
    logger.info("All components initialized! Starting main loop...")
    logger.info("Press Q in the display window to quit")
    logger.info("=" * 60)

    # ── STEP 2: Main pipeline loop ──────────────────────────────
    frame_count = 0
    last_firebase_sync = time.time()
    last_storage_check = time.time()
    firebase_sync_interval = 2
    storage_check_interval = 3600

    try:
        while True:
            # capture frame
            frame = camera.capture_frame()

            if frame is None:
                logger.info("Video ended or camera disconnected")
                break

            frame_count += 1
            start_time = time.time()

            # detect persons
            detections = detector.detect_persons(frame)

            # track persons
            tracks = tracker.track_persons(detections, frame)

            # update count for each track
            for track in tracks:
                track_dict = {
                    "track_id": track.get("track_id", 0),
                    "previous_centroid": track.get("previous_centroid", (0, 0)),
                    "current_centroid": track.get("current_centroid", (0, 540))
                }

                # capture count BEFORE update so we can detect if it actually changed
                count_before = counting_logic.passenger_count
                counting_logic.update_count(track_dict)
                count_after = counting_logic.passenger_count

                # only log event if count actually changed (real boarding or alighting)
                if count_after != count_before:
                    direction = "boarding" if count_after > count_before else "alighting"
                    occupancy = counting_logic.calculate_occupancy()
                    data_logger.log_event({
                        "direction": direction,
                        "passenger_count": occupancy["passenger_count"],
                        "available_seats": occupancy["available_seats"],
                        "stop_location": counting_logic.get_current_stop()
                    })

            # calculate occupancy
            occupancy = counting_logic.calculate_occupancy()
            occupancy["current_stop"] = counting_logic.get_current_stop()

            # calculate next stop
            next_index = (counting_logic.current_stop_index + 1) % len(
                counting_logic.designated_stops_list
            )
            occupancy["next_stop"] = counting_logic.designated_stops_list[next_index]

            # calculate FPS and latency
            latency_ms = (time.time() - start_time) * 1000
            fps = 1000 / latency_ms if latency_ms > 0 else 0

            # monitor performance
            system_monitor.monitor_performance(fps=fps, latency_ms=latency_ms)

            # monitor camera health
            system_monitor.monitor_camera(camera.camera_status)

            # get system status for display
            status = system_monitor.get_system_status()

            # save system status to SQLite for dashboard
            conn = sqlite3.connect('local_database/apcoms.db')
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('system_status', ?)", (status["system_status"],))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('camera_status', ?)", (status["camera_status"],))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_fps', ?)", (str(round(fps, 2)),))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_latency', ?)", (str(round(latency_ms, 2)),))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_count', ?)", (str(occupancy["passenger_count"]),))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('available_seats', ?)", (str(occupancy["available_seats"]),))
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_stop', ?)", (occupancy["current_stop"],))
            conn.commit()
            conn.close()

            # update OLED display
            display.show(occupancy, system_status=status["system_status"])

            # sync to Firebase every 2 seconds
            if time.time() - last_firebase_sync >= firebase_sync_interval:
                firebase_sync.monitor_connectivity()
                firebase_sync.sync_to_firebase(occupancy)
                last_firebase_sync = time.time()

            # check storage every hour
            if time.time() - last_storage_check >= storage_check_interval:
                storage_info = data_logger.monitor_storage()
                if storage_info["available_gb"] < 1.0:
                    system_monitor.handle_alert({"type": "storage_alert"})
                last_storage_check = time.time()

            # log diagnostic every 100 frames
            if frame_count % 100 == 0:
                data_logger.log_diagnostic({
                    "log_type": "info",
                    "message": f"System running normally at {fps:.1f} FPS",
                    "camera_status": camera.camera_status,
                    "fps": round(fps, 2),
                    "latency_ms": round(latency_ms, 2)
                })

            # press Q to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info("Quit signal received")
                break

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received - shutting down")

    finally:
        # ── STEP 3: Clean shutdown ──────────────────────────────
        logger.info("=" * 60)
        logger.info("Shutting down APCOMS...")
        camera.stop()
        cv2.destroyAllWindows()
        logger.info("Camera stopped")
        # advance to next stop so next run starts at the next location
        counting_logic.advance_stop()

        # write offline status to SQLite so dashboard reflects shutdown
        conn = sqlite3.connect('local_database/apcoms.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('system_status', 'Offline')")
        cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('camera_status', 'unknown')")
        cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_fps', '0')")
        cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('current_latency', '0')")
        conn.commit()
        conn.close()

        logger.info("System shutdown complete")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
