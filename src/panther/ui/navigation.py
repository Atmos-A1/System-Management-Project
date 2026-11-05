"""Navigation definitions for the sidebar.

``NAV_ITEMS`` is a list of ``(name, icon_key)`` tuples.  Icon keys are
resolved to Qt standard icons instead of shipping platform-specific image
assets; this keeps the shell dependency-free and consistent on Windows.
"""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

# Order matters – used by ``MainWindow`` to build the sidebar.
# Per PRD section 6.2: Dashboard, Processes, Storage, Battery, Startup Apps,
# Applications, Recommendations, Activity History and Settings.
NAV_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Processes", "processes"),
    ("Adaptive Control", "adaptive"),
    ("Storage", "storage"),
    ("Battery", "battery"),
    ("Startup Apps", "startup"),
    ("Applications", "applications"),
    ("Recommendations", "recommendations"),
    ("Activity History", "history"),
    ("Settings", "settings"),
]

_ICON_STANDARD_PIXMAPS = {
    "dashboard": QStyle.StandardPixmap.SP_DesktopIcon,
    "processes": QStyle.StandardPixmap.SP_FileDialogListView,
    "adaptive": QStyle.StandardPixmap.SP_BrowserReload,
    "storage": QStyle.StandardPixmap.SP_DriveHDIcon,
    "battery": QStyle.StandardPixmap.SP_ComputerIcon,
    "startup": QStyle.StandardPixmap.SP_FileDialogStart,
    "applications": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "recommendations": QStyle.StandardPixmap.SP_MessageBoxInformation,
    "history": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
}


def nav_index(name: str) -> int:
    """Return the sidebar index for a navigation label.

    Raises ``KeyError`` for unknown labels so callers cannot silently
    navigate to an unrelated screen.
    """

    for index, (item_name, _icon_key) in enumerate(NAV_ITEMS):
        if item_name == name:
            return index
    raise KeyError(f"Unknown navigation item: {name}")


def nav_icon(icon_key: str) -> QIcon:
    """Resolve an icon key to a non-null Qt standard icon where possible."""

    application = QApplication.instance()
    if application is None:
        return QIcon()

    standard = _ICON_STANDARD_PIXMAPS.get(
        str(icon_key), QStyle.StandardPixmap.SP_FileIcon
    )
    return application.style().standardIcon(standard)
