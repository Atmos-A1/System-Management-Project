"""Tests for the authoritative design-token module."""

import re

import pytest

from panther.ui.design_system import (
    COLOR_PALETTES,
    DARK_COLORS,
    LIGHT_COLORS,
    RADIUS,
    SPACING,
    TYPOGRAPHY,
    build_stylesheet,
    clear_stylesheet_cache,
    palette_for,
    stylesheet_for,
)


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _color_fields(palette):
    return {
        name: value
        for name, value in vars(palette).items()
        if isinstance(value, str) and value.startswith("#")
    }


def test_light_and_dark_palettes_are_available():
    assert set(COLOR_PALETTES) == {"light", "dark"}
    assert COLOR_PALETTES["light"] is LIGHT_COLORS
    assert COLOR_PALETTES["dark"] is DARK_COLORS


@pytest.mark.parametrize("palette", [LIGHT_COLORS, DARK_COLORS])
def test_all_palette_colors_are_valid_hex_values(palette):
    colors = _color_fields(palette)
    assert colors, "palette should expose colour tokens"
    for name, value in colors.items():
        assert HEX_COLOR.match(value), f"{name} is not a valid hex colour: {value}"


def test_light_and_dark_palettes_are_distinct():
    assert LIGHT_COLORS.background != DARK_COLORS.background
    assert LIGHT_COLORS.surface != DARK_COLORS.surface
    assert LIGHT_COLORS.text_primary != DARK_COLORS.text_primary


def test_palette_for_known_and_unknown_names():
    assert palette_for("light") is LIGHT_COLORS
    assert palette_for("DARK") is DARK_COLORS
    # Unknown values fall back to light rather than silently returning None.
    assert palette_for("sepia") is LIGHT_COLORS


def test_spacing_scale_uses_four_pixel_grid():
    assert (SPACING.xs, SPACING.sm, SPACING.md, SPACING.lg, SPACING.xl) == (
        4,
        8,
        12,
        16,
        24,
    )


def test_typography_scale_matches_design_specification():
    assert TYPOGRAPHY.display_size == 32
    assert TYPOGRAPHY.display_weight == 700
    assert TYPOGRAPHY.heading_size == 24
    assert TYPOGRAPHY.subheading_size == 18
    assert TYPOGRAPHY.body_size == 13
    assert TYPOGRAPHY.caption_size == 11
    assert TYPOGRAPHY.metric_size == 34
    assert "Segoe UI" in TYPOGRAPHY.font_family


def test_radius_scale_provides_card_and_control_tokens():
    assert (RADIUS.sm, RADIUS.md, RADIUS.lg) == (6, 10, 12)


@pytest.mark.parametrize("palette", [LIGHT_COLORS, DARK_COLORS])
def test_palette_exposes_elevation_and_chart_roles(palette):
    for name in (
        "surface_elevated",
        "on_accent",
        "chart_cpu",
        "chart_memory",
        "chart_storage",
        "chart_battery",
        "chart_network",
    ):
        assert getattr(palette, name).startswith("#")


def test_approved_light_and_dark_canvas_tokens():
    assert LIGHT_COLORS.background.lower() == "#f5f7fa"
    assert DARK_COLORS.background.lower() == "#0b1220"
    assert DARK_COLORS.surface.lower() == "#111a2c"
    assert DARK_COLORS.surface_elevated.lower() == "#16213a"


def _relative_luminance(hex_color):
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def linear(channel):
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first, second):
    a, b = _relative_luminance(first), _relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("palette", [LIGHT_COLORS, DARK_COLORS])
def test_text_tokens_meet_wcag_contrast_on_their_surfaces(palette):
    for background in (palette.background, palette.surface, palette.surface_alt):
        assert _contrast(palette.text_primary, background) >= 4.5
        assert _contrast(palette.text_secondary, background) >= 4.5


def test_stylesheet_for_caches_one_rendered_string_per_theme():
    clear_stylesheet_cache()

    first = stylesheet_for("dark")
    second = stylesheet_for("DARK")

    assert first is second
    assert first == build_stylesheet(DARK_COLORS)
    # Unknown names resolve to the light palette, matching palette_for().
    assert stylesheet_for("sepia") == build_stylesheet(LIGHT_COLORS)

    clear_stylesheet_cache()
    assert stylesheet_for("dark") is not first


def test_stylesheet_is_built_from_palette_tokens():
    stylesheet = build_stylesheet(LIGHT_COLORS)

    assert LIGHT_COLORS.background in stylesheet
    assert LIGHT_COLORS.surface in stylesheet
    assert LIGHT_COLORS.accent in stylesheet
    assert LIGHT_COLORS.text_primary in stylesheet
    assert "QListWidget#sidebar" in stylesheet
    assert "Segoe UI" in stylesheet
    assert "$" not in stylesheet


def test_dark_stylesheet_differs_and_uses_dark_tokens():
    light = build_stylesheet(LIGHT_COLORS)
    dark = build_stylesheet(DARK_COLORS)

    assert light != dark
    assert DARK_COLORS.background in dark
    assert DARK_COLORS.accent in dark
    assert LIGHT_COLORS.background not in dark


def test_stylesheet_covers_reusable_component_selectors():
    stylesheet = build_stylesheet(LIGHT_COLORS)

    for selector in (
        "QFrame#metricCard",
        "QLabel#cardTitle",
        "QLabel#cardValue",
        "QLabel#cardDetail",
        'QProgressBar[level="normal"]',
        'QProgressBar[level="warning"]',
        'QProgressBar[level="critical"]',
        "QFrame#statusBanner",
        'QFrame#statusBanner[status="error"]',
        "QLabel#statusBannerState",
        'QPushButton[variant="secondary"]',
        'QPushButton[variant="destructive"]',
        "QLabel#pageTitle",
        "QLabel#pageSubtitle",
        "QWidget#pageScaffold",
        "QLabel#scanStatus",
        "QFrame#sectionCard",
        "QLabel#sectionTitle",
        "QLabel#sectionSubtitle",
    ):
        assert selector in stylesheet, selector
