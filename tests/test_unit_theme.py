"""Unit tests: pdf/theme — colors.toml -> palette."""
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import theme  # noqa: E402

TOML = """
mode = "light"
background = "#ffffff"
foreground = "#000000"
accent = "#123456"
some_unknown = "#abcdef"
"""


class PaletteCase(unittest.TestCase):
    def test_defaults_without_document(self):
        p = theme.palette_from_toml("")
        self.assertEqual(p["bg"], theme.DEFAULT_PALETTE["bg"])

    def test_overlays_known_keys(self):
        p = theme.palette_from_toml(TOML)
        self.assertEqual(p["bg"], "#ffffff")
        self.assertEqual(p["fg"], "#000000")
        self.assertEqual(p["accent"], "#123456")
        self.assertEqual(p["mode"], "light")

    def test_unknown_keys_ignored(self):
        p = theme.palette_from_toml(TOML)
        self.assertNotIn("some_unknown", p)
        self.assertNotIn(None, p)

    def test_malformed_returns_base(self):
        p = theme.palette_from_toml("this is = = not toml")
        self.assertEqual(p, theme.DEFAULT_PALETTE)

    def test_explicit_base_used(self):
        base = {"mode": "dark", "bg": "#111111"}
        p = theme.palette_from_toml('background = "#222222"', base=base)
        self.assertEqual(p["bg"], "#222222")
        self.assertEqual(p["mode"], "dark")

    def test_dark_foreground_maps_to_dim(self):
        p = theme.palette_from_toml('dark_foreground = "#333333"')
        self.assertEqual(p["fg_dim"], "#333333")


class IsDarkCase(unittest.TestCase):
    def test_dark(self):
        self.assertTrue(theme.is_dark({"mode": "dark"}))

    def test_light(self):
        self.assertFalse(theme.is_dark({"mode": "light"}))

    def test_default_is_dark(self):
        self.assertTrue(theme.is_dark({}))


class LiveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-theme-"))
        self.file = self.tmp / "colors.toml"
        self.file.write_text('mode = "light"\nbackground = "#abcdef"\n')
        self.saved = {k: os.environ.get(k)
                      for k in ("OMARCHY_PDF_THEME_FILE", "XDG_STATE_HOME")}
        os.environ["OMARCHY_PDF_THEME_FILE"] = str(self.file)

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_override_path(self):
        self.assertEqual(theme.live_theme_path(), self.file)

    def test_loads_live(self):
        self.assertEqual(theme.load_palette()["bg"], "#abcdef")

    def test_missing_file_falls_back(self):
        self.file.unlink()
        self.assertEqual(theme.load_palette(), theme.DEFAULT_PALETTE)

    def test_state_home_is_honoured(self):
        os.environ.pop("OMARCHY_PDF_THEME_FILE", None)
        os.environ["XDG_STATE_HOME"] = "/tmp/xdg-state-test"
        self.assertEqual(str(theme.live_theme_path()),
                         "/tmp/xdg-state-test/omarchy/current/theme/colors.toml")


if __name__ == "__main__":
    unittest.main()
