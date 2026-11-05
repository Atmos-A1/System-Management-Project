"""Tests for the QPainter-based Sparkline primitive."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from panther.ui.components import Sparkline
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def _render(sparkline: Sparkline):
    sparkline.resize(160, 40)
    return sparkline.grab().toImage()


def test_sparkline_is_a_non_focusable_display_widget(app):
    sparkline = Sparkline()

    assert sparkline.objectName() == "sparkline"
    assert sparkline.focusPolicy() == Qt.NoFocus
    assert sparkline.accessibleName() != ""
    assert sparkline.values() == []


def test_sparkline_stores_and_appends_values(app):
    sparkline = Sparkline([1.0, 2.0, 3.0])

    sparkline.append(4.0)

    assert sparkline.values() == [1.0, 2.0, 3.0, 4.0]
    assert "4" in sparkline.accessibleDescription()


def test_sparkline_ignores_non_numeric_and_bounds_history(app):
    sparkline = Sparkline(max_points=3)

    sparkline.set_values([1, "bad", None, 3, 4, 5])

    assert sparkline.values() == [3.0, 4.0, 5.0]


def test_sparkline_resolves_its_colour_from_the_theme_token(app):
    sparkline = Sparkline(role="cpu")
    sparkline.set_theme("light")
    assert sparkline.resolved_color().name().lower() == LIGHT_COLORS.chart_cpu

    sparkline.set_theme("dark")
    assert sparkline.resolved_color().name().lower() == DARK_COLORS.chart_cpu


def test_sparkline_accepts_an_explicit_colour_override(app):
    sparkline = Sparkline(role="storage")
    sparkline.set_color(QColor("#123456"))

    assert sparkline.resolved_color().name().lower() == "#123456"


def test_sparkline_renders_without_error_for_empty_and_flat_series(app):
    empty = _render(Sparkline())
    flat = _render(Sparkline([5, 5, 5, 5]))
    normal = _render(Sparkline([1, 3, 2, 6, 4]))

    assert not empty.isNull()
    assert not flat.isNull()
    assert not normal.isNull()


def test_sparkline_rejects_unknown_role(app):
    with pytest.raises(ValueError):
        Sparkline(role="gpu")
