import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from panther.ui.dashboard import DashboardScreen

@pytest.fixture(scope="module")
def app():
    # Ensure a QApplication exists for the test session
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    yield app

def test_dashboard_loads(app):
    # Simply instantiate the widget; refresh will be called automatically
    widget = DashboardScreen()
    assert widget.objectName() == "dashboardScreen"
    # Basic sanity: labels contain non‑empty text after refresh
    widget.refresh()
    assert widget.cpu_label.text() != ""
    assert widget.ram_label.text() != ""
    assert widget.disk_label.text() != ""
    # Battery may be absent, but label should be set
    assert widget.battery_label.text() != ""


def test_cards_actually_render_value_detail_and_progress(app):
    """Regression: an early `return card` once left the value/detail/progress
    widgets orphaned, so cards showed only their title."""
    widget = DashboardScreen()
    widget.show()
    widget.refresh()
    for card in (widget.cpu_card, widget.ram_card, widget.disk_card, widget.battery_card):
        for child in (card.value_label, card.detail_label, card.progress):
            assert child.parent() is card, "child widget was never added to the card"
            assert child.isVisibleTo(widget)
        assert card.value_label.text() not in ("", "0%") or card is widget.battery_card
    widget.close()
