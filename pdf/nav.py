"""Navigation arithmetic: pages, scrolling, zoom and rotation.

Pure Python, no Qt. Every function is total — it clamps rather than raising — so
the UI can never scroll or zoom off the end of the document.

The clamps are written as ``max``/``min`` calls (not ``if value < low`` checks)
on purpose: a boundary comparison such as ``value <= 0`` has a twin
(``value < 0``) that only differs at the boundary, where the result is identical,
so the mutant can never be killed. `min`/`max` carry no such twin, which keeps the
mutation score honest.
"""

from __future__ import annotations

# zoom limits, in percent
MIN_ZOOM = 25
MAX_ZOOM = 800
ZOOM_STEP = 10

# valid page rotations, in degrees
ROTATIONS = (0, 90, 180, 270)


def clamp(value: float, low: float, high: float) -> float:
    """Clamp `value` into [low, high]."""
    return max(low, min(value, high))


def clamp_page(index: int, count: int) -> int:
    """Clamp a page index into a document of `count` pages.

    A non-positive `count` collapses the range to 0, so an empty document always
    resolves to page 0 rather than a negative index.
    """
    return int(clamp(index, 0, count - 1))


def first_page(count: int) -> int:
    return clamp_page(0, count)


def last_page(count: int) -> int:
    """The final page index (0 for an empty document)."""
    return clamp_page(count - 1, count)


def next_page(current: int, count: int) -> int:
    return clamp_page(current + 1, count)


def prev_page(current: int, count: int) -> int:
    return clamp_page(current - 1, count)


def zoom_percent(current: int, delta: int, step: int = ZOOM_STEP,
                 low: int = MIN_ZOOM, high: int = MAX_ZOOM) -> int:
    """Apply `delta` zoom steps to `current`, clamped to [low, high].

    `delta` is in steps, so `zoom_percent(100, -1)` is 90 at the default step of 10.
    """
    return int(clamp(current + delta * step, low, high))


def clamp_zoom(percent: int, low: int = MIN_ZOOM, high: int = MAX_ZOOM) -> int:
    """Clamp a directly-set zoom percentage."""
    return int(clamp(percent, low, high))


def rotate(current: int, delta: int) -> int:
    """Rotate a multiple-of-90 angle, normalised into [0, 360)."""
    return (current + delta) % 360


def normalize_rotation(angle: int) -> int:
    """Snap an arbitrary angle into [0, 360)."""
    return angle % 360


def scroll_offset(current: float, delta: float, extent: float, viewport: float) -> float:
    """Clamp a scroll offset so the viewport never leaves the page extent.

    `extent` is the full scrollable length, `viewport` the visible length. When the
    content fits (extent <= viewport) the only valid offset is 0.
    """
    return clamp(current + delta, 0.0, extent - viewport)


def fit_scale(page_w: float, page_h: float, view_w: float, view_h: float,
              mode: str, margin: float = 0.0) -> float:
    """Scale factor fitting a page (``"width"`` or ``"page"``) into a viewport.

    Returns 1.0 for an unknown mode or a degenerate (non-positive) size, so a fit
    key is never a silent no-op.
    """
    w = view_w - margin
    h = view_h - margin
    if page_w <= 0 or page_h <= 0 or w <= 0 or h <= 0:
        return 1.0
    if mode == "width":
        return w / page_w
    if mode == "page":
        return min(w / page_w, h / page_h)
    return 1.0
