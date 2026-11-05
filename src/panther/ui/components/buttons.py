"""Token-styled button variants."""

from PySide6.QtWidgets import QPushButton


class _VariantButton(QPushButton):
    variant = "primary"

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", self.variant)
        if self.variant == "secondary":
            self.setProperty("secondary", True)
        elif self.variant == "destructive":
            self.setProperty("destructive", True)


class PrimaryButton(_VariantButton):
    """Filled accent button for the main action."""

    variant = "primary"


class SecondaryButton(_VariantButton):
    """Outlined/neutral button for secondary or cancel actions."""

    variant = "secondary"


class DestructiveButton(_VariantButton):
    """Red button reserved for destructive actions."""

    variant = "destructive"
