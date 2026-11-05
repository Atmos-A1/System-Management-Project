"""Compact status indicator for categories, scope and impact."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy

STATUSES = ("neutral", "info", "success", "warning", "critical")


class Badge(QLabel):
    """A short label whose severity is exposed as a dynamic property.

    The status is included in the accessible name so the indicator never
    relies on colour alone.
    """

    def __init__(self, text: str = "", status: str = "neutral", parent=None):
        super().__init__(str(text), parent)
        self.setObjectName("badge")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAlignment(Qt.AlignCenter)
        # A status indicator should hug its text rather than stretch to fill
        # a vertical layout.
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._status = "neutral"
        self.set_status(status)

    @property
    def status(self) -> str:
        return self._status

    def set_status(self, status: str) -> None:
        normalized = str(status).lower()
        if normalized not in STATUSES:
            raise ValueError(f"Unknown badge status: {status}")
        self._status = normalized
        self.setProperty("status", normalized)
        self._update_accessible_name()
        self._repolish()

    def set_text(self, text: str) -> None:
        self.setText(str(text))
        self._update_accessible_name()

    def _update_accessible_name(self) -> None:
        self.setAccessibleName(f"{self.text()}, {self._status}")

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


# ``StatusPill`` is the name used in the design plan for the same primitive.
StatusPill = Badge
