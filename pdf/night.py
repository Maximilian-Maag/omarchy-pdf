"""Page colour effects: off, invert, and yellow-on-black ``contrast``.

Pure Python — no Qt. The reader's low-vision setup wants two things a paper-white
page cannot give: inverted pixels for a light room, and a maximum-contrast
yellow-on-black page for reading at high magnification. Both are a per-pixel
function of one number, so the whole feature is a 256-entry lookup table built
here and applied to the rendered page by the Qt side.

``contrast`` is deliberately not a second inversion: it maps the page's *light*
areas onto the accent foreground and its dark areas onto black, which is what
makes text legible instead of merely negative. The foreground comes from the
applied theme, so the effect follows the desktop like everything else.
"""

from __future__ import annotations

# Effects, in cycling order. ``off`` first so a fresh viewer is a paper page.
EFFECTS = ("off", "invert", "contrast")

# What a user types for ``:night <name>``: the boolean names mean "the accessible
# page", because that is what the caller who says "night mode on" wants.
ON_NAMES = ("on", "true", "yes", "1", "contrast", "night")
OFF_NAMES = ("off", "false", "no", "0", "none")


def normalize(name: str, default: str = "contrast") -> str:
    """Map a user-supplied or stored effect name onto one of :data:`EFFECTS`.

    Unknown names fall back to `default` rather than raising: this is reachable
    from a GSettings key that another program may have written a value of its
    own into, and a viewer that refuses to start over an unreadable mode is worse
    than one that reads pages the old way.
    """
    value = (name or "").strip().lower()
    if value in EFFECTS:
        return value
    if value in OFF_NAMES:
        return "off"
    if value in ON_NAMES:
        return "contrast"
    if value == "invert":
        return "invert"
    return default


def cycle(effect: str, order: tuple[str, ...] = EFFECTS) -> str:
    """The next effect in `order`; an unknown current effect restarts at the first."""
    try:
        index = order.index(normalize(effect, default=""))
    except ValueError:
        return order[0]
    return order[(index + 1) % len(order)]


def parse_colour(value: str, fallback: tuple[int, int, int] = (255, 215, 0)) -> tuple[int, int, int]:
    """``#rrggbb`` / ``rrggbb`` -> (r, g, b); anything else -> `fallback`.

    The colour arrives from the theme file, which a user edits by hand, so a typo
    must not take the viewer down with it.
    """
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        number = int(text, 16)
    except ValueError:
        return fallback
    return ((number >> 16) & 0xFF, (number >> 8) & 0xFF, number & 0xFF)


def luminance_map(effect: str, foreground: str = "#ffd700") -> list[tuple[int, int, int]] | None:
    """A 256-entry table mapping a grey value to its output colour, or None for ``off``.

    The renderer only needs the table: it converts the composited page to grey and
    looks each pixel up. ``invert`` is the plain channel flip, so a page that was
    white-on-black ends up black-on-white with no tint from the theme.
    """
    name = normalize(effect)
    if name == "off":
        return None
    if name == "invert":
        return [(255 - i, 255 - i, 255 - i) for i in range(256)]
    fg = parse_colour(foreground)
    table = []
    for i in range(256):
        # i is the page's grey value: white page areas become the foreground,
        # black text becomes the background, and anti-aliased edges blend.
        weight = i / 255.0
        table.append((int(round(fg[0] * weight)),
                      int(round(fg[1] * weight)),
                      int(round(fg[2] * weight))))
    return table


def effect_from_gsettings_get(output: str) -> str:
    """Effect for the output of ``gsettings get org.gnome.Papers night-mode``.

    Papers (the GNOME document viewer) stores the same reader-side preference as a
    boolean, and ``omarchy-toggle-pdf-night`` flips it for ``Super+Ctrl+N``. Sharing
    the key means one keybinding drives whichever reader is open instead of the
    viewer silently ignoring the key.
    """
    if (output or "").strip().lower() in ("true", "1", "yes"):
        return "contrast"
    return "off"


def effect_from_gsettings_monitor(line: str) -> str | None:
    """Effect for one line of ``gsettings monitor org.gnome.Papers night-mode``.

    The monitor prints ``night-mode: true`` per change; anything that is not that
    key's line yields None so the caller can ignore unrelated output.
    """
    text = (line or "").strip()
    if not text.startswith("night-mode:"):
        return None
    return effect_from_gsettings_get(text.split(":", 1)[1])
