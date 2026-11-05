"""Verify every reusable component works under both design palettes."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from panther.ui.components import (
    Badge,
    ConfirmDialog,
    DataTable,
    DestructiveButton,
    EmptyState,
    ErrorState,
    FilterBar,
    KeyValueList,
    LoadingState,
    MetricCard,
    PageScaffold,
    PrimaryButton,
    ScanProgress,
    SecondaryButton,
    Sparkline,
    StatusBanner,
    Toolbar,
)
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.theme import ThemeManager


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


@pytest.mark.parametrize(
    "theme,palette",
    [("light", LIGHT_COLORS), ("dark", DARK_COLORS)],
)
def test_all_components_construct_and_update_under_theme(app, theme, palette):
    resolved = ThemeManager.apply_theme(app, theme)
    assert resolved == theme
    assert palette.background in app.styleSheet()

    metric = MetricCard("CPU", "12.5%", "Processor Usage")
    banner = StatusBanner("Everything is healthy", "success")
    scaffold = PageScaffold("Storage", "Disk usage")
    table = DataTable()
    scan = ScanProgress()
    dialog = ConfirmDialog("Delete", "Are you sure?", destructive=True)
    primary = PrimaryButton("Run")
    secondary = SecondaryButton("Cancel")
    destructive = DestructiveButton("Delete")

    metric.set_progress(95)
    banner.set_state("error", "Something failed")
    scan.start("Scanning…", maximum=100)
    scan.set_progress(50)
    scan.finish()

    assert metric.progress.property("level") == "critical"
    assert banner.state == "error"
    assert banner.message == "Something failed"
    assert scan.progress.value() == 100
    assert scan.is_running is False
    assert dialog.confirm_button.property("variant") == "destructive"
    assert primary.property("variant") == "primary"
    assert secondary.property("variant") == "secondary"
    assert destructive.property("variant") == "destructive"
    assert scaffold.header.title_label.text() == "Storage"
    assert table.rowCount() == 0


@pytest.mark.parametrize(
    "theme",
    ["light", "dark"],
)
def test_phase2_components_construct_and_behave_under_both_themes(app, theme):
    resolved = ThemeManager.apply_theme(app, theme)
    assert resolved == theme

    empty = EmptyState("No results", "Adjust the filter", action_text="Refresh")
    unsupported = EmptyState("Requires Windows", variant="unsupported")
    loading = LoadingState("Scanning…")
    error = ErrorState("Failed", "The service did not respond")
    badge = Badge("Warning", status="warning")
    toolbar = Toolbar()
    filter_bar = FilterBar()
    details = KeyValueList()
    sparkline = Sparkline([1, 2, 3], role="cpu", theme=theme)
    table = DataTable()

    details.add_row("Path", "C:/temp/file.bin")
    toolbar.add_widget(empty)
    filter_bar.set_search_text("alpha")
    table.set_state("empty", "Nothing found")
    loading.stop()

    assert unsupported.variant == "unsupported"
    assert loading.is_running is False
    assert error.retry_button is error.action_button
    assert badge.property("status") == "warning"
    assert details.value("Path") == "C:/temp/file.bin"
    assert sparkline.values() == [1.0, 2.0, 3.0]
    assert table.state == "empty"
    assert filter_bar.search_text() == "alpha"
