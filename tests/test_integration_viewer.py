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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import fixtures  # noqa: E402

# PyQt6 (with the QtPdf module) is required to build the real window. It is a
# runtime dependency, installed in CI; where it is absent the suite SKIPS rather
# than failing, so a bare dev box or a stripped runner does not go red on it.
try:
    from PyQt6.QtWidgets import QApplication  # noqa: E402
    from pdf import app as app_mod, theme  # noqa: E402
    PALETTE = dict(theme.DEFAULT_PALETTE)
    _QT_IMPORT_ERROR = None
except ImportError as _exc:  # pragma: no cover - exercised only without PyQt6
    QApplication = None
    app_mod = theme = None
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
