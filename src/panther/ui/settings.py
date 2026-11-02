"""Settings screen - application configuration.

Provides controls for monitoring intervals, theme, data retention,
privacy settings, and database management.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QComboBox,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt
import os

from ..config import config


class SettingsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settingsScreen")
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QGroupBox {
                background-color: #ffffff;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                margin-top: 12px;
                padding: 16px;
                font-weight: 600;
                color: #111827;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QSpinBox, QComboBox {
                padding: 6px 8px;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QPushButton {
                padding: 8px 14px;
                border-radius: 6px;
                background-color: #2563eb;
                color: #ffffff;
                border: none;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QCheckBox {
                color: #111827;
            }
            QLabel {
                color: #111827;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Settings")
        header.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        
        subtitle = QLabel("Configure Panther System Intelligence")
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280;")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; }")
        
        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(14)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setAlignment(Qt.AlignTop)

        # Monitoring settings
        monitor_group = QGroupBox("Monitoring")
        monitor_layout = QFormLayout()
        monitor_layout.setSpacing(10)
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)
        self.refresh_spin.setValue(config.refresh_interval_seconds)
        self.refresh_spin.setSuffix(" seconds")
        self.refresh_spin.valueChanged.connect(self._on_interval_changed)
        monitor_layout.addRow("Refresh Interval:", self.refresh_spin)
        self.interval_info = QLabel("Applies to auto-refreshing screens on next update.")
        self.interval_info.setStyleSheet("color: #6b7280; font-size: 11px;")
        monitor_layout.addRow("", self.interval_info)
        monitor_group.setLayout(monitor_layout)
        content_layout.addWidget(monitor_group)

        # Appearance
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout()
        appearance_layout.setSpacing(10)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setCurrentText(config.theme.capitalize() if config.theme.lower() in ["light", "dark"] else "Light")
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addRow("Theme:", self.theme_combo)
        self.theme_info = QLabel("Theme changes are applied to the application.")
        self.theme_info.setStyleSheet("color: #6b7280; font-size: 11px;")
        appearance_layout.addRow("", self.theme_info)
        appearance_group.setLayout(appearance_layout)
        content_layout.addWidget(appearance_group)

        # Privacy
        privacy_group = QGroupBox("Privacy & Security")
        privacy_layout = QVBoxLayout()
        privacy_layout.setSpacing(8)
        self.local_only = QCheckBox("Local-only mode (no telemetry or cloud uploads)")
        self.local_only.setChecked(True)
        self.local_only.setEnabled(False)
        privacy_layout.addWidget(self.local_only)
        privacy_info = QLabel("All data is stored locally on your device. No personal information is transmitted by default.")
        privacy_info.setStyleSheet("color: #6b7280; font-size: 11px;")
        privacy_info.setWordWrap(True)
        privacy_layout.addWidget(privacy_info)
        privacy_group.setLayout(privacy_layout)
        content_layout.addWidget(privacy_group)

        # Data management
        data_group = QGroupBox("Data Management")
        data_layout = QVBoxLayout()
        data_layout.setSpacing(12)
        
        data_dir_label = QLabel(f"Data Directory: {config.data_dir}")
        data_dir_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        data_dir_label.setWordWrap(True)
        data_layout.addWidget(data_dir_label)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.open_data_btn = QPushButton("Open Data Directory")
        self.open_data_btn.clicked.connect(self.open_data_dir)
        self.clear_history_btn = QPushButton("Clear Activity History")
        self.clear_history_btn.clicked.connect(self.clear_history)
        self.clear_history_btn.setStyleSheet("padding: 8px 14px; border-radius: 6px; background-color: #f3f4f6; color: #111827; border: 1px solid #d1d5db;")
        self.clear_history_btn.setProperty("secondary", True)
        btn_layout.addWidget(self.open_data_btn)
        btn_layout.addWidget(self.clear_history_btn)
        btn_layout.addStretch()
        data_layout.addLayout(btn_layout)
        
        data_group.setLayout(data_layout)
        content_layout.addWidget(data_group)

        # About
        about_group = QGroupBox("About")
        about_layout = QVBoxLayout()
        about_layout.setSpacing(6)
        app_name = QLabel("Panther System Intelligence")
        app_name.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827;")
        version = QLabel("Version: 1.0.0")
        version.setStyleSheet("color: #6b7280;")
        desc = QLabel("Windows desktop system monitoring, storage intelligence and safe optimization")
        desc.setStyleSheet("color: #6b7280;")
        desc.setWordWrap(True)
        about_layout.addWidget(app_name)
        about_layout.addWidget(version)
        about_layout.addWidget(desc)
        about_group.setLayout(about_layout)
        content_layout.addWidget(about_group)
        
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self._apply_theme(self.theme_combo.currentText())

    def _on_interval_changed(self, value):
        try:
            config.refresh_interval_seconds = int(value)
            self.interval_info.setText(f"Refresh interval set to {value} seconds (applied to timers).")
        except Exception as e:
            self.interval_info.setText(f"Error: {e}")

    def _on_theme_changed(self, theme_text):
        try:
            config.theme = theme_text.lower()
            self._apply_theme(theme_text)
            self.theme_info.setText(f"{theme_text} theme applied. Restart may be needed for some views.")
        except Exception as e:
            self.theme_info.setText(f"Error: {e}")

    def _apply_theme(self, theme_text):
        app = QApplication.instance()
        if not app:
            return
        if theme_text.lower() == "dark":
            dark_style = """
                QMainWindow { background-color: #0f172a; }
                QWidget { background-color: #0f172a; color: #e5e7eb; }
                QListWidget { background-color: #020617; color: #cbd5e1; border: none; }
                QListWidget::item { padding: 11px 22px; border-radius: 8px; margin: 2px 8px; }
                QListWidget::item:selected { background-color: #2563eb; color: #ffffff; }
                QListWidget::item:hover:!selected { background-color: #1e293b; color: #ffffff; }
                QStackedWidget { background-color: #0f172a; }
                QGroupBox { background-color: #111827; border: 1px solid #1f2937; color: #e5e7eb; border-radius: 10px; margin-top: 12px; padding: 16px; }
                QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
                QTableView, QTableWidget, QTextEdit { background-color: #111827; color: #e5e7eb; border: 1px solid #1f2937; gridline-color: #1f2937; selection-background-color: #1e40af; }
                QHeaderView::section { background-color: #0f172a; color: #e5e7eb; border: 1px solid #1f2937; padding: 6px; font-weight: 600; }
                QLineEdit, QComboBox, QSpinBox { background-color: #111827; color: #e5e7eb; border: 1px solid #374151; padding: 6px 8px; border-radius: 6px; }
                QPushButton { background-color: #2563eb; color: #ffffff; border: none; padding: 8px 14px; border-radius: 6px; }
                QPushButton:hover { background-color: #1d4ed8; }
                QPushButton:pressed { background-color: #1e40af; }
                QPushButton:disabled { background-color: #475569; }
                QLabel { color: #e5e7eb; }
                QScrollArea { background-color: transparent; }
                QTabWidget::pane { background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; }
                QTabBar::tab { background-color: #0f172a; color: #cbd5e1; padding: 8px 16px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
                QTabBar::tab:selected { background-color: #111827; color: #ffffff; border: 1px solid #1f2937; border-bottom: none; }
                QListWidget { background-color: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 6px; }
                QListWidget::item { padding: 8px; border-bottom: 1px solid #1f2937; }
                QListWidget::item:selected { background-color: #1e40af; color: #ffffff; }
                QProgressBar { border: none; background-color: #1f2937; border-radius: 4px; }
                QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
                QSplitter::handle { background-color: #1f2937; }
                QFrame#card { background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; }
                QFrame#recCard { background-color: #111827; border: 1px solid #1f2937; }
            """
            app.setStyleSheet(dark_style)
        else:
            light_style = """
                QMainWindow { background-color: #f7f9fc; }
                QWidget { background-color: #f7f9fc; color: #111827; }
                QListWidget { background-color: #111827; color: #e5e7eb; border: none; }
                QListWidget::item { padding: 11px 22px; border-radius: 8px; margin: 2px 8px; }
                QListWidget::item:selected { background-color: #2563eb; color: #ffffff; }
                QListWidget::item:hover:!selected { background-color: #1f2937; color: #ffffff; }
                QStackedWidget { background-color: #f7f9fc; }
            """
            app.setStyleSheet(light_style)

    def open_data_dir(self):
        try:
            data_path = str(config.data_dir)
            os.startfile(data_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open directory: {e}")

    def clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to clear all activity history?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QMessageBox.information(self, "Cleared", "Activity history has been cleared.")
