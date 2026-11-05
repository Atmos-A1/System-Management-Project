"""Tests for the SectionCard primitive introduced by Phase 1."""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from panther.ui.components import SectionCard
from panther.ui.components.section_card import SectionCard as SectionCardDirect


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def test_section_card_is_exported_from_components_package():
    assert SectionCard is SectionCardDirect


def test_section_card_renders_title_and_subtitle(app):
    card = SectionCard("Monitoring", "Refresh cadence for live screens")

    assert card.objectName() == "sectionCard"
    assert card.title_label.objectName() == "sectionTitle"
    assert card.subtitle_label.objectName() == "sectionSubtitle"
    assert card.title_label.text() == "Monitoring"
    assert card.subtitle_label.text() == "Refresh cadence for live screens"
    assert card.title_label.accessibleName() == "Monitoring"


def test_section_card_hides_empty_subtitle(app):
    card = SectionCard("Appearance")
    assert card.header.isHidden() is False
    assert card.subtitle_label.isVisible() is False


def test_section_card_without_title_hides_header(app):
    card = SectionCard()
    assert card.header.isHidden() is True


def test_section_card_accepts_widgets_and_layouts(app):
    card = SectionCard("Data Management")
    body_layout = QVBoxLayout()
    body_layout.addWidget(QLabel("Body"))
    card.add_layout(body_layout)
    card.add_widget(QWidget())

    assert card.body_layout.count() == 2
    assert card.body.objectName() == "sectionCardBody"


def test_section_card_updates_title_after_construction(app):
    card = SectionCard()
    card.set_title("About")
    card.set_subtitle("Version information")

    assert card.title_label.text() == "About"
    assert card.subtitle_label.text() == "Version information"
    assert card.header.isHidden() is False
