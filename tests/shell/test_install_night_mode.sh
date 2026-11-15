#!/bin/bash
# Shell tests for install.sh's night-mode step.
#
# Bug pinned: install.sh ran `gsettings set … 2>/dev/null || true` and then
# unconditionally printed "Papers night mode enabled by default.", so a failed
# write (no dconf daemon, wrong schema) still claimed success.
#
# install.sh is a privileged installer, so the test runs the REAL script in a
# sandbox: `sudo`/`pkexec` are stubbed no-ops (nothing is written outside $TMP),
# destinations come from XDG_* + HOME, the shim build is disabled with a bogus
# $CXX, and a stateful `gsettings` stub decides whether the write succeeds.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL="$ROOT/install.sh"

FAIL=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/home" "$TMP/config" "$TMP/data"

# privileged helpers become no-ops so the script runs unprivileged, and the
# shim build never compiles (a failing $CXX makes that step report a warning).
for tool in sudo pkexec; do
  printf '#!/bin/bash\nexit 0\n' > "$TMP/bin/$tool"
  chmod 755 "$TMP/bin/$tool"
done

# `gsettings set` returns whatever $GSET_RC says; every call is logged.
cat > "$TMP/bin/gsettings" <<'STUB'
#!/bin/bash
echo "$*" >> "$GSET_LOG"
exit "${GSET_RC:-0}"
STUB
chmod 755 "$TMP/bin/gsettings"

run_install() { # GSET_RC
  HOME="$TMP/home" \
  XDG_CONFIG_HOME="$TMP/config" \
  XDG_DATA_HOME="$TMP/data" \
  PATH="$TMP/bin:$PATH" \
  GSET_RC="$1" \
  GSET_LOG="$TMP/gsettings.log" \
  CXX=/bin/false \
    bash "$INSTALL" 2>&1
}

# ── a successful write claims success ─────────────────────────────────────
out="$(run_install 0)"
grep -qF 'Papers night mode enabled by default.' <<<"$out" \
  && pass "a successful gsettings write prints the success line" \
  || fail "a successful gsettings write must print the success line (got: $out)"
grep -qiF 'could not set Papers night mode' <<<"$out" \
  && fail "no failure warning when the write succeeded" \
  || pass "no failure warning when the write succeeded"
grep -qF 'set org.gnome.Papers night-mode true' "$TMP/gsettings.log" 2>/dev/null \
  && pass "install.sh writes the night-mode key" \
  || fail "install.sh must write the night-mode key"

# ── a failed write must NOT claim success ─────────────────────────────────
rm -f "$TMP/gsettings.log"
out="$(run_install 1)"
grep -qF 'Papers night mode enabled by default.' <<<"$out" \
  && fail "a FAILED gsettings write must not print the success line" \
  || pass "a failed gsettings write does not print the success line"
grep -qiF 'could not set Papers night mode' <<<"$out" \
  && pass "a failed gsettings write warns instead" \
  || fail "a failed gsettings write must warn (got: $out)"

echo "shell: install night mode checks done"
exit "$FAIL"
