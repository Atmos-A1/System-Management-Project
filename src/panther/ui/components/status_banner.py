"""Status banner for loading, empty, success, warning and error states."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class StatusBanner(QFrame):
    """A text-labelled status message; colour is never the only signal."""

    STATES = {
        "info": "Info",
        "success": "Success",
        "warning": "Warning",
        "error": "Error",
        "loading": "Loading",
    }

    def __init__(self, message: str = "", state: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("statusBanner")
        self._state = "info"
        self._message = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.state_label = QLabel()
        self.state_label.setObjectName("statusBannerState")
        self.message_label = QLabel()
        self.message_label.setObjectName("statusBannerText")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(self.state_label, 0)
        layout.addWidget(self.message_label, 1)

        self.set_state(state, message)
        if not message and state != "loading":
            self.hide()

    @property
    def state(self) -> str:
        return self._state

    @property
    def message(self) -> str:
        return self._message

    def set_state(self, state: str, message: str = None) -> None:
        normalized = str(state).lower()
        if normalized not in self.STATES:
            raise ValueError(f"Unknown status banner state: {state}")

        self._state = normalized
        if message is not None:
            self._message = str(message)

        self.setProperty("status", normalized)
        self.state_label.setProperty("status", normalized)
        self.state_label.setText(self.STATES[normalized])
        self.message_label.setText(self._message)
        self.state_label.setAccessibleName(f"{self.STATES[normalized]} status")
        self.message_label.setAccessibleName(self._message)

        self._repolish()
        if self._message or normalized == "loading":
            self.show()
        else:
            self.hide()

    def clear(self) -> None:
        self._message = ""
        self.message_label.setText("")
        self.hide()

    def _repolish(self) -> None:
        for widget in (self, self.state_label, self.message_label):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
