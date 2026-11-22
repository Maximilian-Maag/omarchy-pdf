#!/bin/bash
# Shell tests for bin/omarchy-webapp-qutebrowser — plain bash, no bats.
#
# A stub `qutebrowser` on PATH records how it was invoked, so both the
# no-argument fallback and the --target window form are observable, and the
# real browser is never started.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/bin/omarchy-webapp-qutebrowser"
ORIG_PATH="$PATH"

FAIL=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

BIN="$TMP/bin"
LOG="$TMP/qutebrowser.log"
mkdir -p "$BIN"
cat > "$BIN/qutebrowser" <<'STUB'
#!/bin/bash
echo "$*" >> "$QB_LOG"
exit 0
STUB
chmod 755 "$BIN/qutebrowser"

run_cli() { PATH="$BIN:$ORIG_PATH" QB_LOG="$LOG" bash "$CLI" "$@"; }
reset() { rm -f "$LOG"; }
calls() { cat "$LOG" 2>/dev/null; }

# ── --dry-run prints the resolved command and never launches ───────────────
reset; out="$(run_cli --app=https://example.com --dry-run)"; rc=$?
(( rc == 0 )) && pass "dry run exits 0" || fail "dry run must exit 0 (got $rc)"
[[ $out == 'qutebrowser --target window https://example.com' ]] \
  && pass "dry run prints the target-window command" \
  || fail "dry run prints the target-window command (got '$out')"
[[ -z "$(calls)" ]] && pass "dry run never launches qutebrowser" || fail "dry run must not launch qutebrowser"

# the app URL is taken from --app= verbatim, not from position
reset; out="$(run_cli --app=https://a.example/x?a=1 --dry-run)"
[[ $out == 'qutebrowser --target window https://a.example/x?a=1' ]] \
  && pass "--app value is honoured verbatim" || fail "--app value is honoured verbatim (got '$out')"

# ── a URL launches qutebrowser in a dedicated window ──────────────────────
reset; run_cli --app=https://example.com
[[ "$(calls)" == '--target window https://example.com' ]] \
  && pass "a URL launches qutebrowser --target window <url>" \
  || fail "a URL launches qutebrowser --target window <url> (got '$(calls)')"

# ── a clicked link (bare URL) opens as a TAB, not a window ────────────────
# The desktop hands a link to this shim as a plain argument: xdg-open and the
# portal append it to the entry's Exec, and omarchy-launch-browser passes its
# own argv through. Treating only --app= as a URL dropped it and opened the
# start page in a fresh window, which is the bug this test pins.
reset; run_cli https://example.org/some/path?q=1
[[ "$(calls)" == '--target tab https://example.org/some/path?q=1' ]] \
  && pass "a bare URL opens as a tab in the running window" \
  || fail "a bare URL opens as a tab (got '$(calls)')"

reset; out="$(run_cli https://example.org --dry-run)"
[[ $out == 'qutebrowser --target tab https://example.org' ]] \
  && pass "dry run prints the tab command for a link" \
  || fail "dry run prints the tab command for a link (got '$out')"

# the space-separated form of --app is the same web-app request
reset; out="$(run_cli --app https://app.example/ --dry-run)"
[[ $out == 'qutebrowser --target window https://app.example/' ]] \
  && pass "--app <url> is a web-app window too" \
  || fail "--app <url> is a web-app window too (got '$out')"

# an unrelated flag is not mistaken for the URL, and the URL after it survives
reset; run_cli --some-flag https://example.org/x
[[ "$(calls)" == '--target tab https://example.org/x' ]] \
  && pass "an unrelated flag is skipped, the URL after it is opened" \
  || fail "an unrelated flag is skipped (got '$(calls)')"

# only the first bare argument is a URL; a second one does not overwrite it
reset; out="$(run_cli https://first.example https://second.example --dry-run)"
[[ $out == 'qutebrowser --target tab https://first.example' ]] \
  && pass "the first bare URL wins" \
  || fail "the first bare URL wins (got '$out')"

# ── no URL falls back to a plain launch (no empty window argument) ─────────
reset; run_cli
[[ -f "$LOG" ]] && pass "a plain launch invokes qutebrowser" || fail "a plain launch must invoke qutebrowser"
[[ "$(calls)" == "" ]] && pass "a plain launch passes no arguments" || fail "a plain launch passes no arguments (got '$(calls)')"

exit "$FAIL"
