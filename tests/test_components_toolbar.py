"""Tests for the Toolbar and FilterBar primitives."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from panther.ui.components import FilterBar, Toolbar


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_toolbar_places_widgets_left_and_right(app):
    toolbar = Toolbar()
    left = QPushButton("Refresh")
    right = QPushButton("Export")

    toolbar.add_widget(left)
    toolbar.add_stretch()
    toolbar.add_widget(right, align="right")

    assert toolbar.objectName() == "toolbar"
    assert toolbar.layout().indexOf(left) != -1
    assert toolbar.layout().indexOf(right) != -1
    assert toolbar.layout().indexOf(left) < toolbar.layout().indexOf(right)
    assert toolbar.accessibleName() != ""


def test_toolbar_separator_is_not_focusable(app):
    toolbar = Toolbar()
    separator = toolbar.add_separator()

    assert separator.focusPolicy() == Qt.NoFocus


def test_filter_bar_exposes_a_labelled_search_field(app):
    bar = FilterBar(search_placeholder="Search activity…")

    assert bar.objectName() == "filterBar"
    assert bar.search_edit.placeholderText() == "Search activity…"
    assert bar.search_edit.accessibleName() == "Search"
    assert bar.search_edit.isClearButtonEnabled() is True
    assert bar.search_edit.focusPolicy() != Qt.NoFocus


def test_filter_bar_emits_search_changes(app, qtbot):
    bar = FilterBar()
    received = []
    bar.search_changed.connect(received.append)

    bar.search_edit.setText("alpha")

    assert received[-1] == "alpha"
    assert bar.search_text() == "alpha"


def test_filter_bar_accepts_additional_filter_widgets(app):
    bar = FilterBar()
    combo = QLabel("filter")

    bar.add_widget(combo)

    assert bar.layout().indexOf(combo) != -1


def test_filter_bar_can_set_search_text_without_duplicating_signal(app):
    bar = FilterBar()
    received = []
    bar.search_changed.connect(received.append)

    bar.set_search_text("gamma")

    assert bar.search_edit.text() == "gamma"
    assert received == ["gamma"]
