#!/usr/bin/env python3
"""Phase 1 design-system pilot: screenshot and rendered-contrast validation.

Renders the Settings pilot inside the real application shell at the three
acceptance sizes in both appearances, saves the screenshots and measures the
*rendered* contrast ratio of representative text against the surface it is
actually drawn on (rather than comparing token values).

Usage:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python tools/ui_phase1_capture.py

Environment:
    PHASE1_SHOT_DIR   output directory (default /tmp/opencode/phase1-shots)
    QT_SCALE_FACTOR   set by the caller to exercise 150% scaling

Exit code is non-zero when any measured ratio falls below its threshold or a
measured widget falls outside the window bounds.
"""

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from panther.config import config  # noqa: E402
from panther.ui.components import SectionCard  # noqa: E402
from panther.ui.main_window import MainWindow  # noqa: E402
from panther.ui.navigation import nav_index  # noqa: E402
from panther.ui.theme import ThemeManager  # noqa: E402

SIZES = ((1240, 820), (1000, 700), (900, 600))
OUT_DIR = os.environ.get("PHASE1_SHOT_DIR", "/tmp/opencode/phase1-shots")
LARGE_TEXT_RATIO = 3.0
BODY_TEXT_RATIO = 4.5


def relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def contrast_ratio(first: QColor, second: QColor) -> float:
    a = relative_luminance(first)
    b = relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def dominant_color(image) -> QColor:
    counts = {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            key = (color.red(), color.green(), color.blue())
            counts[key] = counts.get(key, 0) + 1
    key = max(counts, key=counts.get)
    return QColor(*key)


def measure_region(image, rect: QRect):
    """Return (best_ratio, background, foreground) for a rendered region."""

    rect = rect.intersected(image.rect())
    if rect.width() < 2 or rect.height() < 2:
        return 1.0, QColor("black"), QColor("white")

    region = image.copy(rect)
    background = dominant_color(region)
    best_ratio = 1.0
    best_color = background
    for y in range(region.height()):
        for x in range(region.width()):
            color = region.pixelColor(x, y)
            ratio = contrast_ratio(color, background)
            if ratio > best_ratio:
                best_ratio = ratio
                best_color = color
    return best_ratio, background, best_color


def widget_rect(window, widget) -> QRect:
    top_left = widget.mapTo(window, QPoint(0, 0))
    return QRect(top_left, widget.size())


def capture(app, theme_name: str, width: int, height: int, scale: str):
    config.theme = theme_name
    window = MainWindow()
    window.resize(width, height)
    window.show()
    app.processEvents()
    app.processEvents()

    row = nav_index("Settings")
    window.sidebar.setCurrentRow(row)
    app.processEvents()
    app.processEvents()

    screen = window._screen_widgets.get(row)
    if screen is None:
        raise RuntimeError("Settings pilot screen was not constructed")

    image = window.grab().toImage()
    prefix = f"{theme_name}-{width}x{height}-scale{scale}"
    path = os.path.join(OUT_DIR, f"{prefix}.png")
    image.save(path)

    cards = screen.findChildren(SectionCard)
    card = cards[0] if cards else None
    descriptions = [
        w
        for w in card.findChildren(type(screen.theme_info))
        if w.property("role") == "secondary"
    ] if card else []

    targets = [
        ("page_title", screen.scaffold.header.title_label, LARGE_TEXT_RATIO),
        ("page_subtitle", screen.scaffold.header.subtitle_label, BODY_TEXT_RATIO),
        ("section_title", card.title_label if card else None, BODY_TEXT_RATIO),
        ("section_subtitle", card.subtitle_label if card else None, BODY_TEXT_RATIO),
        (
            "secondary_body",
            descriptions[0] if descriptions else screen.theme_info,
            BODY_TEXT_RATIO,
        ),
    ]

    results = []
    window_rect = QRect(0, 0, image.width(), image.height())
    for name, widget, threshold in targets:
        if widget is None or widget.isHidden() or not widget.text():
            continue
        rect = widget_rect(window, widget)
        scaled = QRect(
            rect.x() * image.width() // max(window.width(), 1),
            rect.y() * image.height() // max(window.height(), 1),
            max(rect.width() * image.width() // max(window.width(), 1), 1),
            max(rect.height() * image.height() // max(window.height(), 1), 1),
        )
        ratio, background, foreground = measure_region(image, scaled)
        inside = window_rect.contains(scaled)
        results.append(
            {
                "target": name,
                "text": widget.text()[:48],
                "rect": [scaled.x(), scaled.y(), scaled.width(), scaled.height()],
                "inside_window": inside,
                "background": background.name(),
                "foreground": foreground.name(),
                "ratio": round(ratio, 2),
                "required": threshold,
                "pass": ratio >= threshold and inside,
            }
        )

    window.close()
    app.processEvents()
    return {"screenshot": path, "theme": theme_name, "size": [width, height], "checks": results}


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    app = QApplication.instance() or QApplication(sys.argv)

    reports = []
    for theme_name in ("light", "dark"):
        for width, height in SIZES:
            reports.append(capture(app, theme_name, width, height, scale))

    failures = []
    for report in reports:
        for check in report["checks"]:
            if not check["pass"]:
                failures.append(
                    f"{report['screenshot']} :: {check['target']} "
                    f"ratio={check['ratio']} required={check['required']} "
                    f"inside={check['inside_window']}"
                )

    summary = {
        "scale_factor": scale,
        "captures": len(reports),
        "checks": sum(len(r["checks"]) for r in reports),
        "failures": failures,
        "reports": reports,
    }
    with open(os.path.join(OUT_DIR, f"summary-scale{scale}.json"), "w") as handle:
        json.dump(summary, handle, indent=2)

    for report in reports:
        print(report["screenshot"])
        for check in report["checks"]:
            status = "PASS" if check["pass"] else "FAIL"
            print(
                f"  [{status}] {check['target']:<16} ratio={check['ratio']:.2f} "
                f"(>= {check['required']}) bg={check['background']} "
                f"fg={check['foreground']}"
            )

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print("  " + failure)
        return 1
    print(f"\nAll {summary['checks']} rendered-contrast checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
