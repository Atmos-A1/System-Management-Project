"""Tests for dialog and scan-progress components."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from panther.ui.components.confirm_dialog import ConfirmDialog
from panther.ui.components.scan_progress import ScanProgress


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_confirm_dialog_exposes_message_and_buttons(app):
    dialog = ConfirmDialog(
        "Delete files",
        "This action moves the selected files to the recycle bin.",
        confirm_text="Move to Recycle Bin",
        destructive=True,
    )

    assert dialog.windowTitle() == "Delete files"
    assert dialog.message_label.text().startswith("This action moves")
    assert dialog.confirm_button.text() == "Move to Recycle Bin"
    assert dialog.cancel_button.text() == "Cancel"
    assert dialog.confirm_button.property("variant") == "destructive"
    assert dialog.cancel_button.isDefault() is True
    assert dialog.confirmed is False


def test_confirm_dialog_tracks_accept_and_reject(app):
    dialog = ConfirmDialog("Confirm", "Proceed?")

    dialog.accept()
    assert dialog.confirmed is True

    dialog = ConfirmDialog("Confirm", "Proceed?")
    dialog.reject()
    assert dialog.confirmed is False


def test_scan_progress_start_set_progress_and_finish(app):
    scan = ScanProgress()

    scan.start("Scanning Downloads…", maximum=0)
    assert scan.is_running is True
    assert scan.status_label.text() == "Scanning Downloads…"
    assert scan.progress.minimum() == 0
    assert scan.progress.maximum() == 0
    assert scan.cancel_button.isEnabled() is True

    scan.set_progress(40, maximum=100)
    assert scan.progress.maximum() == 100
    assert scan.progress.value() == 40

    scan.finish("Scan complete")
    assert scan.is_running is False
    assert scan.progress.value() == 100
    assert scan.status_label.text() == "Scan complete"
    assert scan.cancel_button.isEnabled() is False


def test_scan_progress_cancel_signal_and_state(app, qtbot):
    scan = ScanProgress()
    scan.start("Scanning…", maximum=100)
    received = []
    scan.cancel_requested.connect(lambda: received.append(True))

    qtbot.mouseClick(scan.cancel_button, Qt.LeftButton)

    assert received == [True]
    assert scan.status_label.text() == "Cancelling…"
    assert scan.cancel_button.isEnabled() is False
    assert scan.is_running is False


def test_scan_progress_reset_clears_state(app):
    scan = ScanProgress()
    scan.start("Scanning…", maximum=50)
    scan.set_progress(20)

    scan.reset()

    assert scan.progress.maximum() == 0
    assert scan.progress.value() == 0
    assert scan.status_label.text() == ""
    assert scan.cancel_button.isEnabled() is True
    assert scan.is_running is False
