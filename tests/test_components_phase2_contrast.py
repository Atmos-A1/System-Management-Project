"""Rendered-contrast validation for the Phase 2 components.

The ratios are measured from pixels actually drawn by QSS/palette under each
appearance, not from token values.
"""

import sys

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from panther.ui.components import (
    Badge,
    EmptyState,
    ErrorState,
    KeyValueList,
    LoadingState,
    SectionCard,
)
from panther.ui.theme import ThemeManager

BODY_TEXT_RATIO = 4.5


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _relative_luminance(color: QColor) -> float:
    def channel(value):
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(first: QColor, second: QColor) -> float:
    a, b = _relative_luminance(first), _relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _dominant(image) -> QColor:
    counts = {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            key = (color.red(), color.green(), color.blue())
            counts[key] = counts.get(key, 0) + 1
    return QColor(*max(counts, key=counts.get))


def _measure(host, widget) -> float:
    host.adjustSize()
    image = host.grab().toImage()
    rect = QRect(widget.mapTo(host, QPoint(0, 0)), widget.size()).intersected(
        image.rect()
    )
    region = image.copy(rect)
    background = _dominant(region)
    best = 1.0
    for y in range(region.height()):
        for x in range(region.width()):
            best = max(best, _contrast(region.pixelColor(x, y), background))
    return best


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_badge_text_contrast_under_both_themes(app, theme):
    ThemeManager.apply_theme(app, theme)
    badge = Badge("Warning", status="warning")

    assert _measure(badge, badge) >= BODY_TEXT_RATIO


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_state_panels_text_contrast_under_both_themes(app, theme):
    ThemeManager.apply_theme(app, theme)

    empty = EmptyState("No results", "Nothing matched the current filter.")
    error = ErrorState("Scan failed", "The service did not respond.")
    loading = LoadingState("Scanning…")

    assert _measure(empty, empty.title_label) >= BODY_TEXT_RATIO
    assert _measure(empty, empty.description_label) >= BODY_TEXT_RATIO
    assert _measure(error, error.title_label) >= BODY_TEXT_RATIO
    assert _measure(error, error.description_label) >= BODY_TEXT_RATIO
    assert _measure(loading, loading.message_label) >= BODY_TEXT_RATIO


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_key_value_list_text_contrast_under_both_themes(app, theme):
    ThemeManager.apply_theme(app, theme)

    card = SectionCard("Details")
    details = KeyValueList()
    details.add_row("Path", "C:/Users/alice/report.pdf")
    card.add_widget(details)

    assert _measure(card, details.label_for("Path")) >= BODY_TEXT_RATIO
    assert _measure(card, details.value_label("Path")) >= BODY_TEXT_RATIO
