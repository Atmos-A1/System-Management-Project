"""Progress, status text and cancellation for long-running scans."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from .buttons import SecondaryButton


class ScanProgress(QWidget):
    """Reusable scan progress row with explicit cancellation state."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scanProgress")
        self._running = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setObjectName("scanStatus")
        self.progress = QProgressBar()
        self.progress.setObjectName("scanProgressBar")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setRange(0, 0)
        self.cancel_button = SecondaryButton("Cancel")

        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.progress, 2)
        layout.addWidget(self.cancel_button)

        self.cancel_button.clicked.connect(self._on_cancel)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, message: str = "Scanning…", maximum: int = 0) -> None:
        self._running = True
        self.status_label.setText(str(message))
        self.progress.setRange(0, max(0, int(maximum)))
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.show()

    def set_progress(self, value: int, maximum: int = None) -> None:
        if maximum is not None:
            maximum = max(0, int(maximum))
            self.progress.setRange(0, maximum)
        if self.progress.maximum() == 0:
            self.progress.setValue(0)
            return
        bounded = max(0, min(self.progress.maximum(), int(value)))
        self.progress.setValue(bounded)

    def set_status(self, message: str) -> None:
        self.status_label.setText(str(message))

    def finish(self, message: str = "Scan complete") -> None:
        self._running = False
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText(str(message))
        self.cancel_button.setEnabled(False)

    def reset(self) -> None:
        self._running = False
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.status_label.setText("")
        self.cancel_button.setEnabled(True)

    def _on_cancel(self) -> None:
        if not self._running:
            return
        self._running = False
        self.status_label.setText("Cancelling…")
        self.cancel_button.setEnabled(False)
        self.cancel_requested.emit()
