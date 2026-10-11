"""Integration tests: bin/omarchy-toggle-pdf-night round-tripping through a
persistent settings backend.

A stateful `gsettings` stub stores the value it is told and serves it back on the
next `get`, which is exactly the read-after-write contract the command depends on.
The sequences below therefore exercise the full command -> store -> read-back path
(including --status) without touching the user's real configuration.
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

PERSISTENT_STUB = """#!/bin/bash
# Persists whatever `set` is told and serves it back on `get`, like GSettings does.
case "$1" in
  get) cat "$GSET_STATE" 2>/dev/null || echo false ;;
  set) printf '%s' "$4" > "$GSET_STATE" ;;
esac
exit 0
"""


class TogglePdfNightIntegrationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-int-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "gsettings"
        stub.write_text(PERSISTENT_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def run_cli(self, *args):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["GSET_STATE"] = str(self.state)
        return subprocess.run(["bash", str(CLI), *args], env=env, cwd=str(REPO),
                              capture_output=True, text=True)

    def enabled(self):
        proc = self.run_cli("--status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["enabled"]

    def test_on_then_off_round_trips(self):
        self.assertFalse(self.enabled())
        self.assertEqual(self.run_cli("on").returncode, 0)
        self.assertTrue(self.enabled())
        self.assertEqual(self.run_cli("off").returncode, 0)
        self.assertFalse(self.enabled())

    def test_toggle_is_its_own_inverse(self):
        self.run_cli("toggle")
        self.assertTrue(self.enabled())
        self.run_cli("toggle")
        self.assertFalse(self.enabled())
        self.run_cli("toggle")
        self.assertTrue(self.enabled())

    def test_on_is_idempotent(self):
        self.run_cli("on")
        self.run_cli("on")
        self.assertTrue(self.enabled())

    def test_status_reads_the_persisted_value_after_a_prior_write(self):
        self.run_cli("off")
        self.assertFalse(self.enabled())
        self.run_cli("on")
        self.assertTrue(self.enabled())


if __name__ == "__main__":
    unittest.main()
