"""Tests for the Badge / StatusPill primitive."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from panther.ui.components import Badge, StatusPill


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_badge_renders_text_and_defaults_to_neutral(app):
    badge = Badge("Cached")

    assert badge.objectName() == "badge"
    assert badge.text() == "Cached"
    assert badge.status == "neutral"
    assert badge.property("status") == "neutral"


@pytest.mark.parametrize(
    "status", ["neutral", "info", "success", "warning", "critical"]
)
def test_badge_accepts_every_supported_status(app, status):
    badge = Badge("State", status=status)

    assert badge.status == status
    assert badge.property("status") == status


def test_badge_rejects_unknown_status(app):
    with pytest.raises(ValueError):
        Badge("State", status="sepia")


def test_badge_accessible_name_conveys_text_and_status(app):
    badge = Badge("2 duplicates", status="warning")

    assert badge.accessibleName() == "2 duplicates, warning"


def test_badge_is_not_keyboard_focusable(app):
    # Badges are status indicators, not controls; colour is never the only
    # signal because the status is part of the accessible name.
    badge = Badge("OK", status="success")

    assert badge.focusPolicy() == Qt.NoFocus


def test_status_pill_is_a_badge_alias(app):
    assert StatusPill is Badge


def test_badge_can_update_text_and_status(app):
    badge = Badge("Old", status="info")

    badge.set_text("New")
    badge.set_status("critical")

    assert badge.text() == "New"
    assert badge.status == "critical"
    assert badge.accessibleName() == "New, critical"
