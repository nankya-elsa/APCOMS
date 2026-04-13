import cv2
import sqlite3
import os
import sys
import time
import datetime
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from camera_interface import CameraInterface

# ─────────────────────────────────────────
# LOAD ENVIRONMENT VARIABLES
# ─────────────────────────────────────────
load_dotenv()

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
SHUTTLE_ID = os.getenv("SHUTTLE_ID")
TOTAL_CAPACITY = int(os.getenv("TOTAL_CAPACITY"))
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE")

# ─────────────────────────────────────────
# SETUP SQLITE
# ─────────────────────────────────────────
def setup_sqlite():
    """Creates the local SQLite database and passenger_events table"""
    conn = sqlite3.connect("local_database/apcoms_demo.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS passenger_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shuttle_id TEXT,
            timestamp TEXT,
            event_type TEXT,
            passenger_count INTEGER,
            available_seats INTEGER
        )
    """)
    conn.commit()
    return conn

# ─────────────────────────────────────────
# SETUP FIREBASE
# ─────────────────────────────────────────
def setup_firebase():
    """Initializes Firebase connection"""
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred, {
        "databaseURL": FIREBASE_DATABASE_URL
    })
    return db.reference(f"shuttles/{SHUTTLE_ID}")

# ─────────────────────────────────────────
# LOG TO SQLITE
# ─────────────────────────────────────────
def log_to_sqlite(conn, event_type, passenger_count, available_seats):
    """Writes a passenger event to SQLite"""
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO passenger_events
        (shuttle_id, timestamp, event_type, passenger_count, available_seats)
        VALUES (?, ?, ?, ?, ?)
    """, (SHUTTLE_ID, timestamp, event_type, passenger_count, available_seats))
    conn.commit()
    print(f"  SQLite  | {timestamp} | {event_type} | count: {passenger_count} | available: {available_seats}")

# ─────────────────────────────────────────
# PUSH TO FIREBASE
# ─────────────────────────────────────────
def push_to_firebase(firebase_ref, passenger_count, available_seats):
    """Pushes current occupancy state to Firebase"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if available_seats > 5:
        status = "Available"
    elif available_seats > 0:
        status = "Nearly Full"
    else:
        status = "Full"

    firebase_ref.set({
        "shuttle_id": SHUTTLE_ID,
        "current_count": passenger_count,
        "available_seats": available_seats,
        "occupancy_status": status,
        "last_updated": timestamp
    })
    print(f"  Firebase  | {timestamp} | count: {passenger_count} | status: {status}")

# ─────────────────────────────────────────
# MAIN DEMO
# ─────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  APCOMS DEMO - AI Passenger Counting System")
    print("  Makerere University Driverless E-Shuttle")
    print("="*60 + "\n")

    # setup
    print("Setting up SQLite database...")
    conn = setup_sqlite()
    print("SQLite ready \n")

    print("Connecting to Firebase...")
    firebase_ref = setup_firebase()
    print("Firebase connected \n")

    print("Loading YOLOv8n model...")
    model = YOLO("models/yolov8n.pt")
    print("YOLOv8n ready \n")

    print("Starting camera...")
    camera = CameraInterface(source=CAMERA_SOURCE)
    camera.start()
    print("Camera ready \n")

    print("="*60)
    print("  LIVE PASSENGER DETECTION STARTING...")
    print("="*60 + "\n")

    passenger_count = 0
    available_seats = TOTAL_CAPACITY
    frame_count = 0
    last_log_time = time.time()
    last_person_count = 0

    while True:
        frame = camera.capture_frame()
        if frame is None:
            print("\n video ended!")
            break

        frame_count += 1

        # run YOLOv8n detection every 10 frames for speed
        if frame_count % 10 == 0:
            results = model(frame, verbose=False)

            # count persons detected in this frame
            current_persons = 0
            for result in results:
                for box in result.boxes:
                    if int(box.cls[0]) == 0:  # class 0 = person
                        current_persons += 1

                        # draw bounding box on frame
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, "Person", (x1, y1-10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # simulate boarding if more people detected than before
            if current_persons > last_person_count:
                passenger_count = min(passenger_count + 1, TOTAL_CAPACITY)
                available_seats = TOTAL_CAPACITY - passenger_count
                print(f"\n Person detected - BOARDING event!")
                log_to_sqlite(conn, "boarding", passenger_count, available_seats)
                push_to_firebase(firebase_ref, passenger_count, available_seats)
                last_log_time = time.time()

            last_person_count = current_persons

            # draw occupancy info on frame
            cv2.putText(frame, f"Passengers: {passenger_count}/{TOTAL_CAPACITY}",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame, f"Available: {available_seats}",
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # show frame
            cv2.imshow("APCOMS - Live Detection", frame)

        # press q to quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n Demo stopped by user!")
            break

    # cleanup
    camera.stop()
    cv2.destroyAllWindows()
    conn.close()

    print("\n" + "="*60)
    print("  DEMO COMPLETE!")
    print(f"  Total frames processed: {frame_count}")
    print(f"  Final passenger count: {passenger_count}")
    print(f"  Check local_database/apcoms_demo.db for logged data!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
