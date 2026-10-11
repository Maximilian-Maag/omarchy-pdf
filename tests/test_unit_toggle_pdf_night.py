"""Unit tests: bin/omarchy-toggle-pdf-night's argument handling and status readout.

The CLI is a bash script, so it is exercised as a subprocess with a stateful
`gsettings` stub and a stub notification sender on PATH. The stub records every
read/write, so the exact schema key and value are observable and the user's real
dconf is never touched.
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

NOTIFY_STUB = """#!/bin/bash
echo "$*" >> "$NOTIFY_LOG"
exit 0
"""


def write_stub(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class TogglePdfNightUnitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-unit-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.log = self.tmp / "gsettings.log"
        self.notify = self.tmp / "notify.log"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        write_stub(self.bin / "gsettings", GSETTINGS_STUB)
        write_stub(self.bin / "omarchy-notification-send", NOTIFY_STUB)

    def run_cli(self, *args):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["GSET_LOG"] = str(self.log)
        env["GSET_STATE"] = str(self.state)
        env["NOTIFY_LOG"] = str(self.notify)
        return subprocess.run(["bash", str(CLI), *args], env=env, cwd=str(REPO),
                              capture_output=True, text=True)

    def set_state(self, value):
        self.state.write_text(value)

    def log_text(self):
        return self.log.read_text() if self.log.exists() else ""

    def set_calls(self):
        return [ln for ln in self.log_text().splitlines()
                if ln.startswith("set org.gnome.Papers night-mode")]

    def last_set(self):
        calls = self.set_calls()
        return calls[-1].split()[-1] if calls else None

    def reset(self):
        for p in (self.state, self.log, self.notify):
            if p.exists():
                p.unlink()

    # ── dispatch ──────────────────────────────────────────────────────────
    def test_on_writes_true(self):
        self.assertEqual(self.run_cli("on").returncode, 0)
        self.assertEqual(self.last_set(), "true")

    def test_off_writes_false(self):
        self.assertEqual(self.run_cli("off").returncode, 0)
        self.assertEqual(self.last_set(), "false")

    def test_toggle_from_false_writes_true(self):
        self.set_state("false")
        self.assertEqual(self.run_cli("toggle").returncode, 0)
        self.assertEqual(self.last_set(), "true")

    def test_toggle_from_true_writes_false(self):
        self.set_state("true")
        self.assertEqual(self.run_cli("toggle").returncode, 0)
        self.assertEqual(self.last_set(), "false")

    def test_no_argument_defaults_to_toggle(self):
        self.set_state("true")
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.last_set(), "false")

    def test_reads_and_writes_only_its_own_key(self):
        # `on` writes directly; `toggle` reads the current value and writes it back.
        self.set_state("false")
        self.run_cli("toggle")
        joined = " ".join(self.log_text().splitlines())
        self.assertIn("get org.gnome.Papers night-mode", joined)
        self.assertIn("set org.gnome.Papers night-mode true", joined)

    # ── validation ────────────────────────────────────────────────────────
    def test_invalid_action_exits_1_with_usage_and_no_write(self):
        proc = self.run_cli("blink")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Usage:", proc.stderr)
        self.assertEqual(self.set_calls(), [])

    # ── status ────────────────────────────────────────────────────────────
    def test_status_false_when_unset(self):
        proc = self.run_cli("--status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"mode": "night", "enabled": False})

    def test_status_true_when_the_value_is_true(self):
        self.set_state("true")
        data = json.loads(self.run_cli("--status").stdout)
        self.assertEqual(data, {"mode": "night", "enabled": True})

    def test_status_never_writes(self):
        self.run_cli("--status")
        self.assertEqual(self.set_calls(), [])

    # ── notification ──────────────────────────────────────────────────────
    def test_enabling_notifies_dark(self):
        self.run_cli("on")
        self.assertIn("Dunkelmodus", self.notify.read_text())

    def test_disabling_notifies_light(self):
        self.run_cli("off")
        self.assertIn("Hellmodus", self.notify.read_text())

    def test_no_notification_for_status(self):
        self.run_cli("--status")
        self.assertFalse(self.notify.exists())


if __name__ == "__main__":
    unittest.main()
