"""Lightweight QPainter trend line for a short numeric series.

No charting dependency is introduced: the widget draws a scaled polyline
using a colour resolved from a design token so both appearances are covered.
"""

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..design_system import palette_for

CHART_ROLES = ("accent", "cpu", "memory", "storage", "battery", "network")


class Sparkline(QWidget):
    """A non-interactive trend line; text is available to screen readers."""

    def __init__(
        self,
        values=None,
        role: str = "accent",
        theme: str = "light",
        max_points: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("sparkline")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName("Trend chart")
        self.setMinimumHeight(28)
        self._theme = "light"
        self._role = "accent"
        self._color = None
        self._max_points = max(2, int(max_points))
        self._values = []

        self.set_theme(theme)
        self.set_role(role)
        if values:
            self.set_values(values)
        self._update_accessible_description()

    # -- data -------------------------------------------------------------

    def values(self):
        return list(self._values)

    def set_values(self, values):
        cleaned = []
        for value in values or []:
            try:
                cleaned.append(float(value))
            except (TypeError, ValueError):
                continue
        self._values = cleaned[-self._max_points :]
        self._update_accessible_description()
        self.update()

    def append(self, value) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        self._values.append(number)
        if len(self._values) > self._max_points:
            del self._values[: len(self._values) - self._max_points]
        self._update_accessible_description()
        self.update()

    # -- appearance -------------------------------------------------------

    @property
    def role(self) -> str:
        return self._role

    @property
    def theme(self) -> str:
        return self._theme

    def set_role(self, role: str) -> None:
        normalized = str(role).lower()
        if normalized not in CHART_ROLES:
            raise ValueError(f"Unknown sparkline role: {role}")
        self._role = normalized
        self.update()

    def set_theme(self, theme: str) -> None:
        self._theme = "dark" if str(theme).lower() == "dark" else "light"
        self.update()

    def set_color(self, color) -> None:
        if color is None:
            self._color = None
        else:
            self._color = QColor(color)
        self.update()

    def resolved_color(self) -> QColor:
        if self._color is not None:
            return QColor(self._color)
        palette = palette_for(self._theme)
        if self._role == "accent":
            return QColor(palette.accent)
        return QColor(getattr(palette, f"chart_{self._role}"))

    def sizeHint(self) -> QSize:
        return QSize(160, 40)

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event):
        if len(self._values) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 3, -2, -3)
        if rect.width() <= 0 or rect.height() <= 0:
            painter.end()
            return

        minimum = min(self._values)
        maximum = max(self._values)
        span = maximum - minimum
        if span <= 0:
            span = 1.0

        step = rect.width() / (len(self._values) - 1)
        polygon = QPolygonF()
        for index, value in enumerate(self._values):
            x = rect.left() + index * step
            ratio = (value - minimum) / span
            y = rect.bottom() - ratio * rect.height()
            polygon.append(QPointF(x, y))

        pen = QPen(self.resolved_color())
        pen.setWidth(2)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPolyline(polygon)
        painter.end()

    def _update_accessible_description(self) -> None:
        if not self._values:
            self.setAccessibleDescription("No data")
            return
        self.setAccessibleDescription(
            f"Latest value {self._values[-1]:g} across {len(self._values)} samples"
        )
