"""Loading panel with an indeterminate progress indicator."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout


class LoadingState(QFrame):
    """Explicit "work in progress" surface for screens and tables."""

    def __init__(self, message: str = "Loading…", parent=None):
        super().__init__(parent)
        self.setObjectName("loadingState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.message_label = QLabel()
        self.message_label.setObjectName("stateTitle")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setObjectName("stateProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setAccessibleName("Progress")
        self.progress.setAccessibleDescription(str(message))

        layout.addStretch()
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress)
        layout.addStretch()

        self.set_message(message)
        self.start()

    @property
    def is_running(self) -> bool:
        return self.progress.minimum() == 0 and self.progress.maximum() == 0

    def set_message(self, message: str) -> None:
        text = str(message)
        self.message_label.setText(text)
        self.progress.setAccessibleDescription(text)
        self.setAccessibleName(text)

    def start(self) -> None:
        self.progress.setRange(0, 0)

    def stop(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
