import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_logger import DataLogger

TEST_DB = "local_database/test_apcoms.db"


class TestDataLoggerInitialization:

    def test_data_logger_initializes_successfully(self):
        """
        Test that DataLogger initializes correctly so the system
        has a logger ready to write passenger events and diagnostic
        data to the SQLite database
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        assert logger is not None

    def test_shuttle_id_is_stored_correctly(self):
        """
        Test that DataLogger stores the shuttle ID so all logged events
        and diagnostics are correctly tagged to the right shuttle
        for accurate data analysis and route optimization
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        assert logger.shuttle_id == "shuttle_001"

    def test_db_path_is_stored_correctly(self):
        """
        Test that DataLogger stores the database path so the system
        knows where to write passenger events and diagnostic logs
        on the local storage device
        """
        logger = DataLogger(shuttle_id="shuttle_001")
        assert logger.db_path == "local_database/apcoms.db"

    def test_database_created_on_initialization(self):
        """
        Test that initialize() creates the SQLite database file so
        the system has a local storage ready to persist passenger
        events and diagnostic logs without requiring manual setup
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        assert os.path.exists(logger.db_path)

    def test_passenger_events_table_exists_after_initialization(self):
        """
        Test that passenger_events table exists after initialize() so
        the DataLogger can immediately start writing boarding and
        alighting events without any additional setup
        """
        import sqlite3
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        conn = sqlite3.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='passenger_events'
        """)
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_diagnostic_log_table_exists_after_initialization(self):
        """
        Test that diagnostic_log table exists after initialize() so
        the DataLogger can immediately start writing system health
        and performance metrics from the System Monitor Component
        """
        import sqlite3
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        conn = sqlite3.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='diagnostic_log'
        """)
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_initialize_logs_success_message(self, caplog):
        """
        Test that initialize() logs a success message when the database
        is ready so the System Monitor knows the DataLogger is
        operational and ready to persist passenger events
        """
        import logging
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        with caplog.at_level(logging.INFO):
            logger.initialize()
        assert "SQLite database connected successfully" in caplog.text


class TestEventLogging:

    def test_log_event_returns_true_on_success(self):
        """
        Test that log_event() returns True when a passenger event is
        successfully written to SQLite so the system knows the event
        has been persisted and will not be lost
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        result = logger.log_event(event_data)
        assert result == True

    def test_logged_event_contains_direction(self):
        """
        Test that log_event() correctly stores the direction so analytics
        can distinguish between boarding and alighting events for
        accurate passenger flow analysis
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        logger.log_event(event_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT direction FROM passenger_events ORDER BY event_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == "boarding"

    def test_logged_event_contains_passenger_count(self):
        """
        Test that log_event() correctly stores passenger count so
        historical data can be used for route optimization and
        demand forecasting
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        logger.log_event(event_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT passenger_count FROM passenger_events ORDER BY event_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == 5

    def test_logged_event_contains_available_seats(self):
        """
        Test that log_event() correctly stores available seats so
        historical occupancy patterns can be analysed for evidence
        based shuttle service planning
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        logger.log_event(event_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT available_seats FROM passenger_events ORDER BY event_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == 15

    def test_logged_event_contains_stop_location(self):
        """
        Test that log_event() correctly stores stop location so
        analytics can identify which stops have highest passenger
        demand for route optimization
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        logger.log_event(event_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT stop_location FROM passenger_events ORDER BY event_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == "Western Gate"

    def test_logged_event_contains_timestamp(self):
        """
        Test that log_event() correctly stores timestamp so events
        can be analysed by time of day to identify peak hours
        and optimize shuttle scheduling
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        logger.log_event(event_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM passenger_events ORDER BY event_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] is not None

    def test_log_event_logs_success_message(self, caplog):
        """
        Test that log_event() logs a success message after writing
        to SQLite so the System Monitor knows the event has been
        persisted successfully
        """
        import logging
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        event_data = {
            "direction": "boarding",
            "passenger_count": 5,
            "available_seats": 15,
            "stop_location": "Western Gate"
        }
        with caplog.at_level(logging.INFO):
            logger.log_event(event_data)
        assert "Event logged successfully" in caplog.text


class TestDiagnosticLogging:

    def test_log_diagnostic_returns_true_on_success(self):
        """
        Test that log_diagnostic() returns True when diagnostic data
        is successfully written to SQLite so the System Monitor knows
        performance metrics have been persisted for analysis
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        result = logger.log_diagnostic(diagnostic_data)
        assert result == True

    def test_logged_diagnostic_contains_log_type(self):
        """
        Test that log_diagnostic() correctly stores log type so the
        Flask Dashboard can filter and display errors warnings and
        info messages separately for efficient troubleshooting
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        logger.log_diagnostic(diagnostic_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT log_type FROM diagnostic_log ORDER BY log_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == "info"

    def test_logged_diagnostic_contains_camera_status(self):
        """
        Test that log_diagnostic() correctly stores camera status so
        maintenance personnel can track camera health over time and
        identify recurring hardware issues
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        logger.log_diagnostic(diagnostic_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT camera_status FROM diagnostic_log ORDER BY log_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == "ok"

    def test_logged_diagnostic_contains_fps(self):
        """
        Test that log_diagnostic() correctly stores FPS so the System
        Monitor can track AI model performance over time and detect
        performance degradation trends
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        logger.log_diagnostic(diagnostic_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT fps FROM diagnostic_log ORDER BY log_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == 28.5

    def test_logged_diagnostic_contains_latency_ms(self):
        """
        Test that log_diagnostic() correctly stores latency so the
        System Monitor can verify processing stays below 100ms
        per frame as required by NFR-CM-1.4
        """
        import sqlite3 as sql
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        logger.log_diagnostic(diagnostic_data)
        conn = sql.connect(logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT latency_ms FROM diagnostic_log ORDER BY log_id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        assert result[0] == 35.2

    def test_log_diagnostic_logs_success_message(self, caplog):
        """
        Test that log_diagnostic() logs a success message after writing
        to SQLite so the System Monitor knows diagnostic data has been
        persisted successfully
        """
        import logging
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        diagnostic_data = {
            "log_type": "info",
            "camera_status": "ok",
            "fps": 28.5,
            "latency_ms": 35.2
        }
        with caplog.at_level(logging.INFO):
            logger.log_diagnostic(diagnostic_data)
        assert "Diagnostic entry logged successfully" in caplog.text


class TestStorageMonitoring:

    def test_monitor_storage_logs_warning_when_storage_is_low(self, caplog):
        """
        Test that monitor_storage() logs a warning when available storage
        is below the minimum threshold so the System Monitor can alert
        administrators before the database runs out of space
        """
        import logging
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        with caplog.at_level(logging.WARNING):
            logger.monitor_storage(available_gb=0.5)
        assert "Storage running low" in caplog.text

    def test_monitor_storage_returns_storage_info(self):
        """
        Test that monitor_storage() returns storage information so the
        Flask Dashboard can display current storage status to system
        administrators for proactive maintenance
        """
        logger = DataLogger(shuttle_id="shuttle_001", db_path=TEST_DB)
        logger.initialize()
        result = logger.monitor_storage(available_gb=10.0)
        assert result is not None
        assert "available_gb" in result
