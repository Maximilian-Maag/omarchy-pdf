#!/bin/bash
# e2e: drive bin/omarchy-toggle-pdf-night against the REAL GSettings schema
# (org.gnome.Papers) using an isolated keyfile backend, so a genuine schema
# round-trip is proven while the user's own dconf is left untouched.
#
# The schema ships with Papers; on a host without it the check is skipped rather
# than failed (an e2e about a specific schema cannot fabricate the schema).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/bin/omarchy-toggle-pdf-night"

FAIL=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=1; }

if ! gsettings list-schemas 2>/dev/null | grep -qx 'org.gnome.Papers'; then
  echo "skip: the org.gnome.Papers schema is not installed on this host"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export XDG_CONFIG_HOME="$TMP/config"
export GSETTINGS_BACKEND=keyfile
mkdir -p "$XDG_CONFIG_HOME"

gread() { GSETTINGS_BACKEND=keyfile gsettings get org.gnome.Papers night-mode; }
run_cli() { XDG_CONFIG_HOME="$XDG_CONFIG_HOME" GSETTINGS_BACKEND=keyfile bash "$CLI" "$@"; }

# start from a known state via the real schema
GSETTINGS_BACKEND=keyfile gsettings set org.gnome.Papers night-mode false

run_cli on >/dev/null
[[ "$(gread)" == "true" ]] && pass "on flips the real schema value to true" || fail "on flips the real schema value to true (got $(gread))"

run_cli off >/dev/null
[[ "$(gread)" == "false" ]] && pass "off flips the real schema value back to false" || fail "off flips the real schema value to false (got $(gread))"

out="$(run_cli --status)"
[[ $out == '{"mode":"night","enabled":false}' ]] \
  && pass "--status reads the real value via gsettings" \
  || fail "--status reads the real value via gsettings (got '$out')"

run_cli toggle >/dev/null
[[ "$(gread)" == "true" ]] && pass "toggle flips the real schema value" || fail "toggle flips the real schema value (got $(gread))"

exit "$FAIL"
