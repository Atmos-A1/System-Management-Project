"""Startup Apps and Activity History tests for the Phase 3 migration."""

import sys
import types

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import panther.ui.history as history_module
import panther.ui.startup as startup_module
from panther.ui.components import (
    DataTable,
    FilterBar,
    KeyValueList,
    PageScaffold,
    SectionCard,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


STARTUP_ENTRIES = [
    {
        "name": "Panther",
        "command": "C:\\Panther\\PantherApp.exe",
        "scope": "HKCU",
        "enabled": True,
    },
    {
        "name": "Cloud Sync",
        "command": "C:\\Cloud\\sync.exe --silent",
        "scope": "HKLM",
        "enabled": True,
    },
]


# ---------------------------------------------------------------------------
# Startup Apps
# ---------------------------------------------------------------------------


def test_startup_uses_scaffold_filter_bar_and_table(app, monkeypatch):
    monkeypatch.setattr(
        startup_module, "get_startup_entries", lambda: list(STARTUP_ENTRIES)
    )

    screen = startup_module.StartupScreen()

    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Startup Apps"
    assert isinstance(screen.filter_bar, FilterBar)
    assert isinstance(screen.table, DataTable)
    assert screen.state_stack.currentWidget() is screen.table
    assert screen.table.model().rowCount() == 2
    assert screen.table.item(0, 0).text() == "Panther"


def test_startup_search_filters_name_command_and_scope(app, monkeypatch):
    monkeypatch.setattr(
        startup_module, "get_startup_entries", lambda: list(STARTUP_ENTRIES)
    )
    screen = startup_module.StartupScreen()

    screen.filter_bar.set_search_text("hklm")
    assert screen.table.model().rowCount() == 1
    assert screen.table.item(0, 0).text() == "Cloud Sync"

    screen.filter_bar.set_search_text("panther")
    assert screen.table.model().rowCount() == 1
    assert screen.table.item(0, 0).text() == "Panther"


def test_startup_shows_loading_while_the_service_runs(app, monkeypatch):
    monkeypatch.setattr(
        startup_module, "get_startup_entries", lambda: list(STARTUP_ENTRIES)
    )
    screen = startup_module.StartupScreen()
    seen = []

    def _load():
        seen.append(screen.state_stack.currentWidget())
        return list(STARTUP_ENTRIES)

    monkeypatch.setattr(startup_module, "get_startup_entries", _load)
    screen.refresh()

    assert seen == [screen.loading_state]
    assert screen.loading_state.is_running is True
    assert screen.state_stack.currentWidget() is screen.table


def test_startup_empty_state_is_explicit(app, monkeypatch):
    monkeypatch.setattr(startup_module, "get_startup_entries", lambda: [])

    screen = startup_module.StartupScreen()

    assert screen.state_stack.currentWidget() is screen.empty_state
    assert screen.empty_state.variant == "empty"
    assert "No startup entries" in screen.empty_state.title_label.text()


def test_startup_unsupported_platform_is_stated_explicitly(app, monkeypatch):
    def _unsupported():
        raise startup_module.UnsupportedPlatformError(
            "Startup app management requires the Windows registry, "
            "which is not available on this platform."
        )

    monkeypatch.setattr(startup_module, "get_startup_entries", _unsupported)

    screen = startup_module.StartupScreen()

    assert screen.state_stack.currentWidget() is screen.unsupported_state
    assert screen.unsupported_state.variant == "unsupported"
    text = (
        screen.unsupported_state.title_label.text()
        + " "
        + screen.unsupported_state.description_label.text()
    ).lower()
    assert "not available" in text
    assert "windows" in text
    assert "error" not in text
    assert screen.filter_bar.isHidden()


def test_startup_error_state_offers_retry(app, monkeypatch):
    calls = {"count": 0}

    def _load():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("registry unavailable")
        return list(STARTUP_ENTRIES)

    monkeypatch.setattr(startup_module, "get_startup_entries", _load)

    screen = startup_module.StartupScreen()

    assert screen.state_stack.currentWidget() is screen.error_state
    assert "registry unavailable" in screen.error_state.description_label.text()

    screen.error_state.retry_button.click()

    assert calls["count"] == 2
    assert screen.state_stack.currentWidget() is screen.table
    assert screen.table.model().rowCount() == 2


# ---------------------------------------------------------------------------
# Activity History
# ---------------------------------------------------------------------------

HISTORY_ROWS = [
    (2, "2026-01-02T03:04:05", "storage", "Moved 3 files"),
    (1, "2026-01-01T00:00:00", "security", "Changed a permission"),
]


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setattr(
        history_module, "get_recent", lambda limit=100: list(HISTORY_ROWS)
    )
    screen = history_module.HistoryScreen()
    screen.timer.stop()
    return screen


def test_history_uses_scaffold_filter_bar_table_and_details(app, history):
    assert isinstance(history.scaffold, PageScaffold)
    assert history.scaffold.header.title_label.text() == "Activity History"
    assert isinstance(history.filter_bar, FilterBar)
    assert isinstance(history.table, DataTable)
    assert history.state_stack.currentWidget() is history.table
    assert history.table.model().rowCount() == 2

    assert isinstance(history.details_card, SectionCard)
    assert isinstance(history.details, KeyValueList)
    assert history.category_filter.accessibleName() != ""


def test_history_formats_timestamps_for_reading(app, history):
    assert history.table.item(0, 1).text() == "2026-01-02 03:04:05"
    assert history.table.item(1, 1).text() == "2026-01-01 00:00:00"


def test_history_selection_populates_the_details_panel(app, history):
    history.table.selectRow(0)

    assert history.details.value("Detail") == "Moved 3 files"
    assert history.details.value("Category") == "storage"
    assert history.details.value("Timestamp") == "2026-01-02 03:04:05"
    assert history.details.value("Record") == "2"
    assert history.details_badge.text() == "storage"


def test_history_search_and_category_filter(app, history):
    history.filter_bar.set_search_text("permission")
    assert history.table.model().rowCount() == 1
    assert history.table.item(0, 3).text() == "Changed a permission"

    history.filter_bar.set_search_text("")
    index = history.category_filter.findText("storage")
    assert index >= 0
    history.category_filter.setCurrentIndex(index)
    assert history.table.model().rowCount() == 1
    assert history.table.item(0, 3).text() == "Moved 3 files"


def test_history_shows_loading_while_the_service_runs(app, monkeypatch):
    monkeypatch.setattr(
        history_module, "get_recent", lambda limit=100: list(HISTORY_ROWS)
    )
    screen = history_module.HistoryScreen()
    screen.timer.stop()
    seen = []

    def _load(limit=100):
        seen.append(screen.state_stack.currentWidget())
        return list(HISTORY_ROWS)

    monkeypatch.setattr(history_module, "get_recent", _load)
    screen.refresh()

    assert seen == [screen.loading_state]
    assert screen.loading_state.is_running is True
    assert screen.state_stack.currentWidget() is screen.table


def test_history_empty_state_is_explicit(app, monkeypatch):
    monkeypatch.setattr(history_module, "get_recent", lambda limit=100: [])
    screen = history_module.HistoryScreen()
    screen.timer.stop()

    assert screen.state_stack.currentWidget() is screen.empty_state
    assert "No activity" in screen.empty_state.title_label.text()


def test_history_error_state_offers_retry(app, monkeypatch):
    calls = {"count": 0}

    def _load(limit=100):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("database unavailable")
        return list(HISTORY_ROWS)

    monkeypatch.setattr(history_module, "get_recent", _load)
    screen = history_module.HistoryScreen()
    screen.timer.stop()

    assert screen.state_stack.currentWidget() is screen.error_state
    assert "database unavailable" in screen.error_state.description_label.text()

    screen.error_state.retry_button.click()

    assert calls["count"] == 2
    assert screen.state_stack.currentWidget() is screen.table
    assert screen.table.model().rowCount() == 2


def test_history_category_filter_is_rebuilt_on_refresh(app, monkeypatch):
    monkeypatch.setattr(
        history_module, "get_recent", lambda limit=100: list(HISTORY_ROWS)
    )
    screen = history_module.HistoryScreen()
    screen.timer.stop()

    assert screen.category_filter.itemText(0) == "All categories"
    assert screen.category_filter.findText("security") >= 0

    screen.category_filter.setCurrentIndex(screen.category_filter.findText("security"))
    monkeypatch.setattr(
        history_module,
        "get_recent",
        lambda limit=100: [(3, "2026-01-03T00:00:00", "startup", "Enabled an entry")],
    )
    screen.refresh()

    assert screen.category_filter.findText("security") == -1
    assert screen.category_filter.findText("startup") >= 0
    assert screen.table.model().rowCount() == 1
