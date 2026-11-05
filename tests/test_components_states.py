"""Tests for the EmptyState, LoadingState and ErrorState primitives."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from panther.ui.components import EmptyState, ErrorState, LoadingState


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


# ---------------------------------------------------------------------------
# EmptyState
# ---------------------------------------------------------------------------


def test_empty_state_renders_title_description_and_variant(app):
    state = EmptyState(
        "No results",
        "Nothing matched the current filter.",
        action_text="Refresh",
    )

    assert state.objectName() == "emptyState"
    assert state.title_label.text() == "No results"
    assert state.title_label.objectName() == "stateTitle"
    assert state.description_label.text() == "Nothing matched the current filter."
    assert state.action_button.text() == "Refresh"
    assert state.property("variant") == "empty"
    assert state.accessibleName() == "No results"


def test_empty_state_defaults_to_no_action_button(app):
    state = EmptyState("Nothing here")

    assert state.action_button is None


def test_empty_state_unsupported_variant_is_machine_readable(app):
    state = EmptyState("Requires Windows", variant="unsupported")

    assert state.property("variant") == "unsupported"
    assert state.variant == "unsupported"


def test_empty_state_rejects_unknown_variant(app):
    with pytest.raises(ValueError):
        EmptyState("x", variant="sepia")


def test_empty_state_action_button_is_keyboard_focusable_and_signals(app):
    state = EmptyState("Nothing here", action_text="Refresh")
    triggered = []
    state.action_triggered.connect(lambda: triggered.append(True))

    assert state.action_button.focusPolicy() != Qt.NoFocus
    assert state.action_button.accessibleName() == "Refresh"

    state.action_button.click()
    assert triggered == [True]


def test_empty_state_can_update_text_and_action(app):
    state = EmptyState("Old")
    state.set_title("New")
    state.set_description("Details")
    state.set_action_text("Try again")

    assert state.title_label.text() == "New"
    assert state.description_label.text() == "Details"
    assert state.action_button.text() == "Try again"
    assert state.accessibleName() == "New"


# ---------------------------------------------------------------------------
# LoadingState
# ---------------------------------------------------------------------------


def test_loading_state_is_indeterminate_while_running(app):
    state = LoadingState("Scanning…")

    assert state.objectName() == "loadingState"
    assert state.message_label.text() == "Scanning…"
    assert state.is_running is True
    assert state.progress.minimum() == 0
    assert state.progress.maximum() == 0
    assert state.progress.accessibleName() != ""


def test_loading_state_stops_to_a_determinate_bar(app):
    state = LoadingState()

    state.stop()

    assert state.is_running is False
    assert state.progress.maximum() == 100
    assert state.progress.value() == 0


def test_loading_state_message_can_change(app):
    state = LoadingState("Starting")

    state.set_message("Almost there")

    assert state.message_label.text() == "Almost there"
    assert state.accessibleName() == "Almost there"


# ---------------------------------------------------------------------------
# ErrorState
# ---------------------------------------------------------------------------


def test_error_state_provides_a_retry_action(app):
    state = ErrorState(
        "Could not load",
        "The service did not respond.",
    )

    assert state.objectName() == "errorState"
    assert state.title_label.text() == "Could not load"
    assert state.retry_button.text() == "Try again"
    assert state.retry_button is state.action_button


def test_error_state_retry_signal_is_emitted(app):
    state = ErrorState("Failed")
    retries = []
    state.retry_requested.connect(lambda: retries.append(True))

    state.retry_button.click()

    assert retries == [True]


def test_error_state_accepts_custom_action_text(app):
    state = ErrorState("Failed", action_text="Reload")

    assert state.retry_button.text() == "Reload"
