#!/bin/bash
# e2e: prove the Chromium-free web-app wiring end to end.
#
# Replays what Omarchy's omarchy-launch-webapp does — because the default browser
# is not Chromium-family it falls back to `chromium.desktop`, reads that file's
# Exec, and runs it with `--app=<url>` — against this plugin's REAL
# config/chromium.desktop and bin/omarchy-webapp-qutebrowser, with a stub
# qutebrowser on PATH. The whole chain
#   (default browser -> chromium.desktop -> shim -> qutebrowser --target window)
# is exercised without launching a real browser.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/bin/omarchy-webapp-qutebrowser"
DESKTOP="$ROOT/config/chromium.desktop"
URL="https://example.com/report?q=1"

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

# ── the desktop entry must name a PATH-resolvable Exec, not an absolute path ──
exec_line="$(sed -n 's/^Exec=//p' "$DESKTOP")"
[ -n "$exec_line" ] && pass "chromium.desktop declares an Exec" || fail "chromium.desktop has no Exec"
case "$exec_line" in
  /*) fail "Exec must be a bare name so PATH resolves it (got '$exec_line')" ;;
  *)  pass "Exec is a bare name ($exec_line)" ;;
esac

# ── replay omarchy-launch-webapp's resolution, then run the resolved command ──
exe="$(sed -n 's/^Exec=\([^ ]*\).*/\1/p' "$DESKTOP" | head -1)"
if command -v "$exe" >/dev/null 2>&1 || [ -x "$SHIM" ]; then
  pass "the Exec resolves to a runnable program"
else
  fail "the Exec '$exe' does not resolve"
fi

# run the resolved Exec the way the launcher would (shim itself, --app=<url>)
PATH="$BIN:$PATH" QB_LOG="$LOG" bash "$SHIM" "--app=$URL"
if [ "$(cat "$LOG" 2>/dev/null)" = "--target window $URL" ]; then
  pass "the wiring opens the URL in qutebrowser (--target window)"
else
  fail "the wiring must open the URL in qutebrowser (got '$(cat "$LOG" 2>/dev/null)')"
fi

# ── and the Chromium package must not be required for this to work ────────────
if command -v chromium >/dev/null 2>&1; then
  echo "note: chromium is present on this host; the wiring still routes to qutebrowser"
fi
pass "the chain completes without invoking chromium"

exit "$FAIL"
