# pytest configuration

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from panther.config import config
from panther.services.cleanup_policy import is_protected_path


@pytest.fixture(autouse=True)
def isolated_history_db(tmp_path_factory, monkeypatch):
    """Redirect every test database reference to a fresh temporary database.

    ``history`` imports the ``panther.db`` singleton by value, so patching only
    the module attribute is insufficient. The environment is also redirected so
    subprocess-based tests inherit the temporary database path.

    The database lives in its own temporary directory, never inside a test's
    ``tmp_path`` tree, so directory-scanning tests see only their own files.
    """
    import panther.db as db_module
    from panther.services import history

    normal_path = db_module.db.path
    db_path = tmp_path_factory.mktemp("test_history_db") / "history.db"
    test_db = db_module.Database(db_path)

    monkeypatch.setattr(db_module, "db", test_db)
    monkeypatch.setattr(history, "db", test_db)
    monkeypatch.setenv("PANTHER_DB_PATH", str(db_path))

    history._ensure_schema()
    yield {"db": test_db, "normal_path": normal_path}


@pytest.fixture
def cleanup_tmp_path(tmp_path):
    """Provide a disposable root that cleanup policy does not protect.

    On Windows, pytest's default temporary directory is under the user's
    AppData tree, which cleanup policy intentionally protects. Cleanup tests
    need a disposable root outside those protected locations.
    """
    if os.name != "nt":
        yield tmp_path
        return

    base = Path(
        os.environ.get("RUNNER_TEMP")
        or (Path.home() / "PantherCleanupTests")
    )
    base.mkdir(parents=True, exist_ok=True)
    path = Path(
        tempfile.mkdtemp(prefix="panther-cleanup-", dir=str(base))
    )
    if is_protected_path(str(path), windows=True):
        shutil.rmtree(path, ignore_errors=True)
        pytest.fail(
            "cleanup_tmp_path resolved inside a protected location"
        )
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def temp_db(tmp_path_factory):
    """Create a temporary SQLite DB for the duration of the test session."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    # Ensure the config points to the temporary DB for the tests
    original = config.db_path
    config.db_path = db_path
    yield db_path
    # Restore original path after tests
    config.db_path = original
