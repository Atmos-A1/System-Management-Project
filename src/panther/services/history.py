"""History service – simple SQLite logger.

Provides functions to record an arbitrary event (timestamp, category, detail) and to retrieve recent events.
All interactions go through the shared `Database` singleton defined in `panther.db`.
"""

import datetime
from typing import List, Tuple, Any

from ..db import db

TABLE_NAME = "history"

def _ensure_schema() -> None:
    """Create the history table if it does not exist."""
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            category TEXT NOT NULL,
            detail TEXT NOT NULL
        );
        """
    )

# Ensure table exists at import time
_ensure_schema()

def record_event(category: str, detail: str) -> None:
    """Insert a new event into the history table.

    *category* is a short tag like ``"action"`` or ``"metric"``.
    *detail* is a JSON‑serialisable string describing the event.
    """
    # Same stored format as before (naive UTC), without the deprecated utcnow().
    timestamp = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    db.execute(
        f"INSERT INTO {TABLE_NAME} (ts, category, detail) VALUES (?, ?, ?)",
        (timestamp, category, detail),
    )

def clear_history() -> int:
    """Delete every history row and return how many were removed."""
    count = db.fetchall(f"SELECT COUNT(*) AS n FROM {TABLE_NAME}")[0]["n"]
    db.execute(f"DELETE FROM {TABLE_NAME}")
    return count

def get_recent(limit: int = 100) -> List[Tuple[int, str, str, str]]:
    """Return the most recent *limit* rows ordered by timestamp descending."""
    rows = db.fetchall(
        f"SELECT id, ts, category, detail FROM {TABLE_NAME} ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return [(r["id"], r["ts"], r["category"], r["detail"]) for r in rows]
