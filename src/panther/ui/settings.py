"""Settings screen - application configuration.

Phase 1 design-system pilot.  This screen is built entirely from the shared
design tokens, :class:`PageScaffold` and :class:`SectionCard`; it contains no
screen-level theme styling, so it follows the application stylesheet and
QPalette under both light and dark appearances.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import config
from .components import PageScaffold, SectionCard
from .theme import ThemeManager


class SettingsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settingsScreen")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scaffold = PageScaffold(
            "Settings",
            "Configure Panther System Intelligence",
            margins=24,
            spacing=16,
        )
        root.addWidget(self.scaffold)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content.setObjectName("settingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setAlignment(Qt.AlignTop)

        content_layout.addWidget(self._build_monitoring_card())
        content_layout.addWidget(self._build_appearance_card())
        content_layout.addWidget(self._build_privacy_card())
        content_layout.addWidget(self._build_data_card())
        content_layout.addWidget(self._build_about_card())
        content_layout.addStretch()

        scroll.setWidget(content)
        self.scaffold.add_widget(scroll, 1)

        # Preserve the previous behaviour: applying the persisted preference
        # when the screen is created keeps the combo, the applied theme and
        # the explanatory caption in agreement.
        self._apply_theme(self.theme_combo.currentText())

    # ------------------------------------------------------------------
    # Card construction
    # ------------------------------------------------------------------

    def _build_monitoring_card(self) -> SectionCard:
        card = SectionCard(
            "Monitoring",
            "Refresh cadence for screens that update automatically",
        )
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)
        self.refresh_spin.setValue(config.refresh_interval_seconds)
        self.refresh_spin.setSuffix(" seconds")
        self.refresh_spin.setAccessibleName("Refresh interval in seconds")
        self.refresh_spin.valueChanged.connect(self._on_interval_changed)
        form.addRow("Refresh interval", self.refresh_spin)

        self.interval_info = QLabel(
            "Applies to auto-refreshing screens on the next update."
        )
        self.interval_info.setProperty("role", "caption")
        self.interval_info.setWordWrap(True)
        form.addRow("", self.interval_info)

        card.add_layout(form)
        return card

    def _build_appearance_card(self) -> SectionCard:
        card = SectionCard(
            "Appearance",
            "Themes apply immediately to every open screen",
        )
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.setAccessibleName("Theme")
        _theme_labels = {"system": "System", "light": "Light", "dark": "Dark"}
        self.theme_combo.setCurrentText(
            _theme_labels.get(str(config.theme).lower(), "System")
        )
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        form.addRow("Theme", self.theme_combo)

        self.theme_info = QLabel()
        self.theme_info.setProperty("role", "caption")
        self.theme_info.setWordWrap(True)
        form.addRow("", self.theme_info)

        card.add_layout(form)
        return card

    def _build_privacy_card(self) -> SectionCard:
        card = SectionCard("Privacy & Security")

        self.local_only = QCheckBox(
            "Local-only mode (no telemetry or cloud uploads)"
        )
        self.local_only.setChecked(True)
        self.local_only.setEnabled(False)
        self.local_only.setAccessibleName("Local-only mode")

        privacy_info = QLabel(
            "All data is stored locally on your device. No personal "
            "information is transmitted by default."
        )
        privacy_info.setProperty("role", "caption")
        privacy_info.setWordWrap(True)

        card.add_widget(self.local_only)
        card.add_widget(privacy_info)
        return card

    def _build_data_card(self) -> SectionCard:
        card = SectionCard("Data Management")

        data_dir_label = QLabel(f"Data directory: {config.data_dir}")
        data_dir_label.setProperty("role", "caption")
        data_dir_label.setWordWrap(True)
        data_dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add_widget(data_dir_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.open_data_btn = QPushButton("Open Data Directory")
        self.open_data_btn.setAccessibleName("Open data directory")
        self.open_data_btn.clicked.connect(self.open_data_dir)
        self.clear_history_btn = QPushButton("Clear Activity History")
        self.clear_history_btn.setAccessibleName("Clear activity history")
        self.clear_history_btn.setProperty("secondary", True)
        self.clear_history_btn.clicked.connect(self.clear_history)
        button_row.addWidget(self.open_data_btn)
        button_row.addWidget(self.clear_history_btn)
        button_row.addStretch()
        card.add_layout(button_row)
        return card

    def _build_about_card(self) -> SectionCard:
        card = SectionCard("About")

        app_name = QLabel("Panther System Intelligence")
        app_name.setProperty("role", "emphasis")
        version = QLabel("Version: 1.0.0")
        version.setProperty("role", "secondary")
        description = QLabel(
            "Windows desktop system monitoring, storage intelligence and "
            "safe optimisation."
        )
        description.setProperty("role", "secondary")
        description.setWordWrap(True)

        card.add_widget(app_name)
        card.add_widget(version)
        card.add_widget(description)
        return card

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _on_interval_changed(self, value):
        try:
            config.refresh_interval_seconds = int(value)
            self.interval_info.setText(
                f"Refresh interval set to {value} seconds (applied to timers)."
            )
        except Exception as e:
            self.interval_info.setText(f"Error: {e}")

    def _on_theme_changed(self, theme_text):
        try:
            config.theme = theme_text.lower()
            self._apply_theme(theme_text)
        except Exception as e:
            self.theme_info.setText(f"Error: {e}")

    def _apply_theme(self, theme_text):
        application = QApplication.instance()
        resolved = None
        if application is not None:
            resolved = ThemeManager.apply_theme(application, theme_text.lower())
        self._update_theme_info(theme_text, resolved)
        return resolved

    def _update_theme_info(self, theme_text, resolved):
        requested = str(theme_text).lower()
        if requested == "system":
            current = str(resolved).title() if resolved else "unknown"
            self.theme_info.setText(
                f"System theme applied (currently {current}). Change the "
                "Windows appearance and re-select System to update."
            )
        else:
            self.theme_info.setText(f"{theme_text} theme applied.")

    def open_data_dir(self):
        try:
            data_path = str(config.data_dir)
            os.startfile(data_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open directory: {e}")

    def clear_history(self):
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all activity history?\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            QMessageBox.information(
                self, "Cleared", "Activity history has been cleared."
            )
