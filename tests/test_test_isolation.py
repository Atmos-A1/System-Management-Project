"""Tests proving scan-history writes are isolated from the real database."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from panther import db as db_module
from panther.services import history, storage_history
from panther.ui.storage import StorageScreen


def _app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _history_state(path: Path):
    """Read-only snapshot of the normal DB history row count."""
    path = Path(path)
    if not path.exists():
        return {"exists": False, "count": 0}
    uri = f"file:{path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return {"exists": True, "count": None}
    try:
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM history"
            ).fetchone()
            count = int(row[0]) if row else 0
        except sqlite3.OperationalError:
            count = 0
    finally:
        connection.close()
    return {"exists": True, "count": count}


def _scan_rows(database):
    return database.fetchall(
        "SELECT id, detail FROM history "
        "WHERE category = 'storage_scan' ORDER BY id"
    )


def _scan_statuses(database):
    return [
        json.loads(row["detail"]).get("status")
        for row in _scan_rows(database)
    ]


def _completion_payload():
    return {
        "generation": 1,
        "kind": "largest",
        "root": "/isolated/root",
        "largest": [],
        "duplicates": [],
        "errors": [],
        "partial": False,
        "files_scanned": 2,
        "directories_scanned": 1,
        "bytes_scanned": 20,
        "elapsed_seconds": 1.0,
    }


def test_scan_completion_writes_only_to_the_isolated_database(
    qtbot, isolated_history_db
):
    _app()
    temp_db = isolated_history_db["db"]
    normal_path = isolated_history_db["normal_path"]
    before = _history_state(normal_path)

    screen = StorageScreen()
    qtbot.addWidget(screen)
    screen._on_scan_finished(_completion_payload())

    assert _scan_statuses(temp_db) == ["completed"]
    assert _history_state(normal_path) == before

    screen.scan_controller.shutdown()
    screen.explorer_panel.shutdown()
    screen.insights_panel.shutdown()


def test_scan_cancellation_and_failure_use_the_isolated_database(
    qtbot, isolated_history_db
):
    _app()
    temp_db = isolated_history_db["db"]
    normal_path = isolated_history_db["normal_path"]
    before = _history_state(normal_path)

    screen = StorageScreen()
    qtbot.addWidget(screen)
    screen._on_scan_cancelled({"generation": 1, "kind": "largest"})
    screen._on_scan_failed(
        {"kind": "duplicates", "error": "permission denied"}
    )

    assert _scan_statuses(temp_db) == ["cancelled", "failed"]
    assert _history_state(normal_path) == before

    screen.scan_controller.shutdown()
    screen.explorer_panel.shutdown()
    screen.insights_panel.shutdown()


def test_database_references_are_redirected(isolated_history_db):
    temp_db = isolated_history_db["db"]
    normal_path = isolated_history_db["normal_path"]

    assert db_module.db is temp_db
    assert history.db is temp_db
    assert storage_history.history.db is temp_db
    assert temp_db.path != normal_path


def test_temporary_database_is_fresh(isolated_history_db):
    assert _scan_rows(isolated_history_db["db"]) == []
    assert history.get_recent(10) == []


def test_temporary_database_is_fresh_again(isolated_history_db):
    assert _scan_rows(isolated_history_db["db"]) == []
    assert history.get_recent(10) == []


def test_mocked_history_recording_still_works(
    qtbot, isolated_history_db, monkeypatch
):
    _app()
    calls = []
    monkeypatch.setattr(
        storage_history,
        "record_scan",
        lambda payload, status: calls.append((payload, status)) or True,
    )
    temp_db = isolated_history_db["db"]

    screen = StorageScreen()
    qtbot.addWidget(screen)
    screen._on_scan_finished(_completion_payload())

    assert [status for _, status in calls] == ["completed"]
    assert _scan_rows(temp_db) == []

    screen.scan_controller.shutdown()
    screen.explorer_panel.shutdown()
    screen.insights_panel.shutdown()


def test_subprocess_scan_recording_uses_the_isolated_database(
    tmp_path, isolated_history_db
):
    temp_db = isolated_history_db["db"]
    normal_path = isolated_history_db["normal_path"]
    before = _history_state(normal_path)
    script = """
import json
from panther.services import storage_history

assert storage_history.record_scan(
    {"kind": "largest", "root": "/child/root"}, "completed"
)
print(json.dumps({"status": "ok"}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(
        Path(__file__).resolve().parents[1] / "src"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip())["status"] == "ok"
    assert _scan_statuses(temp_db) == ["completed"]
    assert _history_state(normal_path) == before
