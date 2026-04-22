import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class FirebaseSyncComponent:

    def __init__(self, shuttle_id):
        self.shuttle_id = shuttle_id
        self.network_status = "disconnected"
        self.offline_queue = []
        self.firebase_ref = None

    def initialize(self):
        """
        Loads Firebase configuration and establishes connection.
        Sets network_status to connected on success or offline on failure.
        Logs success or warning accordingly.
        """
        try:
            load_dotenv()
            import firebase_admin
            from firebase_admin import credentials, db

            if not firebase_admin._apps:
                cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
                db_url = os.getenv("FIREBASE_DATABASE_URL")
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {"databaseURL": db_url})

            self.firebase_ref = db.reference(f"shuttles/{self.shuttle_id}")
            self.network_status = "connected"
            logger.info("Firebase connection established")

        except Exception:
            self.network_status = "offline"
            logger.warning("Firebase connection failed")

    def sync_to_firebase(self, occupancy_data):
        """
        Pushes occupancy data to Firebase Realtime Database.
        Returns True on success, False on failure.
        Queues data locally if network is unavailable.
        """
        import datetime

        if self.network_status == "connected":
            try:
                payload = {
                    "shuttle_id": self.shuttle_id,
                    "current_count": occupancy_data["passenger_count"],
                    "available_seats": occupancy_data["available_seats"],
                    "occupancy_status": occupancy_data["occupancy_status"],
                    "current_stop": occupancy_data.get("current_stop", "Unknown"),
                    "next_stop": occupancy_data.get("next_stop", "Unknown"),
                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self.firebase_ref.set(payload)
                logger.info("Occupancy synced to Firebase successfully")
                if self.offline_queue:
                    self.sync_offline_queue()
                return True
            except Exception:
                logger.warning("Firebase write failed")
                self.offline_queue.append(occupancy_data)
                return False
        else:
            self.offline_queue.append(occupancy_data)
            logger.info("Device offline, update queued locally")
            return False

    def sync_offline_queue(self):
        """
        Syncs all queued occupancy updates to Firebase when connectivity
        is restored. Removes successfully synced items from the queue.
        Logs success for each synced update.
        """
        synced = []
        for queued_data in self.offline_queue:
            try:
                import datetime
                payload = {
                    "shuttle_id": self.shuttle_id,
                    "current_count": queued_data["passenger_count"],
                    "available_seats": queued_data["available_seats"],
                    "occupancy_status": queued_data["occupancy_status"],
                    "current_stop": queued_data.get("current_stop", "Unknown"),
                    "next_stop": queued_data.get("next_stop", "Unknown"),
                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self.firebase_ref.set(payload)
                synced.append(queued_data)
                logger.info("Queued update synced successfully")
            except Exception:
                logger.warning("Failed to sync queued update")
                break

        for item in synced:
            self.offline_queue.remove(item)

    def monitor_connectivity(self):
        """
        Checks Firebase connectivity by attempting to read from the
        database reference. Updates network_status accordingly and
        triggers offline queue sync when connection is restored.
        Logs warning when connection is lost.
        """
        try:
            if self.firebase_ref is not None:
                self.firebase_ref.get()
                self.network_status = "connected"
                if self.offline_queue:
                    self.sync_offline_queue()
            else:
                self.network_status = "offline"
                logger.warning("Network connectivity lost")
        except Exception:
            self.network_status = "offline"
            logger.warning("Network connectivity lost")
