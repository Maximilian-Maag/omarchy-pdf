"""Omarchy theme -> viewer palette.

Pure Python (stdlib only). The palette is read from the **applied** theme at
``~/.local/state/omarchy/current/theme/colors.toml`` — never a hardcoded table — so
any stock or user theme is followed and switching the desktop theme recolours the
viewer. A missing/malformed file falls back to a sane default.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# colors.toml key -> palette key
TOML_MAP = {
    "mode": "mode",
    "background": "bg",
    "dark_background": "bg_dark",
    "darker_background": "bg_darker",
    "lighter_background": "bg_light",
    "foreground": "fg",
    "dark_foreground": "fg_dim",
    "light_foreground": "fg_light",
    "accent": "accent",
    "selection": "selection",
    "red": "red",
    "green": "green",
    "yellow": "yellow",
    "cyan": "cyan",
    "blue": "blue",
    "magenta": "magenta",
    "orange": "orange",
}

DEFAULT_PALETTE: dict[str, str] = {
    "mode": "dark",
    "bg": "#1e1e2e",
    "bg_dark": "#161622",
    "bg_darker": "#101019",
    "bg_light": "#313244",
    "fg": "#cdd6f4",
    "fg_dim": "#6c7086",
    "fg_light": "#bac2de",
    "accent": "#89b4fa",
    "selection": "#45475a",
    "red": "#f38ba8",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "cyan": "#94e2d5",
    "blue": "#89b4fa",
    "magenta": "#f5c2e7",
    "orange": "#f6b6ab",
}


def live_theme_path() -> Path:
    """Path to the applied theme's colors.toml.

    ``$OMARCHY_PDF_THEME_FILE`` overrides it (used by tests and by a caller that
    wants a pinned palette); otherwise the standard state path is used.
    """
    override = os.environ.get("OMARCHY_PDF_THEME_FILE")
    if override:
        return Path(override)
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(state) / "omarchy/current/theme/colors.toml"


def palette_from_toml(text: str, base: dict[str, str] | None = None) -> dict[str, str]:
    """Overlay a colors.toml document onto `base` (default: the default palette)."""
    palette = dict(base if base is not None else DEFAULT_PALETTE)
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return palette
    for key, value in data.items():
        target = TOML_MAP.get(key)
        if target and isinstance(value, str):
            palette[target] = value
    return palette


def load_palette(path: Path | None = None) -> dict[str, str]:
    """Read the applied theme's palette, or the default when it is unavailable."""
    file = path if path is not None else live_theme_path()
    try:
        return palette_from_toml(file.read_text())
    except OSError:
        return dict(DEFAULT_PALETTE)


def is_dark(palette: dict[str, str]) -> bool:
    """True when the palette declares dark mode."""
    return palette.get("mode", "dark") == "dark"
