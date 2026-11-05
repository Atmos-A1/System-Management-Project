#!/usr/bin/env python3
"""Render the Phase 2 component gallery in both appearances.

Used as visual evidence that the shared components, including their loading,
empty, error and badge states, render correctly under light and dark themes.
The same window is switched between themes to exercise already-created widgets.

Usage:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python tools/ui_phase2_gallery.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from panther.ui.components import (  # noqa: E402
    Badge,
    DataTable,
    EmptyState,
    ErrorState,
    FilterBar,
    KeyValueList,
    LoadingState,
    SectionCard,
    Sparkline,
    Toolbar,
)
from panther.ui.theme import ThemeManager  # noqa: E402

OUT_DIR = os.environ.get("PHASE2_SHOT_DIR", "/tmp/opencode/phase2-shots")


def build_gallery() -> QWidget:
    window = QWidget()
    window.setObjectName("centralWidget")
    layout = QVBoxLayout(window)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    badges = SectionCard("Badges", "Status is text, colour is supplementary")
    badge_row = Toolbar()
    for text, status in (
        ("Neutral", "neutral"),
        ("Info", "info"),
        ("Healthy", "success"),
        ("Warning", "warning"),
        ("Critical", "critical"),
    ):
        badge_row.add_widget(Badge(text, status=status))
    badge_row.add_stretch()
    badges.add_widget(badge_row)

    states = SectionCard("States")
    states.add_widget(
        EmptyState(
            "No results",
            "Nothing matched the current filter.",
            action_text="Refresh",
        )
    )
    states.add_widget(
        EmptyState(
            "Requires Windows",
            "Startup entries are read from the Windows registry.",
            variant="unsupported",
        )
    )
    states.add_widget(LoadingState("Scanning applications…"))
    states.add_widget(
        ErrorState("Scan failed", "The background worker stopped unexpectedly.")
    )

    filters = SectionCard("Toolbar and filters")
    filters.add_widget(FilterBar("Search activity…"))

    details = SectionCard("Details")
    key_values = KeyValueList()
    key_values.add_row("Path", "C:/Users/alice/Downloads/report.pdf")
    key_values.add_row("Size", "4.2 MB")
    key_values.add_row("Status", "Read-only")
    details.add_widget(key_values)

    trends = SectionCard("Sparklines", "One token colour per resource type")
    trend_row = Toolbar()
    for role in ("cpu", "memory", "storage", "battery", "network"):
        spark = Sparkline([3, 5, 4, 8, 6, 9, 7], role=role)
        spark.setMinimumWidth(120)
        trend_row.add_widget(QLabel(role.title()))
        trend_row.add_widget(spark, stretch=1)
    trends.add_widget(trend_row)

    table_card = SectionCard("Table state overlay")
    table = DataTable()
    table.set_state("empty", "No processes matched the filter")
    table.setMinimumHeight(160)
    table_card.add_widget(table)

    for card in (badges, states, filters, details, trends, table_card):
        card.setMinimumWidth(520)
        layout.addWidget(card)
    layout.addStretch()
    return window


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_gallery()
    window.resize(900, 1180)
    window.show()
    app.processEvents()

    for theme in ("light", "dark"):
        ThemeManager.apply_theme(app, theme)
        app.processEvents()
        app.processEvents()
        path = os.path.join(OUT_DIR, f"gallery-{theme}.png")
        window.grab().save(path)
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
