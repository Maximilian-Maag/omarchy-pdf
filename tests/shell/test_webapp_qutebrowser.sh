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

# ── no URL falls back to a plain launch (no empty window argument) ─────────
reset; run_cli
[[ -f "$LOG" ]] && pass "a plain launch invokes qutebrowser" || fail "a plain launch must invoke qutebrowser"
[[ "$(calls)" == "" ]] && pass "a plain launch passes no arguments" || fail "a plain launch passes no arguments (got '$(calls)')"

exit "$FAIL"
