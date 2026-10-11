#!/bin/bash
# Shell tests for bin/omarchy-toggle-pdf-night — plain bash, no bats.
#
# The CLI is run with a stateful `gsettings` stub on PATH, so the exact schema/key/
# value it reads and writes is observable and the user's real dconf is never touched.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/bin/omarchy-toggle-pdf-night"
ORIG_PATH="$PATH"

FAIL=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

BIN="$TMP/bin"
STATE="$TMP/state"          # the stub's stored value
LOG="$TMP/gsettings.log"    # every gsettings invocation
NOTIFY_LOG="$TMP/notify.log"
mkdir -p "$BIN"

# stateful gsettings stub: `get` echoes the stored value, `set` stores arg 4.
cat > "$BIN/gsettings" <<'STUB'
#!/bin/bash
echo "$*" >> "$GSET_LOG"
case "$1" in
  get) cat "$GSET_STATE" 2>/dev/null || echo false ;;
  set) printf '%s' "$4" > "$GSET_STATE" ;;
esac
exit 0
STUB
chmod 755 "$BIN/gsettings"

# every notification is recorded, so we can assert notify() really ran.
cat > "$BIN/omarchy-notification-send" <<'STUB'
#!/bin/bash
echo "$*" >> "$NOTIFY_LOG"
exit 0
STUB
chmod 755 "$BIN/omarchy-notification-send"

run_cli() { # args...
  PATH="$BIN:$ORIG_PATH" GSET_LOG="$LOG" GSET_STATE="$STATE" NOTIFY_LOG="$NOTIFY_LOG" \
    bash "$CLI" "$@"
}
reset() { rm -f "$STATE" "$LOG" "$NOTIFY_LOG"; }
state_val() { cat "$STATE" 2>/dev/null; }
set_calls() { grep -F 'set org.gnome.Papers night-mode' "$LOG" 2>/dev/null; }
last_set() { set_calls | tail -1 | awk '{print $NF}'; }

# ── dispatch: explicit on/off ─────────────────────────────────────────────
reset; run_cli on >/dev/null
[[ "$(last_set)" == "true" ]] && pass "on sets night-mode true" || fail "on sets night-mode true (got '$(last_set)')"

reset; run_cli off >/dev/null
[[ "$(last_set)" == "false" ]] && pass "off sets night-mode false" || fail "off sets night-mode false (got '$(last_set)')"

# ── toggle reads the current value and flips it ───────────────────────────
reset; printf 'false' > "$STATE"; run_cli toggle >/dev/null
[[ "$(last_set)" == "true" ]] && pass "toggle from false sets true" || fail "toggle from false sets true (got '$(last_set)')"

reset; printf 'true' > "$STATE"; run_cli toggle >/dev/null
[[ "$(last_set)" == "false" ]] && pass "toggle from true sets false" || fail "toggle from true sets false (got '$(last_set)')"

# bare invocation defaults to toggle
reset; printf 'true' > "$STATE"; run_cli >/dev/null
[[ "$(last_set)" == "false" ]] && pass "no arg defaults to toggle" || fail "no arg defaults to toggle (got '$(last_set)')"

# ── status readout ────────────────────────────────────────────────────────
reset; out="$(run_cli --status)"
[[ $out == '{"mode":"night","enabled":false}' ]] && pass "status with no value is disabled" || fail "status with no value is disabled (got '$out')"
[[ -z "$(set_calls)" ]] && pass "status never writes" || fail "status must not write"

reset; printf 'true' > "$STATE"; out="$(run_cli --status)"
[[ $out == '{"mode":"night","enabled":true}' ]] && pass "status true reports enabled" || fail "status true reports enabled (got '$out')"

# ── validation ────────────────────────────────────────────────────────────
reset; ERR="$TMP/stderr"; run_cli blink 2>"$ERR"; rc=$?
(( rc == 1 )) && pass "an invalid action exits 1" || fail "an invalid action must exit 1 (got $rc)"
grep -qF 'Usage:' "$ERR" && pass "an invalid action prints usage to stderr" || fail "an invalid action prints usage to stderr"
[[ -z "$(set_calls)" ]] && pass "an invalid action never writes" || fail "an invalid action must not write"

# ── notify() is really invoked ────────────────────────────────────────────
reset; run_cli on >/dev/null
grep -qF 'Dunkelmodus' "$NOTIFY_LOG" 2>/dev/null && pass "enabling notifies dark" || fail "enabling notifies dark"
reset; run_cli off >/dev/null
grep -qF 'Hellmodus' "$NOTIFY_LOG" 2>/dev/null && pass "disabling notifies light" || fail "disabling notifies light"

exit "$FAIL"
