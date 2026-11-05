"""Titled surface used to group related settings and detail rows."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SectionCard(QFrame):
    """A consistent surface with an optional title and subtitle.

    The header collapses when no title is supplied so the card can also be
    used as a plain content panel.
    """

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("sectionCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.header = QWidget()
        self.header.setObjectName("sectionCardHeader")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        self.title_label = QLabel()
        self.title_label.setObjectName("sectionTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("sectionSubtitle")
        self.subtitle_label.setWordWrap(True)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)

        self.body = QWidget()
        self.body.setObjectName("sectionCardBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)

        layout.addWidget(self.header)
        layout.addWidget(self.body)

        self.set_title(title)
        self.set_subtitle(subtitle)

    def set_title(self, title: str) -> None:
        text = str(title)
        self.title_label.setText(text)
        self.title_label.setAccessibleName(text)
        self.header.setVisible(bool(text) or bool(self.subtitle_label.text()))

    def set_subtitle(self, subtitle: str) -> None:
        text = str(subtitle)
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))
        self.header.setVisible(bool(text) or bool(self.title_label.text()))

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body_layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body_layout.addLayout(layout, stretch)
