"""Tests for theme resolution and application."""

import sys

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import panther.ui.theme as theme_module
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS, clear_stylesheet_cache
from panther.ui.theme import ThemeManager


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def test_resolve_explicit_light_and_dark(app):
    assert ThemeManager.resolve_theme("light", app) == "light"
    assert ThemeManager.resolve_theme("DARK", app) == "dark"


def test_resolve_invalid_theme_falls_back_to_system(app, monkeypatch):
    monkeypatch.setattr(
        theme_module, "resolve_system_theme", lambda application=None: "dark"
    )
    assert ThemeManager.resolve_theme("sepia", app) == "dark"


def test_apply_light_theme_uses_light_tokens(app):
    resolved = ThemeManager.apply_theme(app, "light")

    assert resolved == "light"
    stylesheet = app.styleSheet()
    assert LIGHT_COLORS.background in stylesheet
    assert LIGHT_COLORS.surface in stylesheet
    # The light sidebar deliberately shares the dark canvas navy, so compare
    # on a token that must differ between appearances.
    assert DARK_COLORS.surface not in stylesheet


def test_apply_dark_theme_uses_dark_tokens(app):
    resolved = ThemeManager.apply_theme(app, "dark")

    assert resolved == "dark"
    stylesheet = app.styleSheet()
    assert DARK_COLORS.background in stylesheet
    assert DARK_COLORS.surface in stylesheet
    assert LIGHT_COLORS.background not in stylesheet


def test_system_theme_uses_style_hint_platform_value(app, monkeypatch):
    monkeypatch.setattr(
        theme_module, "resolve_system_theme", lambda application=None: "dark"
    )

    resolved = ThemeManager.apply_theme(app, "system")

    assert resolved == "dark"
    assert DARK_COLORS.background in app.styleSheet()


def test_system_theme_falls_back_to_palette_lightness(app, monkeypatch):
    monkeypatch.setattr(theme_module, "_style_hint_theme", lambda application: None)
    monkeypatch.setattr(theme_module, "_palette_is_dark", lambda application: True)

    assert theme_module.resolve_system_theme(app) == "dark"

    monkeypatch.setattr(theme_module, "_palette_is_dark", lambda application: False)
    assert theme_module.resolve_system_theme(app) == "light"


def test_apply_theme_uses_cached_stylesheet(app):
    clear_stylesheet_cache()

    ThemeManager.apply_theme(app, "light")
    first = app.styleSheet()
    ThemeManager.apply_theme(app, "light")

    assert app.styleSheet() == first


@pytest.mark.parametrize(
    "theme,palette",
    [("light", LIGHT_COLORS), ("dark", DARK_COLORS)],
)
def test_apply_theme_synchronises_qpalette(app, theme, palette):
    ThemeManager.apply_theme(app, theme)
    applied = app.palette()

    assert applied.color(QPalette.Window).name().lower() == palette.background
    assert applied.color(QPalette.Base).name().lower() == palette.surface
    assert applied.color(QPalette.Text).name().lower() == palette.text_primary
    assert (
        applied.color(QPalette.Disabled, QPalette.Text).name().lower()
        == palette.text_secondary
    )


def test_apply_theme_emits_resolved_theme_once(app):
    received = []
    slot = received.append
    signal = ThemeManager.instance().theme_changed
    signal.connect(slot)
    try:
        ThemeManager.apply_theme(app, "dark")
        ThemeManager.apply_theme(app, "dark")
    finally:
        signal.disconnect(slot)

    assert received == ["dark", "dark"]


def test_theme_switch_updates_an_already_created_widget(app):
    # A top-level widget receives the application palette-change event that a
    # live theme switch sends to already-created screens.
    screen = QWidget()
    label = QLabel("Existing widget", screen)
    label.setObjectName("pageSubtitle")

    ThemeManager.apply_theme(app, "dark")
    app.processEvents()
    dark_window = screen.palette().color(QPalette.Window).name().lower()

    ThemeManager.apply_theme(app, "light")
    app.processEvents()
    light_window = screen.palette().color(QPalette.Window).name().lower()

    screen.deleteLater()

    assert dark_window == DARK_COLORS.background
    assert light_window == LIGHT_COLORS.background


def test_apply_theme_without_application_does_not_crash(monkeypatch):
    # Simulate no QApplication being available; resolving should still be safe.
    monkeypatch.setattr(theme_module, "resolve_system_theme", lambda application=None: "light")

    resolved = ThemeManager.apply_theme(None, "system")

    assert resolved == "light"
