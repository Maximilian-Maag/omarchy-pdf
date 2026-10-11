#!/bin/bash
# Shell tests for bin/omarchy-pdf-sign — plain bash, no bats.
#
# Stub `xdg-open` and `omarchy-notification-send` on PATH record what the command
# did, so the portal URL, the reminder text and the validation path are observable
# and no browser is actually launched.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/bin/omarchy-pdf-sign"
ORIG_PATH="$PATH"
PORTAL="https://www.sign-me.de/"

FAIL=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

BIN="$TMP/bin"
OPEN_LOG="$TMP/xdg-open.log"
NOTIFY_LOG="$TMP/notify.log"
mkdir -p "$BIN"
cat > "$BIN/xdg-open" <<'STUB'
#!/bin/bash
echo "$*" >> "$XDG_OPEN_LOG"
exit 0
STUB
chmod 755 "$BIN/xdg-open"
cat > "$BIN/omarchy-notification-send" <<'STUB'
#!/bin/bash
echo "$*" >> "$NOTIFY_LOG"
exit 0
STUB
chmod 755 "$BIN/omarchy-notification-send"

run_cli() { PATH="$BIN:$ORIG_PATH" XDG_OPEN_LOG="$OPEN_LOG" NOTIFY_LOG="$NOTIFY_LOG" bash "$CLI" "$@"; }
reset() { rm -f "$OPEN_LOG" "$NOTIFY_LOG"; }
opened() { cat "$OPEN_LOG" 2>/dev/null; }

# ── no file: opens the portal, exits 0, reminds the user to upload ─────────
reset; run_cli >/dev/null; rc=$?
(( rc == 0 )) && pass "no file exits 0" || fail "no file must exit 0 (got $rc)"
[[ "$(opened)" == "$PORTAL" ]] && pass "no file opens the sign-me portal" || fail "no file opens the sign-me portal (got '$(opened)')"
grep -qF 'Portal geoeffnet' "$NOTIFY_LOG" 2>/dev/null \
  && pass "no file reminds the user to upload" || fail "no file reminds the user to upload"

# ── an existing file: opens the portal and names the document ──────────────
reset; printf 'x' > "$TMP/Vertrag.pdf"
run_cli "$TMP/Vertrag.pdf" >/dev/null; rc=$?
(( rc == 0 )) && pass "an existing file exits 0" || fail "an existing file must exit 0 (got $rc)"
[[ "$(opened)" == "$PORTAL" ]] && pass "an existing file opens the portal" || fail "an existing file opens the portal (got '$(opened)')"
grep -qF 'Vertrag.pdf' "$NOTIFY_LOG" 2>/dev/null \
  && pass "an existing file names the document" || fail "an existing file names the document"

# ── a missing file: refused, and nothing is opened ─────────────────────────
reset; ERR="$TMP/stderr"
run_cli "$TMP/does-not-exist.pdf" 2>"$ERR"; rc=$?
(( rc == 1 )) && pass "a missing file exits 1" || fail "a missing file must exit 1 (got $rc)"
[[ -z "$(opened)" ]] && pass "a missing file opens nothing" || fail "a missing file must open nothing"
grep -qF 'no such file' "$ERR" && pass "a missing file explains itself" || fail "a missing file explains itself"

exit "$FAIL"
