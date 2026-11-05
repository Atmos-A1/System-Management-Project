"""Applications screen tests for the Phase 3 design-system migration."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import panther.ui.applications as applications_module
from panther.ui.applications import AppTableModel, ApplicationsScreen
from panther.ui.components import DataTable, FilterBar, PageScaffold


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


APPS = [
    {
        "name": "Panther",
        "publisher": "Panther Labs",
        "version": "1.0",
        "install_location": "C:/Program Files/Panther",
    },
    {
        "name": "Report Viewer",
        "publisher": "Acme",
        "version": "2.4",
        "install_location": "C:/Program Files/Acme",
    },
]


def _supported(monkeypatch, apps=None):
    monkeypatch.setattr(applications_module, "winreg", object())
    monkeypatch.setattr(
        applications_module,
        "get_installed_apps",
        lambda: list(APPS if apps is None else apps),
    )


def test_applications_uses_scaffold_filter_bar_and_data_table(app):
    screen = ApplicationsScreen()

    assert screen.objectName() == "applicationsScreen"
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Installed Applications"
    assert isinstance(screen.filter_bar, FilterBar)
    assert isinstance(screen.table, DataTable)


def test_applications_unsupported_platform_is_stated_explicitly(
    app, monkeypatch
):
    monkeypatch.setattr(applications_module, "winreg", None)
    screen = ApplicationsScreen()

    assert screen.state_stack.currentWidget() is screen.unsupported_state
    assert screen.unsupported_state.variant == "unsupported"
    text = (
        screen.unsupported_state.title_label.text()
        + " "
        + screen.unsupported_state.description_label.text()
    ).lower()
    assert "windows" in text
    assert "not available" in text
    assert screen.filter_bar.isHidden()


def test_applications_populated_state_uses_the_existing_table_model(
    app, monkeypatch
):
    _supported(monkeypatch)
    screen = ApplicationsScreen()

    assert isinstance(screen.table.model().sourceModel(), AppTableModel)
    assert screen.state_stack.currentWidget() is screen.table
    assert screen.table.model().rowCount() == 2
    assert screen.table.item(0, 0).text() == "Panther"
    assert screen.table.item(0, 1).text() == "Panther Labs"
    assert screen.filter_bar.isVisible() or not screen.isVisible()


def test_applications_search_filters_all_visible_columns(app, monkeypatch):
    _supported(monkeypatch)
    screen = ApplicationsScreen()

    screen.filter_bar.set_search_text("acme")

    assert screen.table.model().rowCount() == 1
    assert screen.table.item(0, 0).text() == "Report Viewer"

    screen.filter_bar.set_search_text("")

    assert screen.table.model().rowCount() == 2


def test_applications_shows_loading_while_the_service_runs(app, monkeypatch):
    _supported(monkeypatch)
    screen = ApplicationsScreen()
    seen = []

    def _load():
        seen.append(screen.state_stack.currentWidget())
        return list(APPS)

    monkeypatch.setattr(applications_module, "get_installed_apps", _load)
    screen.refresh()

    assert seen == [screen.loading_state]
    assert screen.loading_state.is_running is True
    assert screen.state_stack.currentWidget() is screen.table


def test_applications_empty_state_is_explicit(app, monkeypatch):
    _supported(monkeypatch, apps=[])
    screen = ApplicationsScreen()

    assert screen.state_stack.currentWidget() is screen.empty_state
    assert screen.empty_state.variant == "empty"
    assert "No applications" in screen.empty_state.title_label.text()
    assert screen.table.model().rowCount() == 0


def test_applications_error_state_offers_retry(app, monkeypatch):
    calls = {"count": 0}

    def _load():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("registry read failed")
        return list(APPS)

    monkeypatch.setattr(applications_module, "winreg", object())
    monkeypatch.setattr(applications_module, "get_installed_apps", _load)

    screen = ApplicationsScreen()

    assert screen.state_stack.currentWidget() is screen.error_state
    assert "registry read failed" in screen.error_state.description_label.text()
    assert screen.error_state.retry_button.focusPolicy() != Qt.NoFocus

    screen.error_state.retry_button.click()

    assert calls["count"] == 2
    assert screen.state_stack.currentWidget() is screen.table
    assert screen.table.model().rowCount() == 2


def test_applications_table_is_keyboard_navigable(app, monkeypatch):
    _supported(monkeypatch)
    screen = ApplicationsScreen()

    assert screen.table.focusPolicy() != Qt.NoFocus
    assert screen.table.accessibleName() != ""
    assert screen.filter_bar.search_edit.accessibleName() != ""
