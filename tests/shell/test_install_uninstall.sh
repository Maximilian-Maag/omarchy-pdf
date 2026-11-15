#!/bin/bash
# install.sh --uninstall: it must remove EXACTLY what install added, and nothing else.
#
# The contract, in order of what it protects:
#   * a full install -> uninstall round-trip leaves the user's own config byte-identical
#     (the keybindings block it appended is taken back out by exact content, so the file
#     comes back with the same sha256 it had before);
#   * our artifacts are gone afterwards (bin tools, desktop entries, the share tree, the
#     recorded handler);
#   * a file, a symlink or a mime default that is NOT ours is left alone;
#   * the assertions are load-bearing: if a removal is reverted, the leftover is caught.
#
# install.sh is a privileged installer, so the test runs the REAL script in a sandbox:
# sudo/pkexec are passthrough stubs and the two privileged directories are redirected with
# OMARCHY_PDF_BIN_DIR / OMARCHY_PDF_SHARE_DIR, so nothing is written outside $TMP.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL="$ROOT/install.sh"

pass=0
fail=0
ok()  { pass=$((pass + 1)); printf '  PASS: %s\n' "$1"; }
no()  { fail=$((fail + 1)); printf '  FAIL: %s\n' "$1"; }
check() { # check <name> <expected> <actual>
  if [[ $2 == "$3" ]]; then ok "$1"; else no "$1 (expected: $2, actual: $3)"; fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export XDG_CONFIG_HOME="$TMP/config"
export XDG_DATA_HOME="$TMP/data"
export XDG_STATE_HOME="$TMP/state"
BIN_DIR="$TMP/bin"
SHARE_DIR="$TMP/share"
APP_DIR="$XDG_DATA_HOME/applications"
BINDINGS="$XDG_CONFIG_HOME/hypr/bindings.lua"
XDM_STATE="$TMP/mimeapps.list"
export XDM_STATE
mkdir -p "$HOME" "$XDG_CONFIG_HOME/hypr" "$BIN_DIR" "$TMP/stub"

# ── stubs ─────────────────────────────────────────────────────────────────────
# sudo/pkexec become passthroughs: the script's `sudo bash -c "…"` really runs, but only
# ever against the redirected $BIN_DIR/$SHARE_DIR.
for tool in sudo pkexec; do
  printf '#!/bin/bash\nexec "$@"\n' > "$TMP/stub/$tool"
  chmod 755 "$TMP/stub/$tool"
done
printf '#!/bin/bash\nexit 0\n' > "$TMP/stub/gsettings"
printf '#!/bin/bash\nexit 0\n' > "$TMP/stub/hyprctl"
printf '#!/bin/bash\nexit 0\n' > "$TMP/stub/update-desktop-database"
printf '#!/bin/bash\nexit 0\n' > "$TMP/stub/papers"
chmod 755 "$TMP"/stub/*
# A stateful xdg-mime: `query default <mime>` reads XDM_STATE, `default <entry> <mime>`
# writes it — enough to observe the reversion end to end.
cat > "$TMP/stub/xdg-mime" <<'STUB'
#!/bin/bash
: "${XDM_STATE:?}"
case "$1" in
  query)
    mime="${3:-}"
    [ -f "$XDM_STATE" ] && awk -F= -v m="$mime" '$1 == m { print $2 }' "$XDM_STATE" | head -1
    ;;
  default)
    entry="$2"; mime="$3"; tmpf="${XDM_STATE}.$$"
    if [ -f "$XDM_STATE" ]; then grep -v -F "$mime=" "$XDM_STATE" > "$tmpf" || true; fi
    printf '%s=%s\n' "$mime" "$entry" >> "$tmpf"
    mv "$tmpf" "$XDM_STATE"
    ;;
esac
exit 0
STUB
chmod 755 "$TMP/stub/xdg-mime"

run_install() { # run_install [install-script]
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  XDG_STATE_HOME="$XDG_STATE_HOME" OMARCHY_PDF_BIN_DIR="$BIN_DIR" OMARCHY_PDF_SHARE_DIR="$SHARE_DIR" \
  CXX=/bin/false PATH="$TMP/stub:$PATH" \
    bash "${1:-$INSTALL}" 2>&1
}
run_uninstall() { # run_uninstall [install-script]
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  XDG_STATE_HOME="$XDG_STATE_HOME" OMARCHY_PDF_BIN_DIR="$BIN_DIR" OMARCHY_PDF_SHARE_DIR="$SHARE_DIR" \
  CXX=/bin/false PATH="$TMP/stub:$PATH" \
    bash "${1:-$INSTALL}" --uninstall 2>&1
}

BIN_TOOLS=(omarchy-pdf omarchy-pdf-qtpdf-compat omarchy-toggle-pdf-night omarchy-webapp-qutebrowser omarchy-pdf-sign)
DESKTOP_ENTRIES=(sign-me-qes.desktop chromium.desktop omarchy-pdf.desktop)

# ── the user's own config, before anything runs ───────────────────────────────
printf 'require("default.hypr.omarchy")\nlocal monitors = {}\n' > "$BINDINGS"
before="$(sha256sum "$BINDINGS" | cut -d' ' -f1)"
# A foreign PDF handler in place before install: the round-trip must restore it.
printf 'application/pdf=org.gnome.Papers.desktop\n' > "$XDM_STATE"

printf 'install/uninstall round-trip\n'

out="$(run_install)"; rc=$?
check "installing succeeds" "0" "$rc"

# ── install actually landed the artifacts (so the round-trip is meaningful) ───
landed=0
for t in "${BIN_TOOLS[@]}"; do [[ -f $BIN_DIR/$t ]] || landed=1; done
check "install lands every bin tool" "0" "$landed"
check "a bin tool is a byte-identical copy of our source" "0" \
      "$(cmp -s "$BIN_DIR/omarchy-pdf" "$ROOT/bin/omarchy-pdf" && echo 0 || echo 1)"
e=0; for d in "${DESKTOP_ENTRIES[@]}"; do [[ -f $APP_DIR/$d ]] || e=1; done
check "install lands every desktop entry" "0" "$e"
check "install lands the share tree" "yes" "$([[ -d $SHARE_DIR/pdf ]] && echo yes || echo no)"
check "install appends the keybindings block" "yes" \
      "$(grep -qF -- '-- omarchy-pdf plugin' "$BINDINGS" && echo yes || echo no)"
check "install records the previous handler and claims the mime" "omarchy-pdf.desktop" \
      "$(awk -F= '$1=="application/pdf"{print $2}' "$XDM_STATE")"

# ── uninstall ─────────────────────────────────────────────────────────────────
out="$(run_uninstall)"; rc=$?
check "uninstalling succeeds" "0" "$rc"

left=0
for t in "${BIN_TOOLS[@]}"; do [[ -e $BIN_DIR/$t ]] && left=1; done
check "every bin tool is gone" "0" "$left"
e=0; for d in "${DESKTOP_ENTRIES[@]}"; do [[ -e $APP_DIR/$d ]] && e=1; done
check "every desktop entry is gone" "0" "$e"
check "the share tree is gone" "no" "$([[ -e $SHARE_DIR ]] && echo yes || echo no)"
check "the recorded state is gone" "no" "$([[ -e $XDG_STATE_HOME/omarchy-pdf ]] && echo yes || echo no)"

# The byte-identity guarantee.
check "the user's bindings.lua is byte-identical after the round-trip" "$before" \
      "$(sha256sum "$BINDINGS" | cut -d' ' -f1)"
check "no marker is left behind to stack up" "0" \
      "$(grep -c -- '-- omarchy-pdf plugin' "$BINDINGS" | tr -d ' ')"
check "the user's own lines survived the edit" 'require("default.hypr.omarchy")' \
      "$(grep -h require "$BINDINGS")"

# The mime default is reverted only because it was still ours.
check "the PDF handler is reverted to the previous one" "org.gnome.Papers.desktop" \
      "$(awk -F= '$1=="application/pdf"{print $2}' "$XDM_STATE")"

# A second cycle does not accumulate a marker either.
run_install >/dev/null 2>&1
run_uninstall >/dev/null 2>&1
check "a second round-trip leaves bindings.lua byte-identical again" "$before" \
      "$(sha256sum "$BINDINGS" | cut -d' ' -f1)"

printf 'foreign files, links and mime defaults are left alone\n'

# A foreign regular file at our bin path: not byte-identical, so not ours.
printf '#!/bin/sh\necho not ours\n' > "$BIN_DIR/omarchy-pdf"
run_uninstall >/dev/null 2>&1
check "a foreign file at our bin path is left alone" "yes" \
      "$([[ -f $BIN_DIR/omarchy-pdf ]] && echo yes || echo no)"

# A foreign symlink at our bin path, pointing somewhere else.
ln -sfn /bin/true "$BIN_DIR/omarchy-toggle-pdf-night"
run_uninstall >/dev/null 2>&1
check "a foreign symlink at our bin path is left alone" "/bin/true" \
      "$(readlink "$BIN_DIR/omarchy-toggle-pdf-night")"
rm -f "$BIN_DIR/omarchy-pdf" "$BIN_DIR/omarchy-toggle-pdf-night"

# A foreign desktop entry at our name.
printf '[Desktop Entry]\nName=someone elses\n' > "$APP_DIR/omarchy-pdf.desktop"
run_uninstall >/dev/null 2>&1
check "a foreign desktop entry at our name is left alone" "yes" \
      "$([[ -f $APP_DIR/omarchy-pdf.desktop ]] && echo yes || echo no)"
rm -f "$APP_DIR/omarchy-pdf.desktop"

# A bindings file that never held our block must not be rewritten at all.
printf 'require("default.hypr.omarchy")\n' > "$BINDINGS"
untouched="$(sha256sum "$BINDINGS" | cut -d' ' -f1)"
run_uninstall >/dev/null 2>&1
check "a bindings file without our block is not rewritten" "$untouched" \
      "$(sha256sum "$BINDINGS" | cut -d' ' -f1)"

# A foreign handler: uninstall must not touch it.
printf 'application/pdf=org.gnome.Evince.desktop\n' > "$XDM_STATE"
run_uninstall >/dev/null 2>&1
check "a foreign mime default is left alone" "org.gnome.Evince.desktop" \
      "$(awk -F= '$1=="application/pdf"{print $2}' "$XDM_STATE")"

printf 'the assertions are load-bearing\n'

# Revert one removal and prove the round-trip notices: with the rm in remove_installed
# neutralised, the artifact survives, which is exactly what "every bin tool is gone" checks.
# The copy lives beside symlinks to the real sources so its PLUGIN_DIR still resolves.
SABDIR="$TMP/sab"; mkdir -p "$SABDIR"
for d in bin config pdf tools shim; do ln -sfn "$ROOT/$d" "$SABDIR/$d"; done
SAB="$SABDIR/install.sh"
sed 's|priv rm -f "\$dest"|: ; echo "  (removal sabotaged)"|' "$INSTALL" > "$SAB"
printf 'require("default.hypr.omarchy")\n' > "$BINDINGS"
run_install "$SAB" >/dev/null 2>&1
run_uninstall "$SAB" >/dev/null 2>&1
if [[ -e $BIN_DIR/omarchy-pdf ]]; then
  ok "a reverted removal leaves the artifact behind (the check would fail, as it must)"
else
  no "a reverted removal left nothing behind — the check is not load-bearing"
fi
rm -rf "$BIN_DIR"/* "$SHARE_DIR" 2>/dev/null || true

printf 'install/uninstall: %d passed, %d failed\n' "$pass" "$fail"
(( fail == 0 ))
