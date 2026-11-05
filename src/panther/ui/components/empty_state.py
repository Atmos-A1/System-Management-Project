"""Empty and unsupported state panel.

Colour is never the only signal: the panel always carries a title, an
optional explanation and an optional action, and the ``variant`` property is
exposed for styling and for tests.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

VARIANTS = ("empty", "unsupported")


class EmptyState(QFrame):
    """A centred explanation for a screen or surface with nothing to show."""

    action_triggered = Signal()

    def __init__(
        self,
        title: str = "",
        description: str = "",
        action_text: str = "",
        variant: str = "empty",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self._variant = "empty"
        self.action_button = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch()

        self.title_label = QLabel()
        self.title_label.setObjectName("stateTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)

        self.description_label = QLabel()
        self.description_label.setObjectName("stateDescription")
        self.description_label.setAlignment(Qt.AlignCenter)
        self.description_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        self._layout = layout
        layout.addStretch()

        self.set_title(title)
        self.set_description(description)
        self.set_variant(variant)
        if action_text:
            self.set_action_text(action_text)

    @property
    def variant(self) -> str:
        return self._variant

    def set_variant(self, variant: str) -> None:
        normalized = str(variant).lower()
        if normalized not in VARIANTS:
            raise ValueError(f"Unknown empty-state variant: {variant}")
        self._variant = normalized
        self.setProperty("variant", normalized)
        self._repolish()

    def set_title(self, title: str) -> None:
        text = str(title)
        self.title_label.setText(text)
        self.title_label.setVisible(bool(text))
        self.setAccessibleName(text)

    def set_description(self, description: str) -> None:
        text = str(description)
        self.description_label.setText(text)
        self.description_label.setVisible(bool(text))

    def set_action_text(self, action_text: str) -> None:
        text = str(action_text)
        if not text:
            if self.action_button is not None:
                self.action_button.setVisible(False)
            return
        if self.action_button is None:
            self.action_button = QPushButton()
            self.action_button.setObjectName("stateAction")
            self.action_button.setProperty("secondary", True)
            self.action_button.setCursor(Qt.PointingHandCursor)
            self.action_button.setSizePolicy(
                QSizePolicy.Fixed, QSizePolicy.Fixed
            )
            self.action_button.clicked.connect(self.action_triggered.emit)
            # Insert before the trailing stretch, centred so the action stays
            # grouped with the text rather than stretching across the panel.
            self._layout.insertWidget(
                self._layout.count() - 1,
                self.action_button,
                0,
                Qt.AlignHCenter,
            )
        self.action_button.setText(text)
        self.action_button.setAccessibleName(text)
        self.action_button.setVisible(True)

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()
