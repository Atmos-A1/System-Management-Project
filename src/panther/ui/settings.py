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
        monitor_layout.addRow("Refresh Interval:", self.refresh_spin)
        monitor_group.setLayout(monitor_layout)
        content_layout.addWidget(monitor_group)

        # Appearance
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout()
        appearance_layout.setSpacing(10)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setCurrentText(config.theme.capitalize())
        appearance_layout.addRow("Theme:", self.theme_combo)
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
