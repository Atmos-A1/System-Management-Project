"""Theme resolution and application.

Windows is the primary target for this application.  The effective system
appearance is read from Qt's platform style hints
(``QStyleHints.colorScheme()``) when available.  A palette-lightness check
is used only as a fallback for platforms/Qt versions that report
``ColorScheme.Unknown``.

Theme application is deliberately simple and deterministic:

    tokens -> rendered QSS (cached per theme) -> QApplication.setStyleSheet()
                                              -> QApplication.setPalette()

Synchronising the palette as well as the stylesheet keeps native widgets
that ignore QSS (message boxes, file dialogs, tooltips, scroll bars) aligned
with the active appearance.  A ``theme_changed`` signal lets already-created
screens react without being rebuilt.

Live detection of an operating-system theme change while Panther is
running is intentionally out of scope for this phase.  The System option is
resolved whenever a theme is applied (application start, or a change in
Settings), which requires re-selection to pick up a later OS theme change.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .design_system import ColorPalette, palette_for, stylesheet_for

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"

VALID_THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


def _style_hint_theme(application: Optional[QApplication]) -> Optional[str]:
    """Return ``light``/``dark`` from Qt's platform style hints, if known."""

    if application is None:
        return None

    try:
        hints = application.styleHints()
    except Exception:
        return None

    if hints is None or not hasattr(hints, "colorScheme"):
        return None

    try:
        scheme = hints.colorScheme()
    except Exception:
        return None

    if scheme == Qt.ColorScheme.Dark:
        return THEME_DARK
    if scheme == Qt.ColorScheme.Light:
        return THEME_LIGHT
    return None


def _palette_is_dark(application: Optional[QApplication]) -> bool:
    """Fallback heuristic: treat a dark window colour as dark appearance."""

    if application is None:
        return False

    try:
        window_color = application.palette().window().color()
        return window_color.lightness() < 128
    except Exception:
        return False


def resolve_system_theme(application: Optional[QApplication] = None) -> str:
    """Resolve the effective operating-system appearance.

    Uses Qt's platform style hint first (the Windows-first path), then
    falls back to palette lightness.  The fallback defaults to light when
    neither signal is available.
    """

    hinted = _style_hint_theme(application)
    if hinted is not None:
        return hinted
    return THEME_DARK if _palette_is_dark(application) else THEME_LIGHT


def build_palette(colors: ColorPalette) -> QPalette:
    """Build a QPalette that mirrors the semantic colour tokens.

    This is what keeps native dialogs and unstyled widgets consistent with
    the QSS surface colours under both appearances.
    """

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors.background))
    palette.setColor(QPalette.WindowText, QColor(colors.text_primary))
    palette.setColor(QPalette.Base, QColor(colors.surface))
    palette.setColor(QPalette.AlternateBase, QColor(colors.surface_alt))
    palette.setColor(QPalette.Text, QColor(colors.text_primary))
    palette.setColor(QPalette.Button, QColor(colors.surface))
    palette.setColor(QPalette.ButtonText, QColor(colors.text_primary))
    palette.setColor(QPalette.BrightText, QColor(colors.on_accent))
    palette.setColor(QPalette.Highlight, QColor(colors.selected_bg))
    palette.setColor(QPalette.HighlightedText, QColor(colors.selected_text))
    palette.setColor(QPalette.ToolTipBase, QColor(colors.surface_elevated))
    palette.setColor(QPalette.ToolTipText, QColor(colors.text_primary))
    palette.setColor(QPalette.PlaceholderText, QColor(colors.text_secondary))
    palette.setColor(QPalette.Link, QColor(colors.accent))
    palette.setColor(QPalette.LinkVisited, QColor(colors.accent_pressed))

    disabled = QPalette.Disabled
    palette.setColor(disabled, QPalette.WindowText, QColor(colors.text_secondary))
    palette.setColor(disabled, QPalette.Text, QColor(colors.text_secondary))
    palette.setColor(disabled, QPalette.ButtonText, QColor(colors.text_secondary))
    palette.setColor(disabled, QPalette.Base, QColor(colors.surface_alt))
    return palette


class ThemeManager(QObject):
    """Resolve and apply the application-wide theme.

    The class doubles as a QObject so a single ``theme_changed`` signal can
    be shared by every screen without each screen polling for changes.
    """

    theme_changed = Signal(str)

    _instance: Optional["ThemeManager"] = None
    _current_theme = THEME_LIGHT

    @classmethod
    def instance(cls) -> "ThemeManager":
        """Return the process-wide ThemeManager used for signalling."""

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def current_theme(cls) -> str:
        """Return the last concrete appearance applied by the application."""

        return cls._current_theme

    @staticmethod
    def resolve_theme(
        theme_name: str, application: Optional[QApplication] = None
    ) -> str:
        """Return the concrete ``light``/``dark`` appearance for a name."""

        requested = str(theme_name or "").strip().lower()
        if requested == THEME_LIGHT:
            return THEME_LIGHT
        if requested == THEME_DARK:
            return THEME_DARK
        # ``system`` and any unrecognised value use the OS appearance.
        return resolve_system_theme(application)

    @classmethod
    def apply_theme(
        cls, application: Optional[QApplication], theme_name: str
    ) -> str:
        """Apply a theme to ``application`` and return the resolved theme.

        Passing ``None`` is a no-op for styling (useful in headless tests)
        but still resolves the effective name so callers can report what the
        System option selected.  Both the cached stylesheet and a matching
        QPalette are applied, then ``theme_changed`` is emitted.
        """

        resolved = cls.resolve_theme(theme_name, application)
        if application is not None:
            colors = palette_for(resolved)
            application.setPalette(build_palette(colors))
            application.setStyleSheet(stylesheet_for(resolved))
        cls._current_theme = resolved
        cls.instance().theme_changed.emit(resolved)
        return resolved
