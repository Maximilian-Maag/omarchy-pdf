"""Regression tests for bin/omarchy-toggle-pdf-night.

Each test names the bug it pins. The CLI runs as a subprocess against a stateful
`gsettings` stub, so reads and writes are observable.
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO / "bin/omarchy-toggle-pdf-night"

GSETTINGS_STUB = """#!/bin/bash
echo "$*" >> "$GSET_LOG"
case "$1" in
  get) cat "$GSET_STATE" 2>/dev/null || echo false ;;
  set) printf '%s' "$4" > "$GSET_STATE" ;;
esac
exit 0
"""


class TogglePdfNightRegressionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-reg-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.log = self.tmp / "gsettings.log"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "gsettings"
        stub.write_text(GSETTINGS_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def run_cli(self, *args):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["GSET_LOG"] = str(self.log)
        env["GSET_STATE"] = str(self.state)
        return subprocess.run(["bash", str(CLI), *args], env=env, cwd=str(REPO),
                              capture_output=True, text=True)

    def last_set(self):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        sets = [ln for ln in lines if ln.startswith("set org.gnome.Papers night-mode")]
        return sets[-1].split()[-1] if sets else None

    def test_toggle_actually_flips_rather_than_always_enabling(self):
        # Bug pinned: toggle ignored the current value and always wrote true.
        self.state.write_text("true")
        self.run_cli("toggle")
        self.assertEqual(self.last_set(), "false")

    def test_toggle_does_not_double_print_the_value(self):
        # Bug pinned: read_state's `get ... || echo false` was written with `&&`,
        # so a success appended a second line and the comparison misread it.
        self.state.write_text("true")
        self.run_cli("toggle")
        self.assertEqual(self.last_set(), "false")

    def test_status_does_not_write(self):
        # Bug pinned: --status went through the write path and changed the value.
        self.run_cli("--status")
        self.assertEqual(self.last_set(), None)

    def test_invalid_action_is_validated_before_any_write(self):
        # Bug pinned: a bad action fell through and wrote a value anyway.
        proc = self.run_cli("nonsense")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.last_set(), None)

    def test_status_reports_the_stored_value_not_a_constant(self):
        # Bug pinned: --status always reported enabled:false regardless of state.
        self.state.write_text("true")
        self.assertTrue(json.loads(self.run_cli("--status").stdout)["enabled"])


if __name__ == "__main__":
    unittest.main()
