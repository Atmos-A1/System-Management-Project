"""SQLite helper for Panther.

Provides a tiny wrapper around a single SQLite database file with a simple
connection pool and automatic table creation for the MVP.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Tuple

from .config import config

class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or config.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Create tables required for the MVP if they do not exist."""
        with closing(self._connect()) as conn:
            with conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )

    # Simple key/value helper -------------------------------------------------
    def set_setting(self, key: str, value: str) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) "
                    "VALUES (?, ?)",
                    (key, value),
                )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            return row["value"] if row else default

    # Generic query helpers ---------------------------------------------------
    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            cur = conn.execute(sql, tuple(params))
            return list(cur.fetchall())

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(sql, tuple(params))

# Export a singleton for convenient import
db = Database()
