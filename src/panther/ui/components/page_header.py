"""Standard page title and subtitle block."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    """Title and optional subtitle used at the top of a screen."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

        self.subtitle_label.setVisible(bool(subtitle))

    def set_title(self, title: str) -> None:
        self.title_label.setText(str(title))

    def set_subtitle(self, subtitle: str) -> None:
        text = str(subtitle)
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))
