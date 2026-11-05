"""Tests for core reusable components: headers, scaffolds, banners, buttons."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from panther.ui.components.buttons import (
    DestructiveButton,
    PrimaryButton,
    SecondaryButton,
)
from panther.ui.components.page_header import PageHeader
from panther.ui.components.page_scaffold import PageScaffold
from panther.ui.components.status_banner import StatusBanner


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_page_header_exposes_title_and_subtitle(app):
    header = PageHeader("Storage", "Review disk usage and cleanup candidates")

    assert header.objectName() == "pageHeader"
    assert header.title_label.text() == "Storage"
    assert header.title_label.objectName() == "pageTitle"
    assert header.subtitle_label.text() == "Review disk usage and cleanup candidates"
    assert header.subtitle_label.objectName() == "pageSubtitle"
    assert not header.subtitle_label.isHidden()


def test_page_header_hides_missing_subtitle(app):
    header = PageHeader("Settings")

    assert header.title_label.text() == "Settings"
    assert header.subtitle_label.isHidden()


def test_page_header_can_update_text(app):
    header = PageHeader("Old", "Old subtitle")
    header.set_title("New")
    header.set_subtitle("New subtitle")

    assert header.title_label.text() == "New"
    assert header.subtitle_label.text() == "New subtitle"
    assert not header.subtitle_label.isHidden()

    header.set_subtitle("")
    assert header.subtitle_label.isHidden()


def test_page_scaffold_provides_header_and_content_area(app):
    scaffold = PageScaffold("Processes", "Review running applications")
    child = QWidget()

    scaffold.add_widget(child, 1)

    assert scaffold.objectName() == "pageScaffold"
    assert scaffold.header.title_label.text() == "Processes"
    assert scaffold.content_layout.indexOf(child) != -1
    assert scaffold.layout().indexOf(scaffold.header) == 0
    assert scaffold.layout().indexOf(scaffold.content) == 1


def test_page_scaffold_can_update_header(app):
    scaffold = PageScaffold("Old", "Old subtitle")

    scaffold.set_title("New")
    scaffold.set_subtitle("New subtitle")

    assert scaffold.header.title_label.text() == "New"
    assert scaffold.header.subtitle_label.text() == "New subtitle"


def test_status_banner_starts_hidden_without_message(app):
    banner = StatusBanner()

    assert banner.objectName() == "statusBanner"
    assert banner.state == "info"
    assert banner.isHidden()


@pytest.mark.parametrize(
    "state,label",
    [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("loading", "Loading"),
    ],
)
def test_status_banner_sets_text_and_state(app, state, label):
    banner = StatusBanner()

    banner.set_state(state, f"Message for {state}")

    assert banner.state == state
    assert banner.property("status") == state
    assert banner.state_label.text() == label
    assert banner.message_label.text() == f"Message for {state}"
    assert not banner.isHidden()


def test_status_banner_rejects_invalid_state(app):
    banner = StatusBanner()

    with pytest.raises(ValueError):
        banner.set_state("sepia", "invalid")


def test_status_banner_clear_hides_and_resets_message(app):
    banner = StatusBanner("Something happened", "warning")

    banner.clear()

    assert banner.message_label.text() == ""
    assert banner.isHidden()


def test_button_variants_expose_machine_readable_properties(app):
    primary = PrimaryButton("Run")
    secondary = SecondaryButton("Cancel")
    destructive = DestructiveButton("Delete")

    assert primary.property("variant") == "primary"
    assert secondary.property("variant") == "secondary"
    assert secondary.property("secondary") is True
    assert destructive.property("variant") == "destructive"
    assert destructive.property("destructive") is True
    assert primary.text() == "Run"
    assert secondary.text() == "Cancel"
    assert destructive.text() == "Delete"


def test_button_click_is_preserved(app, qtbot):
    button = PrimaryButton("Run")
    clicks = []
    button.clicked.connect(lambda: clicks.append(True))

    button.click()

    assert clicks == [True]
