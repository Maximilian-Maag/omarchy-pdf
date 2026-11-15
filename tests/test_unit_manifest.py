"""Unit tests: manifest.json — the plugin's declared install surface.

Bug pinned: omarchy_meta.installPaths listed bin/omarchy-pdf but not the
bin/omarchy-pdf-qtpdf-compat helper that omarchy-pdf execs, so a package built
from the manifest would ship a launcher whose helper is missing.

The rule enforced here: every helper this repo actually invokes — a bin/ script
named anywhere in bin/ or in install.sh — must be declared in installPaths.
"""
import json
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO / "manifest.json"
BIN = REPO / "bin"


class InstallPathsCase(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())
        paths = self.manifest["omarchy_meta"]["installPaths"]
        self.sources = {entry["source"] for entry in paths}
        self.bin_names = {p.name for p in BIN.iterdir() if p.is_file()}

    def _referenced_helpers(self) -> set[str]:
        """Helpers named in the shipped scripts that really live in bin/."""
        text = "\n".join((BIN / name).read_text(errors="replace")
                         for name in sorted(self.bin_names))
        text += (REPO / "install.sh").read_text(errors="replace")
        named = set(re.findall(r"\bomarchy-[a-z0-9-]+", text))
        # system commands (omarchy-launch-webapp, omarchy-notification-send) are
        # not shipped by this plugin, so only bin/ residents are required.
        return {name for name in named if name in self.bin_names}

    def test_every_referenced_helper_is_installed(self):
        missing = {f"bin/{name}" for name in self._referenced_helpers()} - self.sources
        self.assertEqual(missing, set(),
                         "helpers invoked by the plugin but not in installPaths")

    def test_the_qtpdf_compat_helper_is_listed(self):
        # the exact regression: omarchy-pdf execs bin/omarchy-pdf-qtpdf-compat
        self.assertIn("bin/omarchy-pdf-qtpdf-compat", self.sources)

    def test_every_installed_source_exists(self):
        for src in self.sources:
            self.assertTrue((REPO / src).is_file(), f"{src} does not exist")


if __name__ == "__main__":
    unittest.main()
