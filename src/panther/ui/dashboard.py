"""Dashboard screen - system overview built on the shared design system."""

import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import config
from ..services.system_monitor import (
    get_battery_info,
    get_cpu_percent,
    get_disk_usage,
    get_ram_usage,
)
from .components import (
    Badge,
    MetricCard,
    PageScaffold,
    SecondaryButton,
    StatusBanner,
    Toolbar,
)
from .theme import ThemeManager


class DashboardScreen(QWidget):
    """Glanceable CPU, memory, storage and battery summary cards."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dashboardScreen")
        self._theme = ThemeManager.current_theme()
        self._errors = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scaffold = PageScaffold(
            "System Dashboard",
            "Real-time monitoring of your system resources.",
        )
        layout.addWidget(self.scaffold)

        self.summary_bar = Toolbar()
        self.health_badge = Badge("Checking…", "neutral")
        self.updated_label = QLabel("Collecting metrics…")
        self.updated_label.setProperty("role", "caption")
        self.refresh_button = SecondaryButton("Refresh")
        self.refresh_button.setAccessibleName("Refresh system metrics")
        self.refresh_button.setToolTip("Refresh system metrics")
        self.refresh_button.clicked.connect(self.refresh)

        self.summary_bar.add_widget(self.health_badge)
        self.summary_bar.add_widget(self.updated_label)
        self.summary_bar.add_widget(self.refresh_button, align="right")

        self.status_banner = StatusBanner()
        self.scaffold.content_layout.addWidget(self.summary_bar)
        self.scaffold.content_layout.addWidget(self.status_banner)

        self.cpu_card = self._create_card(
            "CPU", "Processor Usage", role="cpu", warning=65, critical=85
        )
        self.ram_card = self._create_card(
            "Memory (RAM)", "Memory Usage", role="memory", warning=80, critical=90
        )
        self.disk_card = self._create_card(
            "Storage", "Disk Usage", role="storage", warning=85, critical=92
        )
        self.battery_card = self._create_card(
            "Battery", "Battery Status", role="battery", warning=20, critical=100
        )

        # Compatibility aliases used by older callers and tests.
        self.cpu_label = self.cpu_card.value_label
        self.ram_label = self.ram_card.value_label
        self.disk_label = self.disk_card.value_label
        self.battery_label = self.battery_card.value_label
        self.cpu_detail_label = self.cpu_card.detail_label
        self.ram_detail_label = self.ram_card.detail_label
        self.disk_detail_label = self.disk_card.detail_label
        self.battery_detail_label = self.battery_card.detail_label

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_body = QWidget()
        scroll_body.setObjectName("dashboardScrollBody")
        grid = QGridLayout(scroll_body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        grid.addWidget(self.cpu_card, 0, 0)
        grid.addWidget(self.ram_card, 0, 1)
        grid.addWidget(self.disk_card, 1, 0)
        grid.addWidget(self.battery_card, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(2, 1)
        self.scroll_area.setWidget(scroll_body)
        self.scaffold.content_layout.addWidget(self.scroll_area, 1)

        self._apply_theme_to_charts(self._theme)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    # -- construction helpers -------------------------------------------

    def _create_card(self, title, detail, role, warning, critical):
        card = MetricCard(
            title,
            "—",
            detail,
            sparkline=True,
            sparkline_role=role,
            warning_threshold=warning,
            critical_threshold=critical,
        )
        card.setMinimumHeight(190)
        return card

    def _apply_theme_to_charts(self, theme: str) -> None:
        for card in (
            self.cpu_card,
            self.ram_card,
            self.disk_card,
            self.battery_card,
        ):
            if card.sparkline is not None:
                card.sparkline.set_theme(theme)

    def _on_theme_changed(self, theme: str) -> None:
        self._theme = str(theme)
        self._apply_theme_to_charts(self._theme)

    # -- refresh --------------------------------------------------------

    def refresh(self) -> None:
        errors = []

        # CPU
        try:
            cpu = float(get_cpu_percent())
        except Exception:
            errors.append("CPU")
            self.cpu_card.set_value("N/A")
            self.cpu_card.set_detail("Unavailable")
            self.cpu_card.set_progress(0, level="normal")
        else:
            self.cpu_card.set_value(f"{cpu:.1f}%")
            self.cpu_card.set_detail("Processor Usage")
            self.cpu_card.set_progress(cpu)
            self.cpu_card.sparkline.append(cpu)

        # Memory
        try:
            ram = get_ram_usage()
            ram_percent = float(ram["percent"])
            used_gb = ram["used"] / (1024**3)
            total_gb = ram["total"] / (1024**3)
        except Exception:
            errors.append("Memory")
            self.ram_card.set_value("N/A")
            self.ram_card.set_detail("Unavailable")
            self.ram_card.set_progress(0, level="normal")
        else:
            self.ram_card.set_value(f"{ram_percent:.1f}%")
            self.ram_card.set_detail(f"{used_gb:.1f} GB / {total_gb:.1f} GB")
            self.ram_card.set_progress(ram_percent)
            self.ram_card.sparkline.append(ram_percent)

        # Storage
        try:
            disk = get_disk_usage()
            disk_percent = float(disk["percent"])
            disk_used_gb = disk["used"] / (1024**3)
            disk_total_gb = disk["total"] / (1024**3)
        except Exception:
            errors.append("Storage")
            self.disk_card.set_value("N/A")
            self.disk_card.set_detail("Unavailable")
            self.disk_card.set_progress(0, level="normal")
        else:
            self.disk_card.set_value(f"{disk_percent:.1f}%")
            self.disk_card.set_detail(
                f"{disk_used_gb:.1f} GB / {disk_total_gb:.1f} GB"
            )
            self.disk_card.set_progress(disk_percent)
            self.disk_card.sparkline.append(disk_percent)

        # Battery
        try:
            battery = get_battery_info()
        except Exception:
            errors.append("Battery")
            self.battery_card.set_value("N/A")
            self.battery_card.set_detail("Unavailable")
            self.battery_card.set_progress(0, level="normal")
        else:
            if battery:
                battery_percent = float(battery["percent"])
                plugged = bool(battery.get("power_plugged"))
                self.battery_card.set_value(f"{battery_percent:.0f}%")
                self.battery_card.set_detail(
                    "Charging" if plugged else "Discharging"
                )
                if plugged:
                    level = "accent"
                elif battery_percent <= 10:
                    level = "critical"
                elif battery_percent <= 20:
                    level = "warning"
                else:
                    level = "normal"
                self.battery_card.set_progress(battery_percent, level=level)
                self.battery_card.sparkline.append(battery_percent)
            else:
                self.battery_card.set_value("N/A")
                self.battery_card.set_detail("No battery detected")
                self.battery_card.set_progress(0, level="normal")

        self._errors = errors
        self._update_health(errors)
        self.updated_label.setText(
            "Updated " + datetime.datetime.now().strftime("%H:%M:%S")
        )

    def _update_health(self, errors) -> None:
        if errors:
            status = "critical"
            text = "Degraded"
            self.status_banner.set_state(
                "error",
                "Some system metrics are unavailable: "
                + ", ".join(errors)
                + ".",
            )
        else:
            status = "success"
            text = "Healthy"
            self.status_banner.clear()

            if self.cpu_card.progress.value() >= self.cpu_card.critical_threshold:
                status, text = "critical", "Critical"
            elif self.ram_card.progress.value() >= self.ram_card.critical_threshold:
                status, text = "critical", "Critical"
            elif self.disk_card.progress.value() >= self.disk_card.critical_threshold:
                status, text = "critical", "Critical"
            elif self._battery_is_low():
                status, text = "warning", "Attention"
            elif self.cpu_card.progress.value() >= self.cpu_card.warning_threshold:
                status, text = "warning", "Attention"
            elif self.ram_card.progress.value() >= self.ram_card.warning_threshold:
                status, text = "warning", "Attention"
            elif self.disk_card.progress.value() >= self.disk_card.warning_threshold:
                status, text = "warning", "Attention"

        self.health_badge.set_text(text)
        self.health_badge.set_status(status)

    def _battery_is_low(self) -> bool:
        detail = self.battery_card.detail_label.text()
        if detail != "Discharging":
            return False
        return self.battery_card.progress.value() <= self.battery_card.warning_threshold
