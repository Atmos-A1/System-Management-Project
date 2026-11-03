import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
import panther.ui.dashboard as dashboard_module
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


CARD_ATTRIBUTES = ("cpu_card", "ram_card", "disk_card", "battery_card")


def _layout_widgets(card):
    layout = card.layout()
    widgets = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is not None:
            widgets.append(widget)
    return widgets


@pytest.mark.parametrize("card_attribute", CARD_ATTRIBUTES)
def test_card_layout_attaches_value_detail_and_progress(app, card_attribute):
    screen = DashboardScreen()
    card = getattr(screen, card_attribute)
    layout = card.layout()
    widgets = _layout_widgets(card)

    assert layout.count() == 6
    assert len(widgets) == 4
    assert widgets[0].objectName() == "cardTitle"
    assert widgets[1] is card.value_label
    assert widgets[2] is card.detail_label
    assert widgets[3] is card.progress
    assert layout.indexOf(card.value_label) == 2
    assert layout.indexOf(card.detail_label) == 3
    assert layout.indexOf(card.progress) == 5
    assert card.value_label.parent() is card
    assert card.detail_label.parent() is card
    assert card.progress.parent() is card


def test_card_widgets_are_visible_when_dashboard_is_shown(app, qtbot):
    screen = DashboardScreen()
    qtbot.addWidget(screen)
    screen.show()
    app.processEvents()

    for card_attribute in CARD_ATTRIBUTES:
        card = getattr(screen, card_attribute)
        assert card.value_label.isVisibleTo(screen)
        assert card.detail_label.isVisibleTo(screen)
        assert card.progress.isVisibleTo(screen)


def test_refresh_updates_attached_card_widgets(app, monkeypatch):
    monkeypatch.setattr(
        dashboard_module, "get_cpu_percent", lambda: 12.5
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_ram_usage",
        lambda: {
            "used": 2 * 1024**3,
            "total": 8 * 1024**3,
            "percent": 25.0,
        },
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_disk_usage",
        lambda: {
            "used": 6 * 1024**3,
            "total": 8 * 1024**3,
            "percent": 75.0,
        },
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_battery_info",
        lambda: {"percent": 55, "power_plugged": False},
    )

    screen = DashboardScreen()
    screen.refresh()

    assert screen.cpu_card.value_label.text() == "12.5%"
    assert screen.ram_card.value_label.text() == "25.0%"
    assert screen.disk_card.value_label.text() == "75.0%"
    assert screen.battery_card.value_label.text() == "55%"
    assert screen.cpu_card.progress.value() == 12
    assert screen.ram_card.progress.value() == 25
    assert screen.disk_card.progress.value() == 75
    assert screen.battery_card.progress.value() == 55

    for card_attribute in CARD_ATTRIBUTES:
        card = getattr(screen, card_attribute)
        assert card.layout().indexOf(card.value_label) != -1
        assert card.layout().indexOf(card.detail_label) != -1
        assert card.layout().indexOf(card.progress) != -1
