"""Tests for the KeyValueList details primitive."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from panther.ui.components import KeyValueList


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_key_value_list_adds_labelled_rows(app):
    details = KeyValueList()
    details.add_row("Path", "C:/Users/alice/report.pdf")
    details.add_row("Size", "4.2 MB")

    assert details.objectName() == "keyValueList"
    assert details.keys() == ["Path", "Size"]
    assert details.value("Path") == "C:/Users/alice/report.pdf"
    assert details.value("Size") == "4.2 MB"
    assert details.accessibleName() != ""


def test_key_value_list_values_are_machine_readable_labels(app):
    details = KeyValueList()
    details.add_row("Status", "Read-only")

    label = details.label_for("Status")
    value = details.value_label("Status")

    assert label.objectName() == "keyValueLabel"
    assert value.objectName() == "keyValueValue"
    assert value.textInteractionFlags() & Qt.TextSelectableByMouse


def test_key_value_list_updates_existing_values(app):
    details = KeyValueList()
    details.add_row("Status", "Scanning")

    details.set_value("Status", "Complete")

    assert details.value("Status") == "Complete"


def test_key_value_list_clear_removes_all_rows(app):
    details = KeyValueList()
    details.add_row("A", "1")
    details.add_row("B", "2")

    details.clear()

    assert details.keys() == []
    assert details.value("A") is None


def test_key_value_list_ignores_value_of_unknown_key(app):
    details = KeyValueList()
    details.add_row("A", "1")

    details.set_value("Missing", "x")

    assert details.keys() == ["A"]


def test_key_value_list_rejects_duplicate_keys(app):
    details = KeyValueList()
    details.add_row("A", "1")

    with pytest.raises(ValueError):
        details.add_row("A", "2")
