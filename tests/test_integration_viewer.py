"""Integration tests: the real Qt window, driven offscreen.

Builds the actual MainWindow against a fixture PDF and drives it through the real
keymap + command layer, asserting document state. Runs with QT_QPA_PLATFORM=offscreen
so no display is needed (tools/run_tests.sh picks an interpreter that has PyQt6).
"""
import os
import pathlib
import sys
import tempfile
import time
import unittest

# Force offscreen: this drives real Qt, and inheriting the session's QT_QPA_PLATFORM makes
# the run depend on the desktop session (that is exactly what made the JS harness flaky).
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# No gsettings children from the window under test: the shared night-mode key is read
# and watched only in a real session (its parsing is unit-tested in test_unit_night).
os.environ["OMARCHY_PDF_GSETTINGS"] = "0"

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import fixtures  # noqa: E402

# PyQt6 (with the QtPdf module) is required to build the real window. It is a
# runtime dependency, installed in CI; where it is absent the suite SKIPS rather
# than failing, so a bare dev box or a stripped runner does not go red on it.
try:
    from PyQt6.QtWidgets import QApplication  # noqa: E402
    from PyQt6.QtCore import QRectF  # noqa: E402
    from PyQt6.QtPdf import QPdfLinkModel  # noqa: E402
    from pdf import app as app_mod, theme, view as view_mod  # noqa: E402
    PALETTE = dict(theme.DEFAULT_PALETTE)
    _QT_IMPORT_ERROR = None
except ImportError as _exc:  # pragma: no cover - exercised only without PyQt6
    QApplication = None
    app_mod = theme = view_mod = None
    PALETTE = {}
    _QT_IMPORT_ERROR = str(_exc)


@unittest.skipIf(QApplication is None,
                 "PyQt6 with QtPdf is required for the offscreen integration suite (%s)"
                 % _QT_IMPORT_ERROR)
class ViewerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication(["test"])

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-int-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.pdf = fixtures.write(self.tmp / "text.pdf", fixtures.text_pdf())
        self.window = app_mod.MainWindow(path=self.pdf, palette=PALETTE)
        self.addCleanup(self.window.close)
        self.view = self.window.view
        # Shown, even offscreen: a widget that was resized but never laid out reports a
        # degenerate viewport, and hint targets are filtered against the visible area —
        # so an unshown window would test a geometry the reader never sees.
        self.window.resize(1000, 1300)
        self.window.show()
        self.pump()

    def pump(self, until=None, rounds: int = 400):
        """Run the event loop so the async search worker can deliver results."""
        for _ in range(rounds):
            self.qapp.processEvents()
            time.sleep(0.004)
            if until is not None and until():
                return

    # ── loading ───────────────────────────────────────────────────────────
    def test_document_loaded(self):
        self.assertEqual(self.view.page_count(), 3)
        self.assertEqual(self.view.current_page(), 0)

    def test_page_composited_on_paper(self):
        # QtPdf renders a page with a TRANSPARENT background (most PDFs never paint the
        # white sheet). The view must composite it onto opaque paper before showing it:
        # otherwise the page shows the scene background, which on a dark theme is
        # near-black, and a page of black text is rendered black-on-black.
        self.view.resize(900, 1200)
        self.view.goto_page(0)
        self.view._render_visible()
        item = self.view._pages.get(0)
        self.assertIsNotNone(item, "page 0 should have rendered")
        pixel = item.pixmap().toImage().pixelColor(2, 2)
        self.assertEqual(pixel.alpha(), 255, "page background must be opaque")
        self.assertGreater(min(pixel.red(), pixel.green(), pixel.blue()), 200,
                           "page paper must be light, not the dark scene background")

    # ── navigation via the keymap ─────────────────────────────────────────
    def test_keymap_goto_last(self):
        self.view.send_keys("G")
        self.assertEqual(self.view.current_page(), 2)

    def test_keymap_goto_first(self):
        self.view.send_keys("G")
        self.view.send_keys("g")
        self.view.send_keys("g")
        self.assertEqual(self.view.current_page(), 0)

    def test_command_goto(self):
        self.view.run_command("goto 2")
        self.assertEqual(self.view.current_page(), 1)

    def test_page_next_clamps(self):
        self.view.send_keys("G")
        self.view.run_command("page-next")
        self.assertEqual(self.view.current_page(), 2)

    def test_goto_label(self):
        self.view.run_command("goto 2")
        self.assertEqual(self.view.page_label(1), "2")
        self.view.run_command("goto 1")
        self.assertEqual(self.view.current_page(), 0)

    # ── zoom / rotate ─────────────────────────────────────────────────────
    def test_zoom_steps(self):
        self.view.run_command("zoom-in")
        self.assertEqual(self.view.zoom_percent(), 110)

    def test_zoom_set_and_clamp(self):
        self.view.run_command("zoom-set 250")
        self.assertEqual(self.view.zoom_percent(), 250)
        self.view.run_command("zoom-set 1")
        self.assertEqual(self.view.zoom_percent(), 25)

    def test_rotate(self):
        self.view.run_command("rotate-cw")
        self.assertEqual(self.view.rotation(), 90)
        self.view.run_command("rotate-ccw")
        self.assertEqual(self.view.rotation(), 0)

    # ── search ────────────────────────────────────────────────────────────
    def test_search_jumps_to_hit(self):
        self.view.run_command("search two")
        self.pump(until=lambda: not self.view._search_pending)
        self.assertEqual(self.view.current_page(), 1)
        self.assertEqual(self.view.search_query(), "two")

    def test_search_clear(self):
        self.view.run_command("search two")
        self.view.run_command("search-clear")
        self.assertEqual(self.view.search_query(), "")

    # ── outline ───────────────────────────────────────────────────────────
    def test_outline_present_and_followed(self):
        entries = self.view.outline()
        self.assertTrue(entries)
        self.view.outline_goto(0)
        self.assertEqual(self.view.current_page(), 1)

    # ── hints ─────────────────────────────────────────────────────────────
    def test_hints_on_link_page(self):
        self.view.goto_page(0)
        self.view.run_command("hint-follow")
        self.assertEqual(self.view.mode(), "hint")
        self.assertTrue(self.view._hint_labels)
        self.view.run_command("hint-clear")
        self.assertEqual(self.view.mode(), "normal")

    # ── links: mouse clicks, hint placement, f vs F ───────────────────────
    def _load_links(self):
        """Page 1 of the loaded fixture: one external URI, one internal destination."""
        path = fixtures.write(self.tmp / "links.pdf", fixtures.mixed_links_pdf())
        self.view.load(path)
        self.view.resize(900, 1200)
        self.view.goto_page(0)
        self.pump()
        entries = self.view._link_entries(0)
        self.assertEqual(len(entries), 2, "fixture should expose two links")
        external = [box for link, box in entries if self.view._link_url(link)]
        internal = [box for link, box in entries if not self.view._link_url(link)]
        self.assertEqual((len(external), len(internal)), (1, 1))
        return external[0], internal[0]

    def _click(self, scene_point):
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import Qt as QtCore
        pos = self.view.mapFromScene(scene_point)
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos),
                            QtCore.MouseButton.LeftButton,
                            QtCore.MouseButton.LeftButton,
                            QtCore.KeyboardModifier.NoModifier)
        self.view.mousePressEvent(event)
        self.qapp.processEvents()

    def test_mouse_click_on_external_link_opens_it(self):
        # A click on a link annotation is what every other reader does; before this the
        # view had no mouse handling at all, so the click was swallowed and a perfectly
        # good link read as broken.
        external, _internal = self._load_links()
        opened = []
        self.view.open_url = opened.append
        self._click(external.center())
        self.assertEqual(opened, ["https://omarchy.org/"])

    def test_mouse_click_on_internal_link_jumps_to_its_page(self):
        _external, internal = self._load_links()
        self.view.open_url = lambda url: self.fail(f"an internal link must not open {url}")
        self._click(internal.center())
        self.assertEqual(self.view.current_page(), 1)

    # ── page colour (night mode) ──────────────────────────────────────────
    def _corner(self):
        self.view.goto_page(0)
        self.view._render_visible()
        item = self.view._pages.get(0)
        self.assertIsNotNone(item, "page 0 should have rendered")
        return item.pixmap().toImage().pixelColor(2, 2)

    def test_contrast_paints_the_paper_in_the_theme_foreground(self):
        # The accessible page is yellow-on-black, not a negative: the sheet's light
        # areas take the theme foreground, and the dark text becomes the background.
        self.view.set_night("contrast")
        self.assertEqual(self.view.night_effect(), "contrast")
        pixel = self._corner()
        expected = PALETTE["fg"]
        self.assertEqual(("#%02x%02x%02x" % (pixel.red(), pixel.green(), pixel.blue())).lower(),
                         expected.lower())
        self.assertEqual(pixel.alpha(), 255, "the paper must stay opaque in every effect")

    def test_invert_flips_the_paper_to_black(self):
        self.view.set_night("invert")
        pixel = self._corner()
        self.assertLess(max(pixel.red(), pixel.green(), pixel.blue()), 40,
                        "an inverted white sheet must render black")

    def test_off_restores_the_paper(self):
        self.view.set_night("contrast")
        self.view.set_night("off")
        pixel = self._corner()
        self.assertGreater(min(pixel.red(), pixel.green(), pixel.blue()), 200)

    def test_toggle_cycles_and_renders(self):
        self.assertEqual(self.view.night_effect(), "off")
        self.view.run_command("night-toggle")
        self.assertEqual(self.view.night_effect(), "invert")
        self.view.run_command("night-toggle")
        self.assertEqual(self.view.night_effect(), "contrast")
        self.view.run_command("night-toggle")
        self.assertEqual(self.view.night_effect(), "off")

    def test_night_command_takes_a_name(self):
        self.view.run_command("night on")
        self.assertEqual(self.view.night_effect(), "contrast")
        self.view.run_command("night off")
        self.assertEqual(self.view.night_effect(), "off")

    def test_night_change_is_announced(self):
        said = []
        self.view.messageRaised.connect(lambda text, level: said.append(text))
        self.view.set_night("contrast")
        self.assertIn("contrast", said[-1])

    # ── hints on a page with no link annotations ──────────────────────────
    def _hint_announcement(self):
        said = []
        self.view.messageRaised.connect(lambda text, level: said.append(text))
        return said

    def test_hints_fall_back_to_the_outline_on_a_page_without_links(self):
        # `f` used to say "no links in view" on any prose page, which is where a reader
        # actually stands — the outline is the only structure such a page has.
        self.view.goto_page(2)
        self.assertFalse(self.view._link_entries(2), "page 3 of the fixture has no links")
        said = self._hint_announcement()
        self.view.run_command("hint-follow")
        self.assertEqual(self.view.mode(), "hint")
        kinds = [target[0] for target in self.view._hint_targets]
        self.assertEqual(set(kinds), {"outline"})
        self.assertTrue(said and "\u2192" in said[-1], f"destinations must be spoken: {said}")

    def test_outline_hint_jumps_to_its_entry(self):
        self.view.goto_page(2)
        self.view.run_command("hint-follow")
        self.view.send_keys(self.view._hint_labels[0])
        self.assertEqual(self.view.current_page(), 1)

    def test_links_win_over_the_outline_when_the_page_has_them(self):
        external, _internal = self._load_links()
        self.view.run_command("hint-follow")
        kinds = {target[0] for target in self.view._hint_targets}
        self.assertEqual(kinds, {"link"})

    # ── destinations: land on the mark, not on the page top ───────────────
    def _load_destinations(self):
        """A document whose destinations name a point, in a window shorter than a page."""
        self.window.resize(900, 380)
        path = fixtures.write(self.tmp / "dest.pdf", fixtures.destination_points_pdf())
        self.view.load(path)
        self.view.goto_page(0)
        self.pump()
        return path

    def _assert_landed_on(self, page, point):
        target = self.view._point_scene(page, point)
        self.assertIsNotNone(target, "destination must map onto the scene")
        viewport = self.view._viewport_rect()
        self.assertTrue(viewport.contains(target),
                        f"destination {target} left the window {viewport}")
        page_rect = self.view._positions[page]
        if page_rect.bottom() - target.y() >= viewport.height():
            self.assertLess(target.y() - viewport.top(), 0.25 * viewport.height(),
                            "with room below the mark the destination belongs near "
                            "the top of the window, not in its middle")

    def test_internal_link_lands_on_its_destination_point(self):
        # `/Fit` names a page only, so a viewer that drops the y coordinate still looks
        # right with it; the fixture's `/XYZ` names a spot 200 pt down, which centring
        # the page pushes out of a window shorter than the page.
        self._load_destinations()
        entries = self.view._link_entries(0)
        self.assertEqual(len(entries), 1)
        link, box = entries[0]
        self.assertGreater(link.location().y(), 0, "fixture should name a point")
        self._click(box.center())
        self.pump()
        self.assertEqual(self.view.current_page(), 1)
        self._assert_landed_on(1, link.location())

    def test_outline_goto_lands_on_the_bookmark_point(self):
        self._load_destinations()
        page, location = self.view.outline_destination(0)
        self.assertEqual(page, 1)
        self.assertIsNotNone(location)
        self.assertGreater(location.y(), 0, "fixture bookmark should name a point")
        self.view.outline_goto(0)
        self.pump()
        self.assertEqual(self.view.current_page(), 1)
        self._assert_landed_on(1, location)

    # ── the outline sidebar from the keyboard ─────────────────────────────
    def test_sidebar_takes_the_keyboard_and_escape_returns_it(self):
        from PyQt6.QtCore import Qt as QtCore
        from PyQt6.QtTest import QTest
        # Focus only moves inside an active window, on screen and offscreen alike.
        self.window.activateWindow()
        self.window.raise_()
        self.pump()
        self.assertFalse(self.window.dock.isVisible())
        self.view.send_keys("t")
        self.pump()
        self.assertTrue(self.window.dock.isVisible(), "t must reveal the outline")
        self.assertTrue(self.window.outline.hasFocus(),
                        "revealing the outline must put the keyboard in it, "
                        "otherwise the tree is mouse-only")
        item = self.window.outline.currentItem()
        self.assertIsNotNone(item, "the entry for the current page should be selected")
        QTest.keyClick(self.window.outline, QtCore.Key.Key_Return)
        self.pump()
        self.assertEqual(self.view.current_page(), 1, "Return activates the entry")
        self.assertFalse(self.window.outline.hasFocus(),
                         "after a jump the keys belong to the page again")
        self.view.send_keys("t")
        self.pump()
        self.assertTrue(self.window.outline.hasFocus())
        QTest.keyClick(self.window.outline, QtCore.Key.Key_Escape)
        self.pump()
        self.assertFalse(self.window.dock.isVisible(), "Escape leaves the outline")
        self.assertTrue(self.view.hasFocus())

    def test_mouse_click_off_a_link_does_nothing(self):
        self._load_links()
        opened = []
        self.view.open_url = opened.append
        # the bottom-left corner of page 1 carries no annotation
        self._click(self.view._positions[0].topLeft())
        self.assertEqual(opened, [])
        self.assertEqual(self.view.current_page(), 0)

    def test_mouse_click_in_hint_mode_does_not_activate(self):
        # hint mode owns the pointer: a stray click must not fire a link while the
        # reader is typing a label.
        external, _internal = self._load_links()
        opened = []
        self.view.open_url = opened.append
        self.view.run_command("hint-follow")
        self._click(external.center())
        self.assertEqual(opened, [])
        self.assertEqual(self.view.mode(), "hint")

    def test_hint_labels_scale_with_zoom(self):
        # QtPdf reports link rectangles in PDF points, so they have to be scaled by the
        # zoom: the labels used to be translated by the page origin only, which is
        # correct at 100 % and wrong at every other zoom.
        self._load_links()
        self.view.zoom(set_pct=200)
        page = self.view._positions[0]
        size = self.view.doc.pagePointSize(0)
        self.assertAlmostEqual(page.width(), float(size.width()) * 2, delta=0.5)
        raw = self.view.link_model.data(self.view.link_model.index(0, 0),
                                        QPdfLinkModel.Role.Rectangle.value)
        expected = QRectF(page.x() + raw.x() * 2, page.y() + raw.y() * 2,
                          raw.width() * 2, raw.height() * 2)
        box = self.view._link_entries(0)[0][1]
        self.assertAlmostEqual(box.x(), expected.x(), delta=1.0)
        self.assertAlmostEqual(box.y(), expected.y(), delta=1.0)
        self.assertAlmostEqual(box.width(), expected.width(), delta=0.5)
        self.assertAlmostEqual(box.height(), expected.height(), delta=0.5)

    def test_link_boxes_follow_the_rotation(self):
        # Same root cause as the zoom: the rectangles are reported unrotated, so a
        # rotated view has to rotate them about the page centre or they fall off the
        # page (a 612x792 page rotated by 90° is only 612 points tall).
        self._load_links()
        self.view.rotate(90)
        page = self.view._positions[0]
        entries = self.view._link_entries(0)
        self.assertEqual(len(entries), 2)
        for link, box in entries:
            self.assertTrue(page.contains(box), "a link box must stay on its page")
            hit = self.view._link_at(box.center())
            self.assertIsNotNone(hit, "the box centre must hit the link it names")
            self.assertEqual(self.view._link_url(hit), self.view._link_url(link))
            self.assertEqual(int(hit.page()), int(link.page()))

    def test_hint_open_offers_only_external_links(self):
        # `F` means "open in the browser"; an internal destination has no URL, so it is
        # not a target for it. Before this both keys behaved identically.
        self._load_links()
        self.view.run_command("hint-follow")
        follow = len(self.view._hint_labels)
        self.view.run_command("hint-clear")
        self.view.run_command("hint-open")
        opening = len(self.view._hint_labels)
        self.view.run_command("hint-clear")
        self.assertEqual((follow, opening), (2, 1))

    def test_hint_activation_opens_external_link(self):
        self._load_links()
        opened = []
        self.view.open_url = opened.append
        self.view.run_command("hint-open")
        self.view.hint_key(self.view._hint_labels[0])
        self.assertEqual(opened, ["https://omarchy.org/"])
        self.assertEqual(self.view.mode(), "normal")

    def test_hints_survive_a_re_render(self):
        # Page pixmaps are inserted into the same scene at z 0, so overlay chrome without
        # a z of its own is painted UNDER any page added afterwards. A zoom (or rotate)
        # removes and re-adds every page, which buried a live hint set: mode still
        # "hint", the labels still matched, nothing on screen.
        self._load_links()
        self.view.run_command("hint-follow")
        self.assertTrue(self.view._overlay)
        self.view.zoom(set_pct=200)
        self.assertEqual(self.view.mode(), "hint")
        page_z = max(item.zValue() for item in self.view._pages.values())
        for item in self.view._overlay:
            self.assertGreater(item.zValue(), page_z,
                               "every overlay item must paint above the pages")

    def test_hint_labels_grow_with_the_zoom(self):
        # A fixed point size is a few pixels next to page text at a reading zoom (fit
        # width is 200-300 %, the magnification this reader uses), which looked exactly
        # like hints that never appeared.
        self._load_links()
        self.view.run_command("hint-follow")
        small = self.view._overlay[-1].font().pixelSize()
        self.view.run_command("hint-clear")
        self.view.zoom(set_pct=300)
        self.view.run_command("top")     # at 300 % the page is taller than the window
        self.view.run_command("hint-follow")
        large = self.view._overlay[-1].font().pixelSize()
        self.assertEqual(small, 12, "labels keep a readable floor at 100 %")
        self.assertEqual(large, 33, "labels scale with the zoom")
        self.assertGreater(large, small)

    def test_hint_plate_is_centred_on_its_link(self):
        external, _internal = self._load_links()
        self.view.run_command("hint-follow")
        plates = [item for item in self.view._overlay
                  if item.data(view_mod.OVERLAY_KIND) == "hint-plate"]
        self.assertEqual(len(plates), len(self.view._hint_labels))
        nearest = min(plates,
                      key=lambda item: abs(item.sceneBoundingRect().center().y()
                                           - external.center().y()))
        centre = nearest.sceneBoundingRect().center()
        self.assertAlmostEqual(centre.x(), external.center().x(), delta=1.0)
        self.assertAlmostEqual(centre.y(), external.center().y(), delta=1.0)

    def test_hint_on_a_page_with_no_links_and_no_outline_says_so(self):
        # Entering hint mode with nothing to point at used to show an empty page and eat
        # the next keystroke as a bad label ("no such hint"). The fixture has no outline,
        # so the fallback has nothing to offer either and the reason has to be spoken.
        path = fixtures.write(self.tmp / "nolinks.pdf", fixtures.mixed_links_pdf())
        self.view.load(path)
        self.view.resize(500, 400)
        self.view.goto_page(1)          # page 2 carries neither links nor outline entries
        self.pump()
        messages = []
        self.view.messageRaised.connect(lambda text, level="info": messages.append((level, text)))
        self.view.run_command("hint-follow")
        self.assertEqual(self.view.mode(), "normal")
        self.assertFalse(self.view._overlay)
        self.assertEqual(messages, [("error", "no links or outline in this document")])

    def test_hints_cover_the_visible_neighbouring_page(self):
        # Hints were collected from the current page only, so on a spread (or when the
        # links sit on the sheet above) `f` said "0 hints" with the links on screen.
        self._load_links()
        self.view.run_command("zoom-set 60")     # both sheets on screen, links included
        self.view.goto_page(1)          # a page with no links of its own
        self.pump()
        self.assertEqual(self.view.current_page(), 1)
        self.view.run_command("hint-follow")
        self.assertEqual(self.view.mode(), "hint")
        self.assertEqual(len(self.view._hint_labels), 2)

    def test_hints_only_cover_links_in_view(self):
        # A label has to land where the reader can see it: a page can be taller than the
        # window, and hinting a box below the fold draws off screen.
        self._load_links()
        self.window.resize(900, 300)
        self.pump()
        self.view.goto_page(0)
        self.pump()
        messages = []
        self.view.messageRaised.connect(lambda text, level="info": messages.append((text, level)))
        self.view.run_command("hint-follow")
        self.assertEqual(self.view.mode(), "normal")
        self.assertFalse(self.view._overlay)
        self.assertEqual(messages[-1], ("no links or outline in this document", "error"))

    def test_hint_plates_stay_inside_the_viewport(self):
        # Centred on the link, but never half outside the window: a plate at the edge is
        # clamped inwards.
        self._load_links()
        self.view.run_command("hint-follow")
        viewport = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        plates = [item for item in self.view._overlay
                  if item.data(view_mod.OVERLAY_KIND) == "hint-plate"]
        self.assertTrue(plates)
        for plate in plates:
            self.assertTrue(viewport.contains(plate.sceneBoundingRect()),
                            f"plate {plate.sceneBoundingRect()} escapes {viewport}")

    # ── prompts ───────────────────────────────────────────────────────────
    def test_command_prompt_sets_mode(self):
        self.view.send_keys(":")
        self.assertEqual(self.view.mode(), "command")

    def test_prompt_accept_runs_command(self):
        self.window._prompt("command")
        self.window._prompt_accept("command", "goto 3")
        self.assertEqual(self.view.current_page(), 2)
        self.assertEqual(self.view.mode(), "normal")

    def test_search_prompt_accept(self):
        self.window._prompt("search")
        self.window._prompt_accept("search", "three")
        self.pump(until=lambda: not self.view._search_pending)
        self.assertEqual(self.view.current_page(), 2)

    # ── window ────────────────────────────────────────────────────────────
    def test_quit_command_closes_the_window(self):
        self.window.show()
        self.pump()
        self.assertTrue(self.window.isVisible())
        self.view.run_command("quit")
        self.assertFalse(self.window.isVisible())

    def test_quit_key_closes_the_window(self):
        """`q` must close the window instead of aborting the process.

        commands.h_quit calls view.quit(), which PdfView did not implement; the
        AttributeError was raised inside keyPressEvent, and PyQt6 escalates an unhandled
        exception in a reimplemented virtual to qFatal() — so pressing q dumped core.
        Driving the real key is the point of this test: calling run_command() directly
        would raise an ordinary traceback and never take that path.
        """
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        self.window.show()
        self.pump()
        self.assertTrue(self.window.isVisible())
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q,
                          Qt.KeyboardModifier.NoModifier, "q")
        self.qapp.sendEvent(self.view, event)
        self.pump()
        self.assertFalse(self.window.isVisible())

    # ── marks ─────────────────────────────────────────────────────────────
    def test_marks(self):
        self.view.run_command("goto 2")
        self.view.run_command("mark-set a")
        self.view.run_command("goto 1")
        self.view.run_command("mark-go a")
        self.assertEqual(self.view.current_page(), 1)

    # ── yank ──────────────────────────────────────────────────────────────
    def test_yank_page_copies_text(self):
        self.view.run_command("yank-page")
        clipboard = QApplication.clipboard().text()
        self.assertIn("Hello page one", clipboard)

    # ── errors surface as messages ────────────────────────────────────────
    def test_bad_command_messages(self):
        captured = []
        self.view.messageRaised.connect(lambda text, level="info": captured.append(text))
        self.view.run_command("frobnicate")
        self.assertTrue(any("not a command" in m for m in captured))


if __name__ == "__main__":
    unittest.main()
