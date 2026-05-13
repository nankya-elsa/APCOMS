"""
Tests for the ScenarioManager component.

The ScenarioManager is responsible for finding scenario video files
on disk, tracking which scenario plays next via SQLite system_state,
and advancing the sequence as main.py finishes each run.

This component decouples main.py from scenario bookkeeping so
each run simply asks "what video should I play?" and ScenarioManager
returns the path without main.py needing to know about file globbing,
sorting, or state persistence.
"""

import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from scenario_manager import ScenarioManager

TEST_DB = "local_database/test_apcoms.db"


class TestScenarioManagerInitialization:
    """Tests covering ScenarioManager construction and defaults."""

    def test_scenario_manager_initializes_with_defaults(self):
        """
        ScenarioManager should instantiate without arguments and
        accept sensible defaults for scenario folder and db path.
        We verify the instance exists and core attributes are
        present and set to expected values.
        """
        manager = ScenarioManager()
        assert manager is not None
        assert hasattr(manager, "scenarios_dir")
        assert hasattr(manager, "db_path")

    def test_scenario_manager_accepts_custom_scenarios_dir(self):
        """
        For testing and custom deployments, the scenarios directory
        can be overridden at construction time. This lets test
        fixtures point to a temporary directory without polluting
        the production data/ folder.
        """
        manager = ScenarioManager(scenarios_dir="custom/path")
        assert manager.scenarios_dir == "custom/path"

    def test_scenario_manager_accepts_custom_db_path(self):
        """
        The db_path parameter lets tests point ScenarioManager at
        the test database, preventing test runs from polluting
        production state. Follows the same pattern as DataLogger
        and CountingLogic.
        """
        manager = ScenarioManager(db_path=TEST_DB)
        assert manager.db_path == TEST_DB


class TestListScenarios:
    """Tests covering discovery of scenario video files on disk."""

    def test_list_scenarios_returns_sorted_mp4_files(self, tmp_path):
        """
        list_scenarios() should find all .mp4 files in the scenarios
        directory and return them sorted alphabetically. The sorted
        order ensures '01_*' plays before '02_*' regardless of how
        the OS lists files internally.
        """
        # use pytest's tmp_path to create real files for this test
        (tmp_path / "02_second.mp4").write_text("dummy")
        (tmp_path / "01_first.mp4").write_text("dummy")
        (tmp_path / "03_third.mp4").write_text("dummy")

        manager = ScenarioManager(scenarios_dir=str(tmp_path))
        result = manager.list_scenarios()

        assert len(result) == 3
        assert result[0].endswith("01_first.mp4")
        assert result[1].endswith("02_second.mp4")
        assert result[2].endswith("03_third.mp4")

    def test_list_scenarios_ignores_non_video_files(self, tmp_path):
        """
        Only .mp4 files should be returned. README files, hidden
        files, and other non-video files in the scenarios directory
        should be quietly ignored so the directory can hold
        supporting documentation without breaking the sequence.
        """
        (tmp_path / "01_video.mp4").write_text("dummy")
        (tmp_path / "README.txt").write_text("dummy")
        (tmp_path / "notes.md").write_text("dummy")
        (tmp_path / ".hidden").write_text("dummy")

        manager = ScenarioManager(scenarios_dir=str(tmp_path))
        result = manager.list_scenarios()

        assert len(result) == 1
        assert result[0].endswith("01_video.mp4")

    def test_list_scenarios_returns_empty_when_directory_missing(self):
        """
        If the scenarios directory does not exist (fresh deployment
        without demo videos), list_scenarios should return an empty
        list rather than raising. This lets main.py fall back to
        normal camera/video behaviour without special-casing the
        missing-directory error.
        """
        manager = ScenarioManager(scenarios_dir="nonexistent/directory")
        result = manager.list_scenarios()

        assert result == []

    def test_list_scenarios_returns_empty_when_directory_is_empty(self, tmp_path):
        """
        If the scenarios directory exists but contains no .mp4
        files, return an empty list. This is the steady state
        before any scenarios have been recorded for the demo.
        """
        manager = ScenarioManager(scenarios_dir=str(tmp_path))
        result = manager.list_scenarios()

        assert result == []


class TestScenarioIndex:
    """Tests covering scenario_index persistence and advancement."""

    def setup_method(self):
        """
        Reset the test database before each test so scenario_index
        state doesn't leak between tests. We use the same TEST_DB
        path that DataLogger tests use, keeping test isolation
        consistent across the codebase.
        """
        os.makedirs("local_database", exist_ok=True)
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state WHERE key='scenario_index'")
        conn.commit()
        conn.close()

    def test_get_scenario_index_defaults_to_zero(self):
        """
        When no scenario_index has been persisted yet (fresh
        deployment), get_scenario_index should return 0 so the
        first run plays the first scenario. The default also
        protects against missing system_state entries — the
        manager never reads None and crashes.
        """
        manager = ScenarioManager(db_path=TEST_DB)
        assert manager.get_scenario_index() == 0

    def test_get_scenario_index_reads_persisted_value(self):
        """
        Once scenario_index has been written to system_state,
        subsequent calls to get_scenario_index should read it
        back. This is how state survives across main.py runs —
        each invocation reads where the previous left off.
        """
        conn = sqlite3.connect(TEST_DB)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_state (key, value) VALUES ('scenario_index', ?)",
            ("3",),
        )
        conn.commit()
        conn.close()

        manager = ScenarioManager(db_path=TEST_DB)
        assert manager.get_scenario_index() == 3

    def test_advance_increments_index(self, tmp_path):
        """
        advance() should bump scenario_index by one and persist
        the new value. Called by main.py during shutdown so the
        next invocation plays the next scenario in the sequence.
        """
        # create 3 scenario videos so wrap-around doesn't trigger
        (tmp_path / "01_a.mp4").write_text("dummy")
        (tmp_path / "02_b.mp4").write_text("dummy")
        (tmp_path / "03_c.mp4").write_text("dummy")

        manager = ScenarioManager(scenarios_dir=str(tmp_path), db_path=TEST_DB)
        assert manager.get_scenario_index() == 0

        manager.advance()
        assert manager.get_scenario_index() == 1

        manager.advance()
        assert manager.get_scenario_index() == 2

    def test_advance_wraps_around_at_end(self, tmp_path):
        """
        When scenario_index reaches the last scenario and advance()
        is called again, it should wrap back to 0. This makes the
        demo loop indefinitely — after the last scenario, the next
        run starts the cycle again at scenario 1.
        """
        (tmp_path / "01_a.mp4").write_text("dummy")
        (tmp_path / "02_b.mp4").write_text("dummy")

        manager = ScenarioManager(scenarios_dir=str(tmp_path), db_path=TEST_DB)

        # advance to the last scenario
        manager.advance()
        assert manager.get_scenario_index() == 1

        # advance again — should wrap to 0
        manager.advance()
        assert manager.get_scenario_index() == 0

    def test_get_current_scenario_returns_path_at_index(self, tmp_path):
        """
        get_current_scenario() should return the path of the
        scenario at the current index. This is the method main.py
        calls to decide which video to play.
        """
        (tmp_path / "01_first.mp4").write_text("dummy")
        (tmp_path / "02_second.mp4").write_text("dummy")
        (tmp_path / "03_third.mp4").write_text("dummy")

        manager = ScenarioManager(scenarios_dir=str(tmp_path), db_path=TEST_DB)
        # at index 0, should return the first scenario
        assert manager.get_current_scenario().endswith("01_first.mp4")

        manager.advance()
        # at index 1, should return the second scenario
        assert manager.get_current_scenario().endswith("02_second.mp4")

    def test_get_current_scenario_returns_none_when_no_scenarios(self):
        """
        If there are no scenario videos on disk, get_current_scenario
        should return None so main.py can fall back to normal camera
        behaviour. This is the backward-compatible escape hatch.
        """
        manager = ScenarioManager(
            scenarios_dir="nonexistent/directory",
            db_path=TEST_DB,
        )
        assert manager.get_current_scenario() is None
