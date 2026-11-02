# pytest configuration

import pytest
from panther.config import config


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
