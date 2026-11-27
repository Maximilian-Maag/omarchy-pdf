"""Unit tests: pdf/night — effects, cycling, the luminance table and the shared key."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import night  # noqa: E402


class NormalizeCase(unittest.TestCase):
    def test_effects_pass_through(self):
        for name in night.EFFECTS:
            self.assertEqual(night.normalize(name), name)

    def test_boolean_on_means_contrast(self):
        for name in ("on", "true", "yes", "1", "night", "contrast", "ON", " True "):
            self.assertEqual(night.normalize(name), "contrast")

    def test_boolean_off_means_off(self):
        for name in ("off", "false", "no", "0", "none", "OFF"):
            self.assertEqual(night.normalize(name), "off")

    def test_invert_name(self):
        self.assertEqual(night.normalize("invert"), "invert")

    def test_unknown_falls_back(self):
        self.assertEqual(night.normalize("sepia"), "contrast")
        self.assertEqual(night.normalize("sepia", default="off"), "off")
        self.assertEqual(night.normalize(None, default="off"), "off")


class CycleCase(unittest.TestCase):
    def test_order(self):
        self.assertEqual(night.cycle("off"), "invert")
        self.assertEqual(night.cycle("invert"), "contrast")
        self.assertEqual(night.cycle("contrast"), "off")

    def test_unknown_restarts(self):
        self.assertEqual(night.cycle("sepia"), "off")


class ParseColourCase(unittest.TestCase):
    def test_hash_and_bare(self):
        self.assertEqual(night.parse_colour("#ffd700"), (255, 215, 0))
        self.assertEqual(night.parse_colour("ffd700"), (255, 215, 0))

    def test_typo_falls_back(self):
        self.assertEqual(night.parse_colour("#ffd70"), (255, 215, 0))
        self.assertEqual(night.parse_colour("zzzzzz"), (255, 215, 0))
        self.assertEqual(night.parse_colour(""), (255, 215, 0))

    def test_custom_fallback(self):
        self.assertEqual(night.parse_colour("nope", fallback=(1, 2, 3)), (1, 2, 3))


class LuminanceMapCase(unittest.TestCase):
    def test_off_has_no_table(self):
        self.assertIsNone(night.luminance_map("off"))
        self.assertIsNone(night.luminance_map("false"))

    def test_table_has_256_entries(self):
        for effect in ("invert", "contrast"):
            self.assertEqual(len(night.luminance_map(effect)), 256)

    def test_invert_flips_channels(self):
        table = night.luminance_map("invert")
        self.assertEqual(table[0], (255, 255, 255))
        self.assertEqual(table[255], (0, 0, 0))
        self.assertEqual(table[100], (155, 155, 155))

    def test_contrast_maps_page_white_to_the_foreground(self):
        table = night.luminance_map("contrast", "#ffd700")
        self.assertEqual(table[255], (255, 215, 0))

    def test_contrast_maps_page_black_to_black(self):
        table = night.luminance_map("contrast", "#ffd700")
        self.assertEqual(table[0], (0, 0, 0))

    def test_contrast_midpoint_is_half_the_foreground(self):
        table = night.luminance_map("contrast", "#ff0000")
        self.assertEqual(table[128], (128, 0, 0))

    def test_contrast_follows_an_invalid_foreground_back_to_the_default(self):
        table = night.luminance_map("contrast", "not-a-colour")
        self.assertEqual(table[255], (255, 215, 0))


class GSettingsCase(unittest.TestCase):
    def test_get_true(self):
        self.assertEqual(night.effect_from_gsettings_get("true\n"), "contrast")

    def test_get_false(self):
        self.assertEqual(night.effect_from_gsettings_get("false\n"), "off")

    def test_get_garbage_is_off(self):
        self.assertEqual(night.effect_from_gsettings_get(""), "off")
        self.assertEqual(night.effect_from_gsettings_get("maybe"), "off")

    def test_monitor_line_true(self):
        self.assertEqual(night.effect_from_gsettings_monitor("night-mode: true"), "contrast")

    def test_monitor_line_false(self):
        self.assertEqual(night.effect_from_gsettings_monitor("night-mode: false"), "off")

    def test_monitor_ignores_other_keys(self):
        self.assertIsNone(night.effect_from_gsettings_monitor("theme: dark"))
        self.assertIsNone(night.effect_from_gsettings_monitor(""))

    def test_monitor_line_with_no_value_is_off(self):
        self.assertEqual(night.effect_from_gsettings_monitor("night-mode:"), "off")


if __name__ == "__main__":
    unittest.main()
