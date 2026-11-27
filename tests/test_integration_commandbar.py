"""The ':' prompt offers what it knows, the way qutebrowser's does."""
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from pdf import commandbar  # noqa: E402

PALETTE = {"bg_dark": "#161622", "fg": "#ffd700", "accent": "#89b4fa",
           "selection": "#45475a", "fg_light": "#bac2de"}


class CommandBarCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = QWidget()
        self.host.resize(900, 600)
        self.host.show()
        self.bar = commandbar.CommandBar(self.host, PALETTE)
        self.bar.setGeometry(0, 560, 900, 30)
        self.bar.start("command")
        self.qapp.processEvents()

    def tearDown(self):
        self.bar.hide()
        self.host.close()
        self.host.deleteLater()
        self.qapp.processEvents()

    def _names(self):
        popup = self.bar._popup
        return [popup.item(i).data(Qt.ItemDataRole.UserRole) for i in range(popup.count())]

    def _press(self, key, text=""):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
        self.qapp.sendEvent(self.bar, event)
        self.qapp.processEvents()

    # ── suggestions ───────────────────────────────────────────────────────
    def test_offers_the_commands_as_soon_as_the_colon_is_typed(self):
        # "which command was it called?" is answered by reading, not by guessing and
        # being told "unknown command".
        self.assertTrue(self.bar._popup.isVisible())
        names = self._names()
        self.assertIn("places", names)
        self.assertIn("goto", names)
        self.assertEqual(names, sorted(names))

    def test_narrows_to_what_has_been_typed(self):
        self.bar.setText(":pl")
        self.qapp.processEvents()
        self.assertEqual(self._names(), ["places"])

    def test_no_suggestions_for_text_that_matches_nothing(self):
        self.bar.setText(":zzz")
        self.qapp.processEvents()
        self.assertFalse(self.bar._popup.isVisible())

    def test_suggestions_appear_below_the_bar(self):
        popup = self.bar._popup
        self.assertGreaterEqual(popup.geometry().top(), self.bar.geometry().bottom() - 1)
        self.assertGreaterEqual(popup.width(), popup.geometry().width())

    def test_the_help_of_each_command_is_shown_beside_it(self):
        popup = self.bar._popup
        row = [i for i in range(popup.count())
               if popup.item(i).data(Qt.ItemDataRole.UserRole) == "places"][0]
        self.assertIn("panel", popup.item(row).text())

    # ── keyboard ──────────────────────────────────────────────────────────
    def test_down_moves_the_highlight_and_leaves_the_line_alone(self):
        self.bar.setText(":p")
        self.qapp.processEvents()
        popup = self.bar._popup
        self.assertGreaterEqual(popup.count(), 2)
        before = self.bar.text()
        first = popup.currentRow()
        self._press(Qt.Key.Key_Down)
        self.assertEqual(popup.currentRow(), first + 1)
        self.assertEqual(self.bar.text(), before,
                         "rewriting the line would re-filter the list under the cursor")

    def test_return_runs_the_highlighted_command(self):
        accepted = []
        self.bar.accept.connect(lambda kind, text: accepted.append(text))
        self.bar.setText(":pl")
        self.qapp.processEvents()
        self._press(Qt.Key.Key_Return)
        self.assertEqual(accepted, ["places"])

    def test_return_runs_what_was_typed_when_it_takes_arguments(self):
        accepted = []
        self.bar.accept.connect(lambda kind, text: accepted.append(text))
        self.bar.setText(":goto 12")
        self.qapp.processEvents()
        self._press(Qt.Key.Key_Return)
        self.assertEqual(accepted, ["goto 12"])

    def test_tab_completes_the_first_match(self):
        self.bar.setText(":pl")
        self.qapp.processEvents()
        self._press(Qt.Key.Key_Tab)
        self.assertEqual(self.bar.text(), ":places")

    def test_escape_closes_the_suggestions(self):
        cancelled = []
        self.bar.cancel.connect(lambda: cancelled.append(True))
        self._press(Qt.Key.Key_Escape)
        self.assertFalse(self.bar._popup.isVisible())
        self.assertFalse(self.bar.isVisible())
        self.assertEqual(cancelled, [True])


if __name__ == "__main__":
    unittest.main()
