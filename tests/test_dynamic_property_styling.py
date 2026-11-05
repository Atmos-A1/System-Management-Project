"""Phase 1: dynamic-property variants must repolish without rebuild."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from panther.ui.components import StatusBanner
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.theme import ThemeManager


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _left_border_color(widget) -> str:
    widget.show()
    QApplication.processEvents()
    image = widget.grab().toImage()
    return image.pixelColor(0, image.height() // 2).name().lower()


def test_status_banner_repolishes_to_the_new_state_colour(app):
    ThemeManager.apply_theme(app, "light")

    banner = StatusBanner("Healthy", "success")
    banner.resize(260, 44)
    assert _left_border_color(banner) == LIGHT_COLORS.success.lower()

    # A dynamic-property change must repolish the existing widget.
    banner.set_state("warning", "Watch this")
    assert banner.property("status") == "warning"
    assert _left_border_color(banner) == LIGHT_COLORS.warning.lower()


def test_status_banner_repolishes_under_the_dark_palette(app):
    ThemeManager.apply_theme(app, "dark")

    banner = StatusBanner("Failed", "error")
    banner.resize(260, 44)
    assert _left_border_color(banner) == DARK_COLORS.critical.lower()
