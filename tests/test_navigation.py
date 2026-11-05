"""Tests for navigation metadata, icons and index lookup."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QWidget

import panther.ui.recommendations as recommendations_module
from panther.ui.navigation import NAV_ITEMS, nav_icon, nav_index


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_every_navigation_item_declares_an_icon(app):
    assert NAV_ITEMS
    assert all(icon_key for _name, icon_key in NAV_ITEMS)


def test_nav_icon_resolves_to_a_non_null_pixmap(app):
    for _name, icon_key in NAV_ITEMS:
        icon = nav_icon(icon_key)
        assert not icon.isNull(), icon_key


def test_nav_index_matches_navigation_order(app):
    assert nav_index("Dashboard") == 0
    assert nav_index("Processes") == 1
    assert nav_index("Storage") == 3
    assert nav_index("Settings") == len(NAV_ITEMS) - 1


def test_nav_index_rejects_unknown_screen(app):
    with pytest.raises(KeyError):
        nav_index("Not a screen")


class _RecordingSidebar:
    def __init__(self):
        self.row = None

    def setCurrentRow(self, row):
        self.row = row


class _RecordingStack:
    def __init__(self):
        self.index = None

    def setCurrentIndex(self, index):
        self.index = index


class _FakeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.sidebar = _RecordingSidebar()
        self.stack = _RecordingStack()


@pytest.mark.parametrize(
    "recommendation,expected_screen",
    [
        ({"category": "process", "issue": "High CPU"}, "Processes"),
        ({"category": "storage", "issue": "Disk pressure"}, "Storage"),
        ({"category": "power", "issue": "Battery drain"}, "Battery"),
        ({"category": "startup", "issue": "Startup overhead"}, "Startup Apps"),
        ({"category": "general", "issue": "Unknown"}, None),
    ],
)
def test_recommendation_navigation_uses_navigation_labels(
    app, qtbot, monkeypatch, recommendation, expected_screen
):
    monkeypatch.setattr(
        recommendations_module, "get_recommendations", lambda metrics: []
    )
    monkeypatch.setattr(
        recommendations_module.RecommendationsScreen,
        "_gather_metrics",
        lambda self: {
            "cpu_percent": 0,
            "ram_percent": 0,
            "disk_percent": 0,
            "battery_percent": None,
        },
    )

    screen = recommendations_module.RecommendationsScreen()
    screen.timer.stop()
    window = _FakeWindow()
    qtbot.addWidget(window)
    screen.setParent(window)

    screen.navigate_to_fix(recommendation)

    if expected_screen is None:
        assert window.sidebar.row is None
        assert window.stack.index is None
    else:
        expected_index = nav_index(expected_screen)
        assert window.sidebar.row == expected_index
        assert window.stack.index == expected_index
