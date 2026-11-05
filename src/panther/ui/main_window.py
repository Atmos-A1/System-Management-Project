"""Panther System Intelligence UI - main window.

Provides a QMainWindow with a permanent left-sidebar navigation list.
The central widget is a stacked widget that hosts all screens.
"""

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QLabel,
)
from PySide6.QtCore import Qt

from ..config import config
from .navigation import NAV_ITEMS, nav_icon
from .theme import ThemeManager
from .dashboard import DashboardScreen
from .processes import ProcessesScreen
from .adaptive_control import AdaptiveControlScreen
from .startup import StartupScreen
from .battery import BatteryScreen
from .recommendations import RecommendationsScreen
from .history import HistoryScreen
from .storage import StorageScreen
from .applications import ApplicationsScreen
from .settings import SettingsScreen


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panther System Intelligence")
        self.resize(1150, 780)
        # Keep the shell usable when a user resizes or a display is scaled.
        self.setMinimumSize(900, 600)

        # Apply the persisted theme at the shell boundary.  Individual
        # screens still own their component-specific styling for now.
        application = QApplication.instance()
        self.resolved_theme = ThemeManager.apply_theme(application, config.theme)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        # Responsive shell: the sidebar keeps a comfortable range instead of
        # a fixed pixel width, and the stack takes all remaining space.
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(260)
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        for name, icon_key in NAV_ITEMS:
            item = QListWidgetItem(name)
            item.setIcon(nav_icon(icon_key))
            self.sidebar.addItem(item)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        _screen_map = {
            "Dashboard": DashboardScreen,
            "Processes": ProcessesScreen,
            "Adaptive Control": AdaptiveControlScreen,
            "Storage": StorageScreen,
            "Battery": BatteryScreen,
            "Startup Apps": StartupScreen,
            "Applications": ApplicationsScreen,
            "Recommendations": RecommendationsScreen,
            "Activity History": HistoryScreen,
            "Settings": SettingsScreen,
        }

        self._screen_classes = _screen_map
        self._screen_widgets = {}
        for name, _icon in NAV_ITEMS:
            cls = _screen_map.get(name)
            if cls is not None:
                # Lazy load - create widgets on demand for performance
                self.stack.addWidget(QWidget())  # placeholder
            else:
                placeholder = QLabel(f"{name} screen - coming soon")
                placeholder.setAlignment(Qt.AlignCenter)
                self.stack.addWidget(placeholder)

        layout.addWidget(self.stack, 1)

        self.sidebar.currentRowChanged.connect(self._on_tab_changed)
        self.sidebar.setCurrentRow(0)
        # Expose stack for external navigation
        self.stack_widget = self.stack
    
    def closeEvent(self, event):
        # Stop background workers before Qt destroys child widgets.
        for widget in tuple(self._screen_widgets.values()):
            try:
                widget.close()
            except Exception:
                pass
        super().closeEvent(event)

    def _on_tab_changed(self, index):
        # Lazy load screen if not loaded
        if index in self._screen_widgets:
            self.stack.setCurrentIndex(index)
            return
        # Find name
        if index < len(NAV_ITEMS):
            name, _ = NAV_ITEMS[index]
            cls = self._screen_classes.get(name)
            if cls is not None:
                try:
                    widget = cls()
                    old_widget = self.stack.widget(index)
                    self.stack.removeWidget(old_widget)
                    try:
                        old_widget.deleteLater()
                    except Exception:
                        pass
                    self.stack.insertWidget(index, widget)
                    self._screen_widgets[index] = widget
                except Exception as e:
                    placeholder = QLabel(f"Error loading {name}: {e}")
                    placeholder.setAlignment(Qt.AlignCenter)
                    old_widget = self.stack.widget(index)
                    self.stack.removeWidget(old_widget)
                    try:
                        old_widget.deleteLater()
                    except Exception:
                        pass
                    self.stack.insertWidget(index, placeholder)
            self.stack.setCurrentIndex(index)
        else:
            self.stack.setCurrentIndex(index)
