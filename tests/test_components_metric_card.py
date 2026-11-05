"""Tests for the reusable MetricCard component."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from panther.ui.components.metric_card import MetricCard


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_metric_card_exposes_expected_widgets(app):
    card = MetricCard("CPU", "12.5%", "Processor Usage")

    assert card.objectName() == "metricCard"
    assert card.title_label.text() == "CPU"
    assert card.title_label.objectName() == "cardTitle"
    assert card.value_label.text() == "12.5%"
    assert card.value_label.objectName() == "cardValue"
    assert card.detail_label.text() == "Processor Usage"
    assert card.detail_label.objectName() == "cardDetail"
    assert card.progress.objectName() == "metricProgress"
    assert card.progress.value() == 0


def test_metric_card_updates_value_detail_and_progress(app):
    card = MetricCard("Memory", "0%", "0 GB / 8 GB")

    card.set_value("25.0%")
    card.set_detail("2.0 GB / 8.0 GB")
    card.set_progress(25)

    assert card.value_label.text() == "25.0%"
    assert card.detail_label.text() == "2.0 GB / 8.0 GB"
    assert card.progress.value() == 25
    assert card.progress.property("level") == "normal"


@pytest.mark.parametrize(
    "value,expected_level",
    [
        (10, "normal"),
        (60, "warning"),
        (90, "critical"),
        (100, "critical"),
        (-5, "normal"),
        (150, "critical"),
    ],
)
def test_metric_card_applies_threshold_levels(app, value, expected_level):
    card = MetricCard("Disk", "0%", "", warning_threshold=60, critical_threshold=85)

    card.set_progress(value)

    assert 0 <= card.progress.value() <= 100
    assert card.progress.property("level") == expected_level


def test_metric_card_accepts_explicit_level(app):
    card = MetricCard("Disk", "0%", "")

    card.set_progress(50, level="accent")

    assert card.progress.property("level") == "accent"


def test_metric_card_progress_can_be_hidden(app):
    card = MetricCard("Status", "On battery", "", progress_visible=False)

    assert card.progress.isHidden()


def test_metric_card_thresholds_can_be_changed(app):
    card = MetricCard("CPU", "0%", "")

    card.set_thresholds(warning=30, critical=70)
    card.set_progress(40)

    assert card.progress.property("level") == "warning"


def test_metric_card_optional_sparkline_is_created_only_when_requested(app):
    from panther.ui.components.sparkline import Sparkline

    plain = MetricCard("CPU", "0%", "")
    assert plain.sparkline is None

    trended = MetricCard(
        "CPU", "0%", "", sparkline=True, sparkline_role="cpu"
    )
    assert isinstance(trended.sparkline, Sparkline)
    assert trended.sparkline.role == "cpu"
