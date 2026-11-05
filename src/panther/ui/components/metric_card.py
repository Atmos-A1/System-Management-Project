"""Reusable metric card for glanceable system measurements."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from .sparkline import Sparkline


class MetricCard(QFrame):
    """Title, prominent value, detail line and optional threshold bar."""

    def __init__(
        self,
        title: str,
        value: str = "—",
        detail: str = "",
        progress_visible: bool = True,
        warning_threshold: int = 70,
        critical_threshold: int = 90,
        sparkline: bool = False,
        sparkline_role: str = "accent",
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setProperty("compact", bool(compact))
        self._warning_threshold = int(warning_threshold)
        self._critical_threshold = int(critical_threshold)
        self._validate_thresholds()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        self.title_label = QLabel(str(title))
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("cardValue")
        self.value_label.setProperty("compact", bool(compact))
        self.value_label.setAlignment(Qt.AlignCenter)
        self.detail_label = QLabel(str(detail))
        self.detail_label.setObjectName("cardDetail")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("metricProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setProperty("level", "normal")

        self.sparkline = None
        if sparkline:
            self.sparkline = Sparkline(role=sparkline_role)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        if self.sparkline is not None:
            layout.addWidget(self.sparkline)
        layout.addWidget(self.progress)

        self.set_progress_visible(progress_visible)

    @property
    def warning_threshold(self) -> int:
        return self._warning_threshold

    @property
    def critical_threshold(self) -> int:
        return self._critical_threshold

    def set_value(self, value) -> None:
        self.value_label.setText(str(value))

    def set_detail(self, detail) -> None:
        self.detail_label.setText(str(detail))

    def set_progress(self, value, level: str = None) -> None:
        try:
            numeric = int(value)
        except (TypeError, ValueError, OverflowError):
            numeric = 0
        numeric = max(0, min(100, numeric))
        self.progress.setValue(numeric)

        if level is None:
            level = self._level_for(numeric)
        self.set_progress_level(level)

    def set_progress_level(self, level: str) -> None:
        self.progress.setProperty("level", str(level))
        style = self.progress.style()
        style.unpolish(self.progress)
        style.polish(self.progress)
        self.progress.update()

    def set_thresholds(self, warning: int, critical: int) -> None:
        self._warning_threshold = int(warning)
        self._critical_threshold = int(critical)
        self._validate_thresholds()

    def set_progress_visible(self, visible: bool) -> None:
        self.progress.setVisible(bool(visible))

    def _validate_thresholds(self) -> None:
        if self._warning_threshold >= self._critical_threshold:
            raise ValueError("warning threshold must be below critical threshold")

    def _level_for(self, value: int) -> str:
        if value >= self._critical_threshold:
            return "critical"
        if value >= self._warning_threshold:
            return "warning"
        return "normal"
