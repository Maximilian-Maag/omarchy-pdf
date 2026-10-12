"""Unit tests: pdf/keymap — sequence parsing and the prefix-aware resolver."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import commands, keymap  # noqa: E402


class ParseSequenceCase(unittest.TestCase):
    def test_special_tokens(self):
        self.assertEqual(keymap.parse_sequence("<C-d>"), ("<C-d>",))
        self.assertEqual(keymap.parse_sequence("<Esc>"), ("<Esc>",))

    def test_plain_characters_split(self):
        self.assertEqual(keymap.parse_sequence("gg"), ("g", "g"))
        self.assertEqual(keymap.parse_sequence("j"), ("j",))

    def test_mixed(self):
        self.assertEqual(keymap.parse_sequence("<Esc>j"), ("<Esc>", "j"))
        self.assertEqual(keymap.parse_sequence("g<C-f>"), ("g", "<C-f>"))

    def test_unterminated_angle_is_literal(self):
        self.assertEqual(keymap.parse_sequence("a<b"), ("a", "<", "b"))

    def test_round_trip(self):
        for seq in ("gg", "<C-d>", "<Esc>j", "zp"):
            self.assertEqual(keymap.format_sequence(keymap.parse_sequence(seq)), seq)


class ResolverCase(unittest.TestCase):
    def setUp(self):
        self.km = keymap.default_keymap()

    def feed(self, mode, keys):
        res = keymap.Resolution(keymap.UNMATCHED)
        buf: tuple[str, ...] = ()
        for key in keys:
            res = self.km.feed(mode, key, buf)
            buf = res.buffer
            if res.state != keymap.PENDING:
                break
        return res

    def test_single_key_fires(self):
        res = self.feed("normal", ["j"])
        self.assertEqual(res.state, keymap.FIRED)
        self.assertEqual(res.command, "scroll-down")

    def test_unbound_key_is_unmatched(self):
        res = self.feed("normal", ["Z"])
        self.assertEqual(res.state, keymap.UNMATCHED)

    def test_prefix_then_fire(self):
        # 'g' is unbound but a prefix of 'gg' -> pending, then fires
        first = self.km.feed("normal", "g")
        self.assertEqual(first.state, keymap.PENDING)
        second = self.km.feed("normal", "g", first.buffer)
        self.assertEqual(second.state, keymap.FIRED)
        self.assertEqual(second.command, "first")

    def test_prefix_then_unknown_resets(self):
        first = self.km.feed("normal", "g")
        self.assertEqual(first.state, keymap.PENDING)
        second = self.km.feed("normal", "u", first.buffer)   # 'gu' unbound
        self.assertEqual(second.state, keymap.UNMATCHED)
        self.assertEqual(second.buffer, ())

    def test_flush_fires_a_complete_binding(self):
        # '<C-q>' is a complete, non-prefix binding -> feed fires it directly
        res = self.km.feed("normal", "<C-q>")
        self.assertEqual(res.state, keymap.FIRED)
        self.assertEqual(res.command, "quit")

    def test_flush_unmatched_on_partial(self):
        res = self.km.flush("normal", ("g",))
        self.assertEqual(res.state, keymap.UNMATCHED)

    def test_bound_that_is_also_prefix_stays_pending(self):
        km = keymap.KeyMap({"normal": {"g": "first", "gg": "last"}})
        res = km.feed("normal", "g")
        self.assertEqual(res.state, keymap.PENDING)
        res2 = km.feed("normal", "j", ("g",))
        self.assertEqual(res2.state, keymap.UNMATCHED)

    def test_flush_fires_the_bound_shorter(self):
        km = keymap.KeyMap({"normal": {"g": "first", "gg": "last"}})
        p = km.feed("normal", "g")
        self.assertEqual(p.state, keymap.PENDING)
        self.assertEqual(km.flush("normal", p.buffer).command, "first")


class BindTableCase(unittest.TestCase):
    def setUp(self):
        self.km = keymap.default_keymap()

    def test_command_for(self):
        self.assertEqual(self.km.command_for("normal", "gg"), "first")
        self.assertIsNone(self.km.command_for("normal", "ZZ"))
        self.assertEqual(self.km.command_for("hint", "<Esc>"), "hint-clear")

    def test_modes_present(self):
        self.assertEqual(self.km.modes(), sorted(keymap.MODES))

    def test_bind_and_unbind(self):
        self.km.bind("normal", "ZQ", "quit")
        self.assertEqual(self.km.command_for("normal", "ZQ"), "quit")
        self.km.unbind("normal", "ZQ")
        self.assertIsNone(self.km.command_for("normal", "ZQ"))

    def test_every_default_binding_names_a_real_command(self):
        for mode, mapping in keymap.DEFAULT_BINDS.items():
            for seq, line in mapping.items():
                name = line.split()[0]
                with self.subTest(mode=mode, seq=seq, command=name):
                    self.assertIsNotNone(commands.lookup(name),
                                         f"{mode}/{seq} -> unknown command {name!r}")


if __name__ == "__main__":
    unittest.main()
