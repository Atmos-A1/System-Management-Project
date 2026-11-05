"""Phase 1 acceptance tests for the Settings design-system pilot."""

import inspect
import re
import sys

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

import panther.ui.settings as settings_module
from panther.config import config
from panther.ui.components import PageScaffold, SectionCard
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.settings import SettingsScreen

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def restore_theme_config(app):
    original_theme = config.theme
    yield
    config.theme = original_theme
    app.setStyleSheet("")


def test_settings_uses_page_scaffold(app):
    screen = SettingsScreen()
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Settings"


def test_settings_groups_use_section_cards(app):
    screen = SettingsScreen()
    cards = [c for c in screen.findChildren(SectionCard)]
    titles = {card.title_label.text() for card in cards}

    assert {
        "Monitoring",
        "Appearance",
        "Privacy & Security",
        "Data Management",
        "About",
    }.issubset(titles)


def test_settings_source_has_no_screen_level_theme_colors():
    source = inspect.getsource(settings_module)

    assert "setStyleSheet" not in source
    assert not HEX_COLOR.search(source)


def test_settings_theme_switch_updates_existing_widgets(app):
    screen = SettingsScreen()

    screen.theme_combo.setCurrentText("Dark")
    app.processEvents()
    assert screen.palette().color(QPalette.Window).name().lower() == (
        DARK_COLORS.background
    )

    screen.theme_combo.setCurrentText("Light")
    app.processEvents()
    assert screen.palette().color(QPalette.Window).name().lower() == (
        LIGHT_COLORS.background
    )
    assert config.theme == "light"


def test_settings_reports_resolved_system_theme(app, monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "ThemeManager",
        type(
            "StubThemeManager",
            (),
            {
                "apply_theme": staticmethod(lambda application, name: "dark"),
            },
        ),
    )
    screen = SettingsScreen()
    screen.theme_combo.setCurrentText("System")

    assert config.theme == "system"
    assert "dark" in screen.theme_info.text().lower()


def test_settings_controls_keep_accessible_names(app):
    screen = SettingsScreen()

    assert screen.refresh_spin.accessibleName() != ""
    assert screen.theme_combo.accessibleName() != ""
    assert screen.open_data_btn.accessibleName() != ""
    assert screen.clear_history_btn.accessibleName() != ""
