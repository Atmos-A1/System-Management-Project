"""Authoritative design tokens for Panther System Intelligence.

This module is the single source of truth for colours, typography, spacing
and radii.  It deliberately builds a stylesheet from tokens instead of
hard-coding a second theme inside individual screens.  Screens may still
keep component-specific styling where that styling expresses layout or
behaviour rather than theme colours.

The palette values follow the approved "Calm Precision" design direction.
Only :func:`build_stylesheet` should turn tokens into QSS; consumers should
import the token objects, :func:`palette_for` or :func:`stylesheet_for`.
"""

from dataclasses import asdict, dataclass
from string import Template
from typing import Dict

# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColorPalette:
    """Semantic colour tokens for one appearance."""

    background: str
    surface: str
    surface_alt: str
    surface_elevated: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    destructive: str
    destructive_hover: str
    success: str
    warning: str
    critical: str
    selected_bg: str
    selected_text: str
    sidebar_bg: str
    sidebar_text: str
    sidebar_hover: str
    # Data-visualisation roles, bound to resource type rather than to
    # individual screens.
    chart_cpu: str
    chart_memory: str
    chart_storage: str
    chart_battery: str
    chart_network: str


LIGHT_COLORS = ColorPalette(
    background="#f5f7fa",
    surface="#ffffff",
    surface_alt="#f8fafc",
    surface_elevated="#ffffff",
    border="#e2e8f0",
    border_strong="#cbd5e1",
    text_primary="#0f172a",
    text_secondary="#55657c",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_pressed="#1e40af",
    on_accent="#ffffff",
    destructive="#dc2626",
    destructive_hover="#b91c1c",
    success="#16a34a",
    warning="#d97706",
    critical="#dc2626",
    selected_bg="#dbeafe",
    selected_text="#0f172a",
    sidebar_bg="#0b1220",
    sidebar_text="#e6edf7",
    sidebar_hover="#16213a",
    chart_cpu="#2563eb",
    chart_memory="#7c3aed",
    chart_storage="#d97706",
    chart_battery="#16a34a",
    chart_network="#0891b2",
)

DARK_COLORS = ColorPalette(
    background="#0b1220",
    surface="#111a2c",
    surface_alt="#0e1726",
    surface_elevated="#16213a",
    border="#24324a",
    border_strong="#334155",
    text_primary="#e6edf7",
    text_secondary="#94a3b8",
    accent="#60a5fa",
    accent_hover="#93c5fd",
    accent_pressed="#3b82f6",
    on_accent="#0b1220",
    destructive="#dc2626",
    destructive_hover="#b91c1c",
    success="#4ade80",
    warning="#fbbf24",
    critical="#f87171",
    selected_bg="#1e3a8a",
    selected_text="#e6edf7",
    sidebar_bg="#070d18",
    sidebar_text="#cbd5e1",
    sidebar_hover="#16213a",
    chart_cpu="#60a5fa",
    chart_memory="#a78bfa",
    chart_storage="#fbbf24",
    chart_battery="#4ade80",
    chart_network="#22d3ee",
)

COLOR_PALETTES = {
    "light": LIGHT_COLORS,
    "dark": DARK_COLORS,
}


def palette_for(theme_name: str) -> ColorPalette:
    """Return the palette for ``theme_name``.

    Unknown names fall back to the light palette so callers never receive
    ``None``; theme validation happens in :mod:`panther.ui.theme`.
    """

    return COLOR_PALETTES.get(str(theme_name).lower(), LIGHT_COLORS)


# ---------------------------------------------------------------------------
# Typography tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Typography:
    """Type scale.  Segoe UI is the Windows-first family with fallbacks."""

    font_family: str = (
        '"Segoe UI Variable", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'
    )
    display_size: int = 32
    display_weight: int = 700
    heading_size: int = 24
    heading_weight: int = 650
    subheading_size: int = 18
    subheading_weight: int = 600
    body_size: int = 13
    body_weight: int = 400
    caption_size: int = 11
    caption_weight: int = 400
    metric_size: int = 34
    metric_weight: int = 700
    metric_caption_size: int = 11
    metric_caption_weight: int = 400


TYPOGRAPHY = Typography()


# ---------------------------------------------------------------------------
# Spacing and radius tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Spacing:
    """4px spacing grid."""

    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24


@dataclass(frozen=True)
class Radius:
    """Corner radii: controls, cards and panels."""

    sm: int = 6
    md: int = 10
    lg: int = 12


SPACING = Spacing()
RADIUS = Radius()


# ---------------------------------------------------------------------------
# Stylesheet builder
# ---------------------------------------------------------------------------

# ``$name`` placeholders are filled from the token dataclasses.  This keeps
# every colour in the stylesheet traceable to exactly one token.  Two braces
# are not used here because Template substitution does not treat them
# specially, so normal QSS braces can be written directly.
_STYLESHEET_TEMPLATE = Template(
    """
* {
    font-family: $font_family;
}

QMainWindow, QDialog {
    background-color: $background;
    color: $text_primary;
}

QWidget#centralWidget, QStackedWidget {
    background-color: $background;
}

QWidget#settingsScreen {
    background-color: $background;
}

QWidget#pageScaffold {
    background-color: $background;
}

QWidget#pageContent, QWidget#pageHeader {
    background-color: transparent;
}

/* Base label treatment.  Keeps text legible and prevents the accidental
   background strips caused by broad QWidget background rules. */
QLabel {
    color: $text_primary;
    background-color: transparent;
}

/* Sidebar is scoped by object name so other list widgets are unaffected. */
QListWidget#sidebar {
    background-color: $sidebar_bg;
    color: $sidebar_text;
    border: none;
    font-size: ${body_size}px;
    padding: ${sm}px 0px;
}

QListWidget#sidebar::item {
    padding: 11px 16px;
    border: none;
    margin: 2px ${sm}px;
    border-radius: ${radius_sm}px;
}

QListWidget#sidebar::item:selected {
    background-color: $accent;
    color: $on_accent;
}

QListWidget#sidebar::item:hover:!selected {
    background-color: $sidebar_hover;
    color: $sidebar_text;
}

QListWidget#detailList {
    background-color: $surface;
    color: $text_primary;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
    padding: ${sm}px;
    font-size: ${body_size}px;
}

QListWidget#detailList::item {
    padding: ${sm}px;
    border-radius: ${radius_sm}px;
}

QListWidget#detailList::item:selected {
    background-color: $selected_bg;
    color: $selected_text;
}

QListWidget#detailList::item:hover:!selected {
    background-color: $surface_alt;
}

QLabel#pageTitle {
    font-size: ${heading_size}px;
    font-weight: ${heading_weight};
    color: $text_primary;
}

QLabel#pageSubtitle {
    font-size: ${body_size}px;
    color: $text_secondary;
}

QLabel[role="secondary"] {
    color: $text_secondary;
}

QLabel[role="caption"] {
    font-size: ${caption_size}px;
    color: $text_secondary;
}

QLabel[role="emphasis"] {
    font-weight: ${subheading_weight};
    color: $text_primary;
}

QFrame#statusBanner {
    background-color: $surface_alt;
    border: 1px solid $border;
    border-left: ${xs}px solid $accent;
    border-radius: ${radius_sm}px;
}

QFrame#statusBanner[status="success"] {
    border-left: ${xs}px solid $success;
}

QFrame#statusBanner[status="warning"] {
    border-left: ${xs}px solid $warning;
}

QFrame#statusBanner[status="error"] {
    border-left: ${xs}px solid $critical;
}

QFrame#statusBanner[status="loading"] {
    border-left: ${xs}px solid $accent;
}

QLabel#statusBannerState {
    font-weight: 600;
    color: $text_primary;
    background-color: transparent;
}

QLabel#statusBannerState[status="success"] {
    color: $success;
}

QLabel#statusBannerState[status="warning"] {
    color: $warning;
}

QLabel#statusBannerState[status="error"] {
    color: $critical;
}

QLabel#statusBannerState[status="loading"] {
    color: $accent;
}

QLabel#statusBannerText {
    color: $text_primary;
    background-color: transparent;
}

QFrame#sectionCard, QFrame#card, QFrame#recCard {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}

QWidget#sectionCardHeader, QWidget#sectionCardBody {
    background-color: transparent;
}

QLabel#sectionTitle {
    font-size: ${subheading_size}px;
    font-weight: ${subheading_weight};
    color: $text_primary;
    background-color: transparent;
}

QLabel#sectionSubtitle {
    font-size: ${caption_size}px;
    color: $text_secondary;
    background-color: transparent;
}

/* Empty, loading and error state panels. */
QFrame#emptyState, QFrame#loadingState, QFrame#errorState {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}

QFrame#emptyState[variant="unsupported"] {
    border-style: dashed;
}

QFrame#errorState {
    border-left: ${xs}px solid $critical;
}

QLabel#stateTitle {
    font-size: ${subheading_size}px;
    font-weight: ${subheading_weight};
    color: $text_primary;
    background-color: transparent;
}

QLabel#stateDescription {
    font-size: ${body_size}px;
    color: $text_secondary;
    background-color: transparent;
}

QFrame#tableStateOverlay {
    background-color: $background;
    border: none;
}

/* Status badges: text stays on a high-contrast surface, colour is the
   supplementary border signal. */
QLabel#badge {
    background-color: $surface_alt;
    color: $text_primary;
    border: 1px solid $border_strong;
    border-radius: ${radius_lg}px;
    padding: 2px 10px;
    font-size: ${caption_size}px;
    font-weight: 600;
}

QLabel#badge[status="info"] {
    border-color: $accent;
}

QLabel#badge[status="success"] {
    border-color: $success;
}

QLabel#badge[status="warning"] {
    border-color: $warning;
}

QLabel#badge[status="critical"] {
    border-color: $critical;
}

QFrame#toolbar, QFrame#filterBar {
    background-color: transparent;
    border: none;
}

QFrame#filterBar {
    border-bottom: 1px solid $border;
}

QLabel#keyValueLabel {
    color: $text_secondary;
    background-color: transparent;
}

QLabel#keyValueValue {
    color: $text_primary;
    font-weight: 600;
    background-color: transparent;
}

QGroupBox {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
    margin-top: ${md}px;
    padding: ${lg}px;
    font-weight: ${subheading_weight};
    color: $text_primary;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: $surface;
    color: $text_primary;
    border: 1px solid $border_strong;
    padding: 6px 8px;
    border-radius: ${radius_sm}px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid $accent;
}

QComboBox QAbstractItemView {
    background-color: $surface_elevated;
    color: $text_primary;
    border: 1px solid $border;
    selection-background-color: $selected_bg;
    selection-color: $selected_text;
}

QPushButton {
    background-color: $accent;
    color: $on_accent;
    border: none;
    padding: ${sm}px 14px;
    border-radius: ${radius_sm}px;
}

QPushButton:hover {
    background-color: $accent_hover;
}

QPushButton:pressed {
    background-color: $accent_pressed;
}

QPushButton:focus {
    border: 2px solid $on_accent;
}

QPushButton:disabled {
    background-color: $border;
    color: $text_secondary;
}

QPushButton[variant="secondary"], QPushButton[secondary="true"] {
    background-color: $surface_alt;
    color: $text_primary;
    border: 1px solid $border_strong;
}

QPushButton[variant="destructive"], QPushButton[destructive="true"] {
    background-color: $destructive;
    color: $on_accent;
}

QPushButton[variant="destructive"]:hover, QPushButton[destructive="true"]:hover {
    background-color: $destructive_hover;
}

QCheckBox {
    color: $text_primary;
}

QCheckBox:disabled {
    color: $text_secondary;
}

QTableView, QTableWidget, QTextEdit, QPlainTextEdit {
    background-color: $surface;
    alternate-background-color: $surface_alt;
    color: $text_primary;
    border: 1px solid $border;
    gridline-color: $border;
    selection-background-color: $selected_bg;
    selection-color: $selected_text;
}

QHeaderView {
    background-color: $surface_alt;
}

QHeaderView::section {
    background-color: $surface_alt;
    color: $text_primary;
    border: 1px solid $border;
    padding: 6px;
    font-weight: 600;
}

QTabWidget::pane {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: ${radius_sm}px;
}

QTabBar::tab {
    background-color: $background;
    color: $text_secondary;
    padding: ${sm}px ${lg}px;
    margin-right: ${xs}px;
    border-top-left-radius: ${radius_sm}px;
    border-top-right-radius: ${radius_sm}px;
}

QTabBar::tab:selected {
    background-color: $surface;
    color: $text_primary;
    border: 1px solid $border;
    border-bottom: none;
}

QProgressBar {
    border: none;
    background-color: $surface_alt;
    border-radius: ${xs}px;
    color: $text_primary;
    text-align: center;
}

QProgressBar::chunk {
    background-color: $accent;
    border-radius: ${xs}px;
}

QProgressBar[level="normal"]::chunk {
    background-color: $success;
}

QProgressBar[level="warning"]::chunk {
    background-color: $warning;
}

QProgressBar[level="critical"]::chunk {
    background-color: $critical;
}

QProgressBar[level="accent"]::chunk {
    background-color: $accent;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

/* Keep scrolled content on the page canvas rather than the Base colour. */
QScrollArea > QWidget {
    background-color: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: ${radius_sm}px;
    min-height: 24px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: $border_strong;
    border-radius: ${radius_sm}px;
    min-width: 24px;
}

QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSplitter::handle {
    background-color: $border;
}

QFrame#metricCard, QFrame#card, QFrame#recCard {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}

QLabel#cardTitle {
    font-size: ${body_size}px;
    font-weight: 600;
    color: $text_primary;
    background-color: transparent;
}

QLabel#cardValue {
    font-size: ${metric_size}px;
    font-weight: ${metric_weight};
    color: $accent;
    background-color: transparent;
}

QLabel#cardValue[compact="true"] {
    font-size: ${subheading_size}px;
}

QLabel#cardDetail {
    font-size: ${metric_caption_size}px;
    color: $text_secondary;
    background-color: transparent;
}

QWidget#scanProgress {
    background-color: transparent;
}

QLabel#scanStatus {
    font-size: ${caption_size}px;
    color: $text_secondary;
    background-color: transparent;
}

QToolTip {
    background-color: $surface_elevated;
    color: $text_primary;
    border: 1px solid $border;
}
"""
)


def build_stylesheet(
    colors: ColorPalette,
    typography: Typography = TYPOGRAPHY,
    spacing: Spacing = SPACING,
    radius: Radius = RADIUS,
) -> str:
    """Build the application stylesheet from design tokens.

    The returned stylesheet covers shared chrome and common controls.  It
    does not attempt to replace component-specific layout styling.
    """

    values = {}
    values.update(asdict(colors))
    values.update(asdict(typography))
    values.update(asdict(spacing))
    values.update({f"radius_{name}": value for name, value in asdict(radius).items()})
    return _STYLESHEET_TEMPLATE.substitute(values)


# Rendered stylesheets are cached per theme.  Rendering is deterministic and
# cheap, but caching keeps theme switches free of repeated string building and
# gives the shell one object to hand to QApplication.
_STYLESHEET_CACHE: Dict[str, str] = {}


def stylesheet_for(theme_name: str) -> str:
    """Return the cached application stylesheet for ``theme_name``."""

    key = str(theme_name).lower()
    cached = _STYLESHEET_CACHE.get(key)
    if cached is None:
        cached = build_stylesheet(palette_for(key))
        _STYLESHEET_CACHE[key] = cached
    return cached


def clear_stylesheet_cache() -> None:
    """Drop cached stylesheets.  Used by tests and token-change tooling."""

    _STYLESHEET_CACHE.clear()
