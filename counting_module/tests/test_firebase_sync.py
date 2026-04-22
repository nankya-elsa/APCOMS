import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from firebase_sync import FirebaseSyncComponent


class TestFirebaseSyncInitialization:

    def test_firebase_sync_initializes_successfully(self):
        """
        Test that FirebaseSyncComponent initializes correctly so the
        system has a sync component ready to push occupancy data to
        Firebase Realtime Database
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        assert sync is not None

    def test_shuttle_id_is_stored_correctly(self):
        """
        Test that FirebaseSyncComponent stores the shuttle ID so the
        system knows which shuttle's data to push to Firebase and
        the mobile app can identify the correct shuttle
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        assert sync.shuttle_id == "shuttle_001"

    def test_network_status_is_disconnected_before_initialization(self):
        """
        Test that network status is disconnected before initialize()
        is called to confirm the system is not attempting to sync
        before a Firebase connection has been established
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        assert sync.network_status == "disconnected"

    def test_offline_queue_is_empty_before_initialization(self):
        """
        Test that offline queue is empty before initialize() is called
        to confirm no stale queued updates exist when the system
        first starts up
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        assert sync.offline_queue == []

    def test_network_status_connected_after_initialization(self):
        """
        Test that network status changes to connected after initialize()
        is called successfully so the system knows it can push
        occupancy data to Firebase Realtime Database
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()
        assert sync.network_status == "connected"

    def test_initialize_logs_success_message(self, caplog):
        """
        Test that initialize() logs a success message when Firebase
        connection is established so the System Monitor knows the
        sync component is ready to push occupancy data
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        with caplog.at_level(logging.INFO):
            sync.initialize()
        assert "Firebase connection established" in caplog.text


class TestSyncToFirebase:

    def test_sync_to_firebase_returns_true_on_success(self):
        """
        Test that sync_to_firebase() returns True when data is
        successfully pushed to Firebase so the system knows the
        occupancy update reached the mobile app
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        result = sync.sync_to_firebase(occupancy_data)
        assert result == True

    def test_payload_contains_passenger_count(self):
        """
        Test that sync_to_firebase() includes passenger count in the
        payload so the mobile app can display accurate occupancy numbers
        to students checking seat availability
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert snapshot["current_count"] == 8

    def test_payload_contains_available_seats(self):
        """
        Test that sync_to_firebase() includes available seats in the
        payload so the mobile app can show students exactly how many
        seats are left before they go to the shuttle stop
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert snapshot["available_seats"] == 12

    def test_payload_contains_occupancy_status(self):
        """
        Test that sync_to_firebase() includes occupancy status in the
        payload so the mobile app can display the correct color coded
        status badge to students
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert snapshot["occupancy_status"] == "Available"

    def test_payload_contains_current_stop(self):
        """
        Test that sync_to_firebase() includes current stop in the
        payload so the mobile app can show students the shuttle's
        current location along the campus route
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert snapshot["current_stop"] == "Western Gate"

    def test_payload_contains_next_stop(self):
        """
        Test that sync_to_firebase() includes next stop in the payload
        so the mobile app can inform students where the shuttle is
        heading next along the predefined campus route
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert snapshot["next_stop"] == "CEDAT"

    def test_payload_contains_timestamp(self):
        """
        Test that sync_to_firebase() includes last updated timestamp
        so the mobile app can show students when the data was last
        refreshed and warn them if data is stale
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        snapshot = sync.firebase_ref.get()
        assert "last_updated" in snapshot

    def test_queues_data_when_offline(self):
        """
        Test that sync_to_firebase() adds data to offline queue when
        network is unavailable so no occupancy updates are lost during
        network outages as required by FR-CM-6.3
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.network_status = "offline"

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        assert len(sync.offline_queue) == 1

    def test_logs_warning_when_offline(self, caplog):
        """
        Test that sync_to_firebase() logs when device is offline so
        the System Monitor knows updates are being queued locally
        and not reaching the mobile app in real time
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.network_status = "offline"

        occupancy_data = {
            "passenger_count": 8,
            "available_seats": 12,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        with caplog.at_level(logging.INFO):
            sync.sync_to_firebase(occupancy_data)
        assert "Device offline, update queued locally" in caplog.text


class TestOfflineQueue:

    def test_offline_queue_starts_empty(self):
        """
        Test that offline queue starts empty on initialization so
        the system begins with a clean slate and no stale queued
        updates from previous sessions
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        assert sync.offline_queue == []

    def test_adds_to_queue_when_offline(self):
        """
        Test that sync_to_firebase() adds occupancy data to the
        offline queue when network is unavailable to ensure no
        updates are lost during network outages
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.network_status = "offline"

        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.sync_to_firebase(occupancy_data)
        assert len(sync.offline_queue) == 1

    def test_queue_cleared_after_successful_sync(self):
        """
        Test that offline queue is cleared after successfully syncing
        queued updates to Firebase so the system does not send
        duplicate updates when connectivity is restored
        """
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.offline_queue.append(occupancy_data)
        sync.sync_offline_queue()
        assert len(sync.offline_queue) == 0

    def test_logs_success_when_queued_update_synced(self, caplog):
        """
        Test that sync_offline_queue() logs success when a queued
        update is synced to Firebase so the System Monitor knows
        the offline queue has been cleared successfully
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()

        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available",
            "current_stop": "Western Gate",
            "next_stop": "CEDAT"
        }

        sync.offline_queue.append(occupancy_data)
        with caplog.at_level(logging.INFO):
            sync.sync_offline_queue()
        assert "Queued update synced successfully" in caplog.text


class TestConnectivityMonitoring:

    def test_monitor_connectivity_updates_status_to_connected(self, caplog):
        """
        Test that monitor_connectivity() sets network_status to connected
        when Firebase is reachable so the system knows it can resume
        pushing occupancy updates to the mobile app
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.initialize()
        with caplog.at_level(logging.INFO):
            sync.monitor_connectivity()
        assert sync.network_status == "connected"

    def test_monitor_connectivity_updates_status_to_offline(self, caplog):
        """
        Test that monitor_connectivity() sets network_status to offline
        when Firebase is unreachable so the system switches to offline
        queue mode without crashing
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.network_status = "offline"
        sync.firebase_ref = None
        with caplog.at_level(logging.WARNING):
            sync.monitor_connectivity()
        assert sync.network_status == "offline"

    def test_monitor_connectivity_logs_warning_when_connection_lost(self, caplog):
        """
        Test that monitor_connectivity() logs a warning when connection
        is lost so the System Monitor can alert maintenance personnel
        that the shuttle has lost Firebase connectivity
        """
        import logging
        sync = FirebaseSyncComponent(shuttle_id="shuttle_001")
        sync.network_status = "offline"
        sync.firebase_ref = None
        with caplog.at_level(logging.WARNING):
            sync.monitor_connectivity()
        assert "Network connectivity lost" in caplog.text
