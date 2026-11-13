"""Theme colors must be readable: WCAG AA needs a contrast ratio of 4.5:1 for body text.

The test reads the color tokens straight from app.css, so changing a token to a
color that is too faint fails here instead of being noticed in the browser.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent / "app/static/css/app.css").read_text("utf-8")

BACKGROUNDS = ["--bg", "--surface", "--raised"]
TEXT_COLORS = ["--text", "--text-2", "--muted", "--accent", "--ok", "--fail", "--warn", "--info",
               "--neutral"]
AA_BODY_TEXT = 4.5


def tokens(selector):
    """Color tokens declared in one CSS block, e.g. {'--bg': '#0E0F11', ...}."""
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.DOTALL).group(1)
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})\b", block))


def luminance(hex_color):
    """Relative luminance as defined by WCAG 2."""
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(color_a, color_b):
    lighter, darker = sorted([luminance(color_a), luminance(color_b)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


DARK = tokens(":root")
LIGHT = {**DARK, **tokens('[data-theme="light"]')}  # light overrides the dark defaults


def test_contrast_formula_matches_known_values():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("theme_name, theme", [("dark", DARK), ("light", LIGHT)])
def test_text_colors_meet_wcag_aa_on_every_background(theme_name, theme):
    too_faint = [
        f"{theme_name}: {text} on {background} = {contrast(theme[text], theme[background]):.2f}"
        for text in TEXT_COLORS
        for background in BACKGROUNDS
        if contrast(theme[text], theme[background]) < AA_BODY_TEXT
    ]
    assert too_faint == []


@pytest.mark.parametrize("theme_name, theme", [("dark", DARK), ("light", LIGHT)])
def test_button_labels_meet_wcag_aa(theme_name, theme):
    assert contrast(theme["--on-accent"], theme["--accent"]) >= AA_BODY_TEXT
    assert contrast(theme["--on-accent"], theme["--accent-hover"]) >= AA_BODY_TEXT
    assert contrast(theme["--on-fail"], theme["--fail"]) >= AA_BODY_TEXT
