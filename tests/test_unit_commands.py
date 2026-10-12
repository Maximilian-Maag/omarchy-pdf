"""Unit tests: pdf/commands — dispatch, parsing, completion, error handling.

Driven against a recording FakeView, so both the effect and the absence of an
effect are observable.
"""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from fakeview import FakeView  # noqa: E402
from pdf import commands  # noqa: E402


class DispatchCase(unittest.TestCase):
    def setUp(self):
        self.view = FakeView(pages=10, page=0)

    def cmd(self, line):
        commands.dispatch(self.view, line)
        return self.view.calls[-1]

    # motion
    def test_scroll_ring(self):
        self.assertEqual(self.cmd("scroll-down"), ("scroll", 60, 0))
        self.assertEqual(self.cmd("scroll-up"), ("scroll", -60, 0))
        self.assertEqual(self.cmd("scroll-left"), ("scroll", 0, -60))
        self.assertEqual(self.cmd("scroll-right"), ("scroll", 0, 60))

    def test_half_page(self):
        self.assertEqual(self.cmd("half-down"), ("scroll_pages", 1))
        self.assertEqual(self.cmd("half-up"), ("scroll_pages", -1))

    def test_page_step(self):
        self.assertEqual(self.cmd("page-next"), ("goto_page", 1))

    def test_page_step_clamps(self):
        self.view.page = 9
        self.assertEqual(self.cmd("page-next"), ("goto_page", 9))

    def test_page_prev_clamps(self):
        self.assertEqual(self.cmd("page-prev"), ("goto_page", 0))

    def test_first_last(self):
        self.assertEqual(self.cmd("first"), ("goto_page", 0))
        self.assertEqual(self.cmd("last"), ("goto_page", 9))

    def test_edges_use_scroll(self):
        self.assertEqual(self.cmd("top"), ("goto_scroll", "top"))
        self.assertEqual(self.cmd("middle"), ("goto_scroll", "middle"))
        self.assertEqual(self.cmd("bottom"), ("goto_scroll", "bottom"))

    # goto
    def test_goto_number_is_one_based(self):
        self.assertEqual(self.cmd("goto 5"), ("goto_page", 4))

    def test_goto_label(self):
        self.assertEqual(self.cmd("goto iv"), ("goto_label", "iv"))

    def test_goto_clamps(self):
        self.assertEqual(self.cmd("goto 999"), ("goto_page", 9))

    # zoom
    def test_zoom_steps(self):
        self.assertEqual(self.cmd("zoom-in"), ("zoom", 1, None, None))
        self.assertEqual(self.cmd("zoom-out"), ("zoom", -1, None, None))

    def test_zoom_set(self):
        self.assertEqual(self.cmd("zoom-set 150"), ("zoom", None, 150, None))

    def test_zoom_set_clamps(self):
        self.assertEqual(self.cmd("zoom-set 1"), ("zoom", None, 25, None))

    def test_zoom_fit(self):
        self.assertEqual(self.cmd("zoom-fit-width"), ("zoom", None, None, "width"))
        self.assertEqual(self.cmd("zoom-fit-page"), ("zoom", None, None, "page"))

    # rotate
    def test_rotate(self):
        self.assertEqual(self.cmd("rotate-cw"), ("rotate", 90))
        self.assertEqual(self.cmd("rotate-ccw"), ("rotate", -90))

    # search
    def test_search_takes_rest_of_line(self):
        self.assertEqual(self.cmd("search hello world"), ("search", "hello world"))

    def test_search_next_prev(self):
        self.assertEqual(self.cmd("search-next"), ("search_next",))
        self.assertEqual(self.cmd("search-prev"), ("search_prev",))

    def test_search_prompt(self):
        self.assertEqual(self.cmd("search-prompt"), ("start_prompt", "search"))

    # hints
    def test_hint_follow(self):
        self.assertEqual(self.cmd("hint-follow"), ("open_hints", "follow"))

    def test_hint_activate(self):
        self.assertEqual(self.cmd("hint-activate s"), ("activate_hint", "s"))

    # history / open / sidebar
    def test_history(self):
        self.assertEqual(self.cmd("history-back"), ("history_back",))
        self.assertEqual(self.cmd("history-forward"), ("history_forward",))

    def test_open(self):
        self.assertEqual(self.cmd("open /tmp/a.pdf"), ("load", "/tmp/a.pdf"))

    def test_sidebar(self):
        self.assertEqual(self.cmd("sidebar-toggle"), ("toggle_sidebar",))

    def test_outline_goto(self):
        self.assertEqual(self.cmd("outline-goto 3"), ("outline_goto", 3))

    # yank / modes
    def test_yanks(self):
        self.assertEqual(self.cmd("yank-selection"), ("yank_selection",))
        self.assertEqual(self.cmd("yank-page"), ("yank_page",))

    def test_visual(self):
        self.assertEqual(self.cmd("visual"), ("set_mode", "visual"))

    def test_mark(self):
        self.assertEqual(self.cmd("mark"), ("start_prompt", "mark"))

    # document ops
    def test_doc_ops(self):
        for name, op in (("info", "op_info"), ("save-as", "op_save_as"),
                         ("print", "op_print"), ("attachments", "op_attachments"),
                         ("layers", "op_layers"), ("forms", "op_forms"),
                         ("annotate", "op_annotate"), ("sign", "op_sign"),
                         ("redact", "op_redact"), ("ocr", "op_ocr")):
            with self.subTest(command=name):
                self.assertEqual(self.cmd(name), (op,))

    # chrome
    def test_prompt_and_quit(self):
        self.assertEqual(self.cmd("command-prompt"), ("start_prompt", "command"))
        self.assertEqual(self.cmd("prompt-accept"), ("prompt_action", "accept"))
        self.assertEqual(self.cmd("quit"), ("quit",))

    def test_help_messages(self):
        commands.dispatch(self.view, "help")
        self.assertTrue(self.view.messages)


class ErrorCase(unittest.TestCase):
    def setUp(self):
        self.view = FakeView()

    def test_unknown_command(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(self.view, "frobnicate")

    def test_missing_required_argument(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(self.view, "goto")

    def test_too_many_arguments(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(self.view, "goto 1 2")

    def test_non_numeric_argument(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(self.view, "zoom-set abc")

    def test_search_requires_text(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(self.view, "search")

    def test_blank_line_is_noop(self):
        self.assertIsNone(commands.dispatch(self.view, "   "))
        self.assertEqual(self.view.calls, [])


class ParseCase(unittest.TestCase):
    def test_split(self):
        self.assertEqual(commands.parse("goto 5"), ("goto", "5"))

    def test_blank(self):
        self.assertEqual(commands.parse(""), ("", ""))
        self.assertEqual(commands.parse("  "), ("", ""))

    def test_rest_preserved(self):
        self.assertEqual(commands.parse("search a b c"), ("search", "a b c"))


class RegistryCase(unittest.TestCase):
    def test_alias_resolves(self):
        q = commands.lookup("q")
        clear = commands.lookup("clear")
        assert q is not None and clear is not None
        self.assertEqual(q.name, "quit")
        self.assertEqual(clear.name, "search-clear")

    def test_command_is_frozen_and_hashable(self):
        command = commands.lookup("quit")
        self.assertEqual(hash(command), hash(command))
        with self.assertRaises(Exception):
            command.name = "other"          # frozen dataclass
        set([command])                       # requires __hash__

    def test_lookup_missing(self):
        self.assertIsNone(commands.lookup("nope"))

    def test_complete_prefix(self):
        got = commands.complete("zoom")
        self.assertIn("zoom-in", got)
        self.assertIn("zoom-fit-width", got)
        self.assertTrue(all(name.startswith("zoom") for name in got))

    def test_command_names_sorted(self):
        names = commands.command_names()
        self.assertEqual(names, sorted(names))
        self.assertIn("quit", names)

    def test_every_binding_command_exists(self):
        # keeps the binding table and the registry in lockstep
        from pdf import keymap
        for mode, mapping in keymap.DEFAULT_BINDS.items():
            for seq, line in mapping.items():
                with self.subTest(mode=mode, seq=seq):
                    self.assertIsNotNone(commands.lookup(line.split()[0]))


if __name__ == "__main__":
    unittest.main()
