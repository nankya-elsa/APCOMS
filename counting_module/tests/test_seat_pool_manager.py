"""
Tests for the SeatPoolManager component.

SeatPoolManager owns the available_seats stored field in SQLite
system_state. In the soft-hold reservation model, available_seats
is maintained explicitly on every event that affects it:

    Book        -> decrement (seat held)
    Cancel      -> increment (seat returned)
    No-show     -> increment (seat returned)
    Alight      -> increment (seat returned)

This component is the single source of truth for those mutations.
Other components (NoShowCanceller, CountingLogic, the Firebase
booking listener) call increment/decrement here rather than
writing to system_state directly. Each mutation also syncs the
full occupancy payload to Firebase so the dashboard, OLED, and
mobile app stay consistent.

SQLite and firebase_sync are mocked or pointed at TEST_DB
throughout these tests so the component can be verified in
pure isolation.
"""

import os
import sys
import sqlite3
import json
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from seat_pool_manager import SeatPoolManager

TEST_DB = "local_database/test_apcoms.db"


def _reset_test_db():
    """Drop and recreate system_state table for a clean slate."""
    os.makedirs("local_database", exist_ok=True)
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS system_state")
    cursor.execute("""
        CREATE TABLE system_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


def _set_state(key, value):
    """Helper to seed a value into system_state for tests."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def _get_state(key):
    """Helper to read a value from system_state for assertions."""
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_state WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


class TestSeatPoolManagerInitialization:

    def setup_method(self):
        _reset_test_db()

    def test_manager_initializes_with_required_args(self):
        """
        SeatPoolManager should construct cleanly with total_capacity
        and db_path so it knows the upper bound for increments and
        where to persist available_seats.
        """
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        assert manager is not None
        assert manager.total_capacity == 20
        assert manager.db_path == TEST_DB

    def test_manager_accepts_optional_firebase_sync(self):
        """
        firebase_sync is optional so the manager can be tested in
        isolation and gracefully degrade if Firebase is unavailable.
        """
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        assert manager.firebase_sync is mock_sync

    def test_firebase_sync_defaults_to_none(self):
        """
        When firebase_sync is not provided, the attribute should be
        None so increment/decrement know to skip the sync step
        rather than crashing.
        """
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        assert manager.firebase_sync is None


class TestGetCurrent:

    def setup_method(self):
        _reset_test_db()

    def test_returns_stored_value_from_sqlite(self):
        """
        get_current() reads available_seats from system_state. This
        is the authoritative source — never derived from
        total_capacity minus passenger_count.
        """
        _set_state("available_seats", 12)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        assert manager.get_current() == 12

    def test_defaults_to_total_capacity_when_unset(self):
        """
        Fresh deployment: no available_seats entry in system_state
        yet. The manager should default to total_capacity because
        an empty shuttle with zero bookings has all seats available.
        """
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        assert manager.get_current() == 20

    def test_firebase_payload_honors_env_total_capacity_over_stale_sqlite_value(self, monkeypatch):
        """
        Firebase payloads should use the env-based effective capacity
        instead of stale SQLite seat values when the shuttle size changes.
        """
        monkeypatch.setenv("TOTAL_CAPACITY", "15")
        _set_state("available_seats", 25)
        _set_state("current_count", 0)
        _set_state("current_stop", "CONAS")
        _set_state("current_stop_index", 2)
        _set_state("designated_stops", json.dumps(["A", "B", "CONAS", "D"]))

        mock_sync = MagicMock()
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync)
        manager._sync_to_firebase()

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["available_seats"] == 15

    def test_handles_non_integer_stored_value_gracefully(self):
        """
        If something corrupts available_seats to a non-integer
        value, get_current() should fall back to total_capacity
        rather than crash. Defensive — we'd rather show "shuttle
        is empty" than take the system down.
        """
        _set_state("available_seats", "not_a_number")
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        assert manager.get_current() == 20

    def test_blank_env_capacity_falls_back_to_default_capacity(self, monkeypatch):
        """
        A blank TOTAL_CAPACITY in the environment should behave like
        an unset value and not allow a stale SQLite seat count to
        override the effective capacity.
        """
        monkeypatch.setenv("TOTAL_CAPACITY", "")
        _set_state("available_seats", 10)
        _set_state("current_count", 0)
        _set_state("current_stop", "CONAS")
        _set_state("current_stop_index", 2)
        _set_state("designated_stops", json.dumps(["A", "B", "CONAS", "D"]))

        mock_sync = MagicMock()
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync)
        manager._sync_to_firebase()

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["available_seats"] == 20


class TestIncrement:

    def setup_method(self):
        _reset_test_db()

    def test_increments_available_seats_by_one(self):
        """
        increment() should bump available_seats by 1 in SQLite. The
        canonical case: a no-show is cancelled, the held seat
        returns to the pool, and the stored field reflects it.
        """
        _set_state("available_seats", 10)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.increment(reason="no_show")
        assert int(_get_state("available_seats")) == 11

    def test_caps_at_total_capacity(self):
        """
        available_seats can never exceed total_capacity. If a
        spurious release event fires when the shuttle is already
        empty, the value must not climb above the seat limit.
        """
        _set_state("available_seats", 20)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.increment(reason="no_show")
        assert int(_get_state("available_seats")) == 20

    def test_logs_increment_with_reason(self, caplog):
        """
        Each mutation should log the reason so the diagnostic log
        carries a clear audit trail. Operators investigating an
        unexpected seat count change must be able to see why.
        """
        import logging
        _set_state("available_seats", 5)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        with caplog.at_level(logging.INFO):
            manager.increment(reason="alight")
        assert "Seat released" in caplog.text
        assert "alight" in caplog.text

    def test_calls_firebase_sync_when_present(self):
        """
        After updating SQLite, the new value must be pushed to
        Firebase so the mobile app and dashboard see the change.
        We verify sync_to_firebase was called.
        """
        _set_state("available_seats", 10)
        _set_state("current_count", 3)
        _set_state("current_stop", "CONAS")
        _set_state("current_stop_index", 2)
        _set_state(
            "designated_stops",
            json.dumps(["A", "B", "CONAS", "D"]),
        )
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.increment(reason="cancel")
        mock_sync.sync_to_firebase.assert_called_once()

    def test_increment_graceful_without_firebase_sync(self):
        """
        With no firebase_sync provided, increment() should still
        update SQLite cleanly and not crash. Offline-first means
        local state always wins.
        """
        _set_state("available_seats", 10)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.increment(reason="alight")
        assert int(_get_state("available_seats")) == 11


class TestDecrement:

    def setup_method(self):
        _reset_test_db()

    def test_decrements_available_seats_by_one(self):
        """
        decrement() should reduce available_seats by 1 in SQLite.
        The canonical case: a user creates a booking, the seat is
        held, and the stored field reflects one less available.
        """
        _set_state("available_seats", 10)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.decrement(reason="book")
        assert int(_get_state("available_seats")) == 9

    def test_caps_at_zero(self):
        """
        available_seats must never go negative. If a spurious hold
        event fires when no seats are available, the value must
        stay at zero rather than become -1.
        """
        _set_state("available_seats", 0)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.decrement(reason="book")
        assert int(_get_state("available_seats")) == 0

    def test_logs_decrement_with_reason(self, caplog):
        """
        Same audit trail principle as increment — the diagnostic
        log must carry the reason so investigators can trace why
        a seat got held.
        """
        import logging
        _set_state("available_seats", 10)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        with caplog.at_level(logging.INFO):
            manager.decrement(reason="book")
        assert "Seat held" in caplog.text
        assert "book" in caplog.text

    def test_calls_firebase_sync_when_present(self):
        """
        After SQLite is updated, Firebase must get the new value
        so Cissy's app refreshes the displayed available_seats
        for every other user looking at this shuttle.
        """
        _set_state("available_seats", 10)
        _set_state("current_count", 3)
        _set_state("current_stop", "CONAS")
        _set_state("current_stop_index", 2)
        _set_state(
            "designated_stops",
            json.dumps(["A", "B", "CONAS", "D"]),
        )
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.decrement(reason="book")
        mock_sync.sync_to_firebase.assert_called_once()

    def test_decrement_graceful_without_firebase_sync(self):
        """
        With no firebase_sync, decrement() still mutates SQLite
        without crashing. Offline-first principle.
        """
        _set_state("available_seats", 10)
        manager = SeatPoolManager(total_capacity=20, db_path=TEST_DB)
        manager.decrement(reason="book")
        assert int(_get_state("available_seats")) == 9


class TestFirebaseSyncPayload:
    """
    Verifies that the payload pushed to Firebase contains all the
    keys FirebaseSyncComponent expects so the set() write doesn't
    nuke fields. The payload must include passenger_count,
    available_seats, occupancy_status, current_stop, next_stop.
    """

    def setup_method(self):
        _reset_test_db()
        _set_state("current_count", 4)
        _set_state("current_stop", "CONAS")
        _set_state("current_stop_index", 2)
        _set_state(
            "designated_stops",
            json.dumps(["Western Gate", "CEDAT", "CONAS", "Main Library"]),
        )

    def test_payload_contains_all_required_keys(self):
        """
        FirebaseSyncComponent.sync_to_firebase() does a full
        overwrite of shuttles/{id} via .set(). The payload must
        therefore include every key the mobile app and dashboard
        rely on, otherwise downstream readers see missing fields.
        """
        _set_state("available_seats", 10)
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.increment(reason="alight")

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert "passenger_count" in payload
        assert "available_seats" in payload
        assert "occupancy_status" in payload
        assert "current_stop" in payload
        assert "next_stop" in payload

    def test_payload_reflects_post_mutation_available_seats(self):
        """
        The available_seats value in the synced payload must be
        the value AFTER the increment/decrement, not before.
        Otherwise Firebase would be permanently one event behind.
        """
        _set_state("available_seats", 10)
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.decrement(reason="book")

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["available_seats"] == 9

    @pytest.mark.parametrize('current_idx,expected_next', [(3, 0)])
    def test_payload_next_stop_wraps_around(self, current_idx, expected_next, monkeypatch):
        """
        When current_stop_index is the last stop, next_stop must
        wrap to index 0 (start of the route again). The same
        wraparound CountingLogic.advance_stop uses.
        """
        from unittest.mock import patch
        # Mock designated stops to be just 4 stops for this test
        test_stops = ["Stop A", "Stop B", "Stop C", "Stop D"]

        with patch('seat_pool_manager.get_designated_stops', return_value=test_stops):
            _set_state("available_seats", 10)
            _set_state("current_stop_index", current_idx)  # last of 4 stops
            mock_sync = MagicMock()
            manager = SeatPoolManager(
                total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
            )
            manager.increment(reason="alight")

            payload = mock_sync.sync_to_firebase.call_args[0][0]
            # After wraparound from index 3, next should be index 0 (Stop A)
            assert payload["next_stop"] == test_stops[expected_next]

    def test_occupancy_status_available_when_seats_above_5(self):
        """
        Matches CountingLogic's occupancy thresholds: > 5 seats
        free means status is Available.
        """
        _set_state("available_seats", 9)
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.increment(reason="alight")  # 9 -> 10

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["occupancy_status"] == "Available"

    def test_occupancy_status_nearly_full_when_seats_between_1_and_5(self):
        """
        Matches CountingLogic's occupancy thresholds: 1-5 seats
        free means status is Nearly Full.
        """
        _set_state("available_seats", 4)
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.increment(reason="alight")  # 4 -> 5

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["occupancy_status"] == "Nearly Full"

    def test_occupancy_status_full_when_zero_seats(self):
        """
        Matches CountingLogic's occupancy thresholds: 0 seats
        free means status is Full.
        """
        _set_state("available_seats", 1)
        mock_sync = MagicMock()
        manager = SeatPoolManager(
            total_capacity=20, db_path=TEST_DB, firebase_sync=mock_sync
        )
        manager.decrement(reason="book")  # 1 -> 0

        payload = mock_sync.sync_to_firebase.call_args[0][0]
        assert payload["occupancy_status"] == "Full"
