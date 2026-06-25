import json
import logging
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_DESIGNATED_STOPS = [
    "Western Gate",
    "CEDAT",
    "CONAS",
    "Main Library",
    "Africa Hall",
    "Swimming Pool",
    "Mitchel Hall",
    "COCIS",
    "Complex Hall",
    "CEES",
    "Lumumba Hall",
]


def _parse_stop_list(value):
    """Parse a stop list from env/SQLite/json/list input."""
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = None

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]

        return [text]

    return []


def get_designated_stops(db_path=None):
    """
    Return the configured designated stops.

    Priority order:
    1. DESIGNATED_STOPS from the environment (.env / process env)
    2. designated_stops from SQLite system_state
    3. built-in default route list
    """
    env_value = os.getenv("DESIGNATED_STOPS")
    stops = _parse_stop_list(env_value)
    if stops:
        return stops

    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state WHERE key='designated_stops'"
            )
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                stops = _parse_stop_list(row[0])
                if stops:
                    return stops
        except (sqlite3.Error, ValueError, TypeError) as exc:
            logger.warning(f"Unable to read designated stops from SQLite: {exc}")

    return list(DEFAULT_DESIGNATED_STOPS)
