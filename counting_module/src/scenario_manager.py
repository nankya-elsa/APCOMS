"""
Scenario Manager Component for APCOMS

Manages the sequence of scripted demo videos that main.py plays.
Each scenario is a short video showing a specific boarding event
(one passenger entering, multiple alighting, etc) — together they
tell a complete story for panel presentations.

The manager handles three responsibilities:
  - Finding scenario video files on disk
  - Tracking which scenario plays next via SQLite system_state
  - Advancing the sequence on each main.py run

This decouples main.py from scenario bookkeeping. main.py simply
asks "what video should I play?" and gets a path back. After the
run completes, main.py calls advance() to bump the counter so the
next invocation plays the next video.

When the scenarios directory is missing or empty, the manager
returns None, letting main.py fall back to its normal CAMERA_SOURCE
behaviour — fully backward-compatible with the existing pipeline.
"""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


class ScenarioManager:
    """
    Sequences scenario videos for main.py demo runs.

    Attributes:
        scenarios_dir: Path to the folder containing scenario video
                       files. Defaults to 'data/scenarios'.
        db_path:       Path to the SQLite database used to persist
                       scenario_index across runs. Defaults to the
                       production database; tests override this.
    """

    def __init__(self, scenarios_dir=None, db_path=None):
        """
        Initialize the ScenarioManager.

        Args:
            scenarios_dir: Optional override for the scenarios folder.
                           Defaults to 'data/scenarios'.
            db_path:       Optional override for the SQLite database
                           path. Defaults to 'local_database/apcoms.db'.
        """
        self.scenarios_dir = scenarios_dir or "data/scenarios"
        self.db_path = db_path or "local_database/apcoms.db"

    def list_scenarios(self):
        """
        Discover all scenario video files in the scenarios directory.

        Returns the full paths of all .mp4 files in the directory,
        sorted alphabetically so numeric prefixes (01_*, 02_*, ...)
        determine the play order. Non-video files are quietly
        ignored so the directory can hold supporting documentation.

        Returns an empty list if the directory does not exist or
        contains no video files. This lets main.py fall back to
        normal camera behaviour without special-casing missing
        scenarios — a perfectly valid deployment state.

        Returns:
            A sorted list of absolute (or relative, matching the
            input) paths to .mp4 files. Empty if none found.
        """
        if not os.path.isdir(self.scenarios_dir):
            return []

        videos = []
        for filename in os.listdir(self.scenarios_dir):
            if filename.lower().endswith(".mp4"):
                videos.append(os.path.join(self.scenarios_dir, filename))

        videos.sort()
        return videos

    def get_scenario_index(self):
        """
        Read the current scenario_index from SQLite system_state.

        Returns 0 when no value has been persisted yet, which
        happens on first deployment or after the database has
        been reset. The default ensures main.py always has a
        valid starting point and never reads a None index.

        Returns:
            The current scenario_index as an integer.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state WHERE key='scenario_index'"
            )
            row = cursor.fetchone()
            conn.close()
            if row is None:
                return 0
            return int(row[0])
        except (sqlite3.Error, ValueError, TypeError) as e:
            logger.error(f"Error reading scenario_index: {e}")
            return 0

    def advance(self):
        """
        Increment scenario_index by one, wrapping back to 0 when
        the sequence has played through all available scenarios.

        Called by main.py during shutdown so that the NEXT
        invocation plays the next scenario in the sequence.
        Wrap-around makes the demo loop indefinitely — after the
        last scenario plays, the cycle restarts from scenario 1.

        If there are no scenarios on disk, the index is reset to
        0 (a no-op for a fresh deployment).
        """
        scenarios = self.list_scenarios()
        if not scenarios:
            self._save_index(0)
            return

        current = self.get_scenario_index()
        next_index = (current + 1) % len(scenarios)
        self._save_index(next_index)
        logger.info(
            f"Scenario index advanced from {current} to {next_index}"
        )

    def get_current_scenario(self):
        """
        Return the path of the scenario at the current index.

        This is the method main.py calls to decide which video
        to play. Returns None when no scenarios are available
        on disk so main.py can fall back to the normal
        CAMERA_SOURCE behaviour without special-casing the
        missing-directory error.

        Returns:
            The path of the current scenario video, or None if
            no scenarios are available.
        """
        scenarios = self.list_scenarios()
        if not scenarios:
            return None

        index = self.get_scenario_index()
        # guard against an out-of-bounds index if scenarios were
        # removed since the index was last persisted
        if index >= len(scenarios):
            index = 0
            self._save_index(0)
        return scenarios[index]

    def _save_index(self, value):
        """
        Persist scenario_index to SQLite system_state.

        Internal helper used by advance() and get_current_scenario().
        Uses INSERT OR REPLACE so the row is created on first write
        and updated on subsequent writes — no need to differentiate
        between "first save" and "update".

        Args:
            value: The integer to persist as scenario_index.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("scenario_index", str(value)),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error saving scenario_index: {e}")
