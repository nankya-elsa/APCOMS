import cv2
import os
import sys
import datetime
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from camera_interface import CameraInterface
from counting_logic import CountingLogic

load_dotenv()

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
TOTAL_CAPACITY = int(os.getenv("TOTAL_CAPACITY"))
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE")


def setup_firebase():
    """Initializes Firebase connection and returns database reference"""
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})
    return db.reference("shuttles/shuttle_001")


def push_to_firebase(firebase_ref, counter):
    """Pushes current occupancy and stop data to Firebase Realtime Database"""
    occupancy = counter.calculate_occupancy()
    current_stop = counter.get_current_stop()
    stops = counter.designated_stops_list
    next_stop_index = (counter.current_stop_index + 1) % len(stops)
    next_stop = stops[next_stop_index]

    firebase_ref.set({
        "shuttle_id": "shuttle_001",
        "current_count": occupancy["passenger_count"],
        "available_seats": occupancy["available_seats"],
        "occupancy_status": occupancy["occupancy_status"],
        "current_stop": current_stop,
        "next_stop": next_stop,
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    print(f"  Firebase | count: {occupancy['passenger_count']} | stop: {current_stop} | next: {next_stop} | status: {occupancy['occupancy_status']}")


def main():
    print("\n" + "="*60)
    print("  APCOMS - AI Passenger Counting System")
    print("  Makerere University Driverless E-Shuttle")
    print("="*60 + "\n")

    print("Initializing Counting Logic...")
    counter = CountingLogic(total_capacity=TOTAL_CAPACITY)
    counter.initialize()
    print(f"Resuming from count: {counter.passenger_count} passengers")
    print(f"Current stop: {counter.get_current_stop()}\n")

    print("Connecting to Firebase...")
    firebase_ref = setup_firebase()
    print("Firebase connected\n")

    print("Loading YOLOv8n model...")
    model = YOLO("models/yolov8n.pt")
    print("YOLOv8n ready\n")

    print("Starting camera...")
    camera = CameraInterface(source=CAMERA_SOURCE)
    camera.start()
    print("Camera ready\n")

    print("="*60)
    print("  LIVE PASSENGER DETECTION STARTING")
    print("="*60 + "\n")

    frame_count = 0
    last_person_count = 0
    track_id_counter = 1000

    while True:
        frame = camera.capture_frame()
        if frame is None:
            print("\nVideo ended.")
            break

        frame_count += 1

        if frame_count % 10 == 0:
            results = model(frame, verbose=False)

            current_persons = 0
            for result in results:
                for box in result.boxes:
                    if int(box.cls[0]) == 0:
                        current_persons += 1
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, "Person", (x1, y1-10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            if current_persons > last_person_count:
                track_id_counter += 1
                track = {
                    "track_id": track_id_counter,
                    "previous_centroid": (960, 200),
                    "current_centroid": (960, 700)
                }
                counter.update_count(track)
                print(f"\nBoarding event detected at {counter.get_current_stop()}")
                push_to_firebase(firebase_ref, counter)

            elif current_persons < last_person_count and counter.passenger_count > 0:
                track_id_counter += 1
                track = {
                    "track_id": track_id_counter,
                    "previous_centroid": (960, 700),
                    "current_centroid": (960, 200)
                }
                counter.update_count(track)
                print(f"\nAlighting event detected at {counter.get_current_stop()}")
                push_to_firebase(firebase_ref, counter)

            last_person_count = current_persons

            cv2.putText(frame, f"Passengers: {counter.passenger_count}/{TOTAL_CAPACITY}",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame, f"Available: {counter.available_seats}",
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"Stop: {counter.get_current_stop()}",
                       (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

            cv2.imshow("APCOMS - Live Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\nDemo stopped by user.")
            break

    counter.advance_stop()
    print(f"\nAdvanced to next stop: {counter.get_current_stop()}")

    camera.stop()
    cv2.destroyAllWindows()

    print("\n" + "="*60)
    print("  DEMO COMPLETE")
    print(f"  Final passenger count: {counter.passenger_count}")
    print(f"  Current stop: {counter.get_current_stop()}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
