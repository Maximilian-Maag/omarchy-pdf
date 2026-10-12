"""Unit tests: pdf/nav — pages, zoom, rotation, scrolling and fit arithmetic."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import nav  # noqa: E402


class ClampCase(unittest.TestCase):
    def test_within(self):
        self.assertEqual(nav.clamp(5, 0, 10), 5)

    def test_below(self):
        self.assertEqual(nav.clamp(-3, 0, 10), 0)

    def test_above(self):
        self.assertEqual(nav.clamp(99, 0, 10), 10)


class PageCase(unittest.TestCase):
    def test_clamp_page_mid(self):
        self.assertEqual(nav.clamp_page(4, 5), 4)

    def test_clamp_page_high(self):
        self.assertEqual(nav.clamp_page(9, 5), 4)

    def test_clamp_page_low(self):
        self.assertEqual(nav.clamp_page(-2, 5), 0)

    def test_clamp_page_empty_document_is_zero(self):
        self.assertEqual(nav.clamp_page(3, 0), 0)

    def test_first(self):
        self.assertEqual(nav.first_page(5), 0)

    def test_last(self):
        self.assertEqual(nav.last_page(5), 4)

    def test_last_empty(self):
        self.assertEqual(nav.last_page(0), 0)

    def test_next(self):
        self.assertEqual(nav.next_page(0, 10), 1)

    def test_next_clamps_at_end(self):
        self.assertEqual(nav.next_page(9, 10), 9)

    def test_prev(self):
        self.assertEqual(nav.prev_page(5, 10), 4)

    def test_prev_clamps_at_start(self):
        self.assertEqual(nav.prev_page(0, 10), 0)


class ConstantsCase(unittest.TestCase):
    def test_literal_limits(self):
        self.assertEqual(nav.MIN_ZOOM, 25)
        self.assertEqual(nav.MAX_ZOOM, 800)
        self.assertEqual(nav.ZOOM_STEP, 10)


class ZoomCase(unittest.TestCase):
    def test_step_default_is_ten(self):
        self.assertEqual(nav.zoom_percent(100, 1), 110)

    def test_out(self):
        self.assertEqual(nav.zoom_percent(100, -1), 90)

    def test_reset_is_noop(self):
        self.assertEqual(nav.zoom_percent(150, 0), 150)

    def test_clamped_to_min(self):
        self.assertEqual(nav.zoom_percent(30, -100), nav.MIN_ZOOM)

    def test_clamped_to_max(self):
        self.assertEqual(nav.zoom_percent(790, 100), nav.MAX_ZOOM)

    def test_custom_step(self):
        self.assertEqual(nav.zoom_percent(100, 1, step=25), 125)

    def test_clamp_zoom_low(self):
        self.assertEqual(nav.clamp_zoom(0), nav.MIN_ZOOM)

    def test_clamp_zoom_high(self):
        self.assertEqual(nav.clamp_zoom(9999), nav.MAX_ZOOM)

    def test_clamp_zoom_inside(self):
        self.assertEqual(nav.clamp_zoom(123), 123)


class RotateCase(unittest.TestCase):
    def test_cw(self):
        self.assertEqual(nav.rotate(0, 90), 90)

    def test_wrap(self):
        self.assertEqual(nav.rotate(270, 90), 0)

    def test_ccw_wrap(self):
        self.assertEqual(nav.rotate(0, -90), 270)

    def test_normalize(self):
        self.assertEqual(nav.normalize_rotation(450), 90)

    def test_normalize_negative(self):
        self.assertEqual(nav.normalize_rotation(-90), 270)


class ScrollCase(unittest.TestCase):
    def test_moves(self):
        self.assertEqual(nav.scroll_offset(10, 5, 1000, 100), 15)

    def test_clamps_at_zero(self):
        self.assertEqual(nav.scroll_offset(10, -50, 1000, 100), 0)

    def test_clamps_at_end(self):
        self.assertEqual(nav.scroll_offset(895, 50, 990, 100), 890)

    def test_fits_returns_zero(self):
        self.assertEqual(nav.scroll_offset(50, 50, 100, 200), 0)


class FitCase(unittest.TestCase):
    def test_fit_width(self):
        self.assertEqual(nav.fit_scale(100, 100, 200, 500, "width"), 2.0)

    def test_fit_page(self):
        self.assertEqual(nav.fit_scale(100, 200, 200, 200, "page"), 1.0)

    def test_fit_page_limited_by_height(self):
        self.assertEqual(nav.fit_scale(100, 400, 200, 200, "page"), 0.5)

    def test_unknown_mode_is_one(self):
        self.assertEqual(nav.fit_scale(100, 100, 200, 200, "diagonal"), 1.0)

    def test_degenerate_page_is_one(self):
        self.assertEqual(nav.fit_scale(0, 100, 200, 200, "width"), 1.0)

    def test_degenerate_view_is_one(self):
        self.assertEqual(nav.fit_scale(100, 100, 0, 200, "page"), 1.0)

    def test_degenerate_page_height_is_one(self):
        self.assertEqual(nav.fit_scale(100, 0, 200, 200, "page"), 1.0)

    def test_degenerate_view_height_is_one(self):
        self.assertEqual(nav.fit_scale(100, 100, 200, 0, "page"), 1.0)

    def test_margin_applied(self):
        self.assertEqual(nav.fit_scale(100, 100, 300, 300, "width", margin=100), 2.0)


if __name__ == "__main__":
    unittest.main()
