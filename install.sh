#!/bin/bash
# omarchy-pdf install script
# Wires the plugin into the live Omarchy/Hyprland config.
# Safe to re-run — all steps are idempotent.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
HYPR_CONFIG_DIR="$CONFIG_HOME/hypr"
BINDINGS="$HYPR_CONFIG_DIR/bindings.lua"
BIN_DIR="${OMARCHY_PDF_BIN_DIR:-/usr/local/bin}"
SHARE_DIR="${OMARCHY_PDF_SHARE_DIR:-/usr/local/share/omarchy-pdf}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-pdf"
MIME_STATE="$STATE_DIR/mime-application-pdf"

# The exact artifacts install adds. --uninstall reverses these lists and nothing else.
BIN_TOOLS=(omarchy-pdf omarchy-pdf-qtpdf-compat omarchy-toggle-pdf-night omarchy-webapp-qutebrowser omarchy-pdf-sign)
DESKTOP_ENTRIES=(sign-me-qes.desktop chromium.desktop omarchy-pdf.desktop)
PDF_MIME="application/pdf"
PDF_ENTRY="omarchy-pdf.desktop"
BIND_MARKER='-- omarchy-pdf plugin'
BIND_LINES=(
  'o.bind("SUPER + D",         "Documents (omarchy-pdf)",   "/usr/local/bin/omarchy-pdf")'
  'o.bind("SUPER + CTRL + N",  "PDF dark/light toggle",    "/usr/local/bin/omarchy-toggle-pdf-night")'
  'o.bind("SUPER + SHIFT + Q", "sign-me (QES signieren)",  { launch = "qutebrowser --target window https://www.sign-me.de/" })'
)

# Run a command with the privilege install used: root, else sudo, else pkexec.
priv() {
  if (( EUID == 0 )); then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else pkexec "$@"; fi
}

# remove_installed <dest> <source it must match>
# A file is ours only if it is a symlink into this checkout or a byte-identical copy of
# the source install wrote; anything else at that path is somebody else's and is left alone.
remove_installed() {
  local dest="$1" src="$2"
  if [[ -L $dest ]] && [[ "$(readlink -f "$dest")" == "$(readlink -f "$src")" ]]; then
    priv rm -f "$dest"; echo "  Removed $dest"
  elif [[ -f $dest ]] && cmp -s "$src" "$dest"; then
    priv rm -f "$dest"; echo "  Removed $dest"
  elif [[ -e $dest ]]; then
    echo "  WARNING: $dest is not ours — left alone."
  fi
}

uninstall() {
  echo "omarchy-pdf: uninstalling"

  # 2. The helper binaries on PATH.
  local tool
  # The short name first: it is a symlink to omarchy-pdf, so compare before that goes.
  local short="$BIN_DIR/opf"
  if [[ -L $short ]] && [[ "$(readlink -f "$short")" == "$(readlink -f "$BIN_DIR/omarchy-pdf")" ]]; then
    priv rm -f "$short"; echo "  Removed $short"
  fi
  for tool in "${BIN_TOOLS[@]}"; do
    remove_installed "$BIN_DIR/$tool" "$PLUGIN_DIR/bin/$tool"
  done

  # 3. The desktop entries.
  local entry
  for entry in "${DESKTOP_ENTRIES[@]}"; do
    remove_installed "$APP_DIR/$entry" "$PLUGIN_DIR/config/$entry"
  done
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

  # 3b. The package + shim share tree: the path is ours alone, so the whole tree goes.
  if [[ -d $SHARE_DIR ]]; then
    priv rm -rf "$SHARE_DIR"; echo "  Removed $SHARE_DIR"
  fi

  # 4. The PDF handler — reverted only while it still points at our entry.
  if command -v xdg-mime >/dev/null 2>&1; then
    local cur prev
    cur="$(xdg-mime query default "$PDF_MIME" 2>/dev/null || true)"
    if [[ $cur == "$PDF_ENTRY" ]]; then
      prev=""
      [[ -f $MIME_STATE ]] && prev="$(cat "$MIME_STATE")"
      if [[ -n $prev && $prev != "$PDF_ENTRY" ]]; then
        xdg-mime default "$prev" "$PDF_MIME" >/dev/null 2>&1 && echo "  Default PDF handler reverted to $prev."
      else
        echo "  WARNING: a PDF is still opened with $PDF_ENTRY; set another viewer with:"
        echo "    xdg-mime default <viewer>.desktop $PDF_MIME"
      fi
    fi
  fi

  # 6. The keybindings block, taken out by exact content — never `sed -i`, so the user's
  # config is only ever rewritten a few lines smaller and nothing in it is interpreted.
  # install.sh appends a blank line, the marker, then the three bind lines; the whole block
  # comes back out so a cycle does not stack another marker on the file.
  if [[ -f $BINDINGS ]] && grep -qF -e "$BIND_MARKER" "$BINDINGS"; then
    local kept; kept="$(mktemp)"
    local lines=() out=() line b drop
    mapfile -t lines < "$BINDINGS"
    for line in "${lines[@]}"; do
      if [[ $line == "$BIND_MARKER" ]]; then
        # Drop the blank line install wrote just before the marker, if it is still there.
        if (( ${#out[@]} )) && [[ -z ${out[-1]} ]]; then unset 'out[-1]'; fi
        continue
      fi
      drop=0
      for b in "${BIND_LINES[@]}"; do [[ $line == "$b" ]] && { drop=1; break; }; done
      (( drop )) && continue
      out+=("$line")
    done
    for line in ${out[@]+"${out[@]}"}; do printf '%s\n' "$line"; done > "$kept"
    mv "$kept" "$BINDINGS"
    echo "  Took the omarchy-pdf keybindings back out of $BINDINGS"
  fi

  # 5-state. The recorded previous handler.
  if [[ -d $STATE_DIR ]]; then
    rm -rf "$STATE_DIR"; echo "  Removed $STATE_DIR"
  fi

  echo ""
  echo "Done. Run 'hyprctl reload' to drop the keybindings."
}

if [[ ${1:-} == --uninstall ]]; then
  uninstall
  exit 0
fi

echo "omarchy-pdf: installing from $PLUGIN_DIR"

# ── 1. The viewer itself ───────────────────────────────────────────────────────
if command -v papers >/dev/null 2>&1; then
  echo "  Papers present."
else
  echo "  WARNING: Papers is not installed. Install it with:  omarchy pkg add papers"
fi

# ── 2. Install the helper binaries onto PATH ──────────────────────────────────
install_bin() { # source-name
  local name="$1" dest="$BIN_DIR/$1" src="$PLUGIN_DIR/bin/$1"
  cp "$src" "$dest"
  chmod 755 "$dest"
  echo "  Installed $dest"
}

for tool in omarchy-pdf omarchy-pdf-qtpdf-compat omarchy-toggle-pdf-night omarchy-webapp-qutebrowser omarchy-pdf-sign; do
  dest="$BIN_DIR/$tool"
  src="$PLUGIN_DIR/bin/$tool"
  if [[ -L $dest ]] && [[ "$(readlink -f "$dest")" == "$(readlink -f "$src")" ]]; then
    echo "  $tool already linked."
  elif (( EUID == 0 )); then
    install_bin "$tool"
  elif command -v sudo >/dev/null 2>&1; then
    sudo bash -c "cp '$src' '$dest' && chmod 755 '$dest'"
    echo "  Installed $dest"
  else
    pkexec bash -c "cp '$src' '$dest' && chmod 755 '$dest'"
    echo "  Installed $dest"
  fi
done

# `opf` is the short name: typing `omarchy-pdf` for every document is a tax on the
# reader who opens the most documents. A symlink, so there is one implementation.
link_opf() {
  local dest="$BIN_DIR/opf"
  if [[ -L $dest ]] && [[ "$(readlink -f "$dest")" == "$(readlink -f "$BIN_DIR/omarchy-pdf")" ]]; then
    echo "  opf already linked."
    return
  fi
  priv ln -sf "$BIN_DIR/omarchy-pdf" "$dest"
  echo "  Installed $dest"
}

link_opf

# ── 3. Desktop entries: QES signer + Chromium-free web-app fallback ───────────
mkdir -p "$APP_DIR"
cp "$PLUGIN_DIR/config/sign-me-qes.desktop" "$APP_DIR/sign-me-qes.desktop"
cp "$PLUGIN_DIR/config/chromium.desktop" "$APP_DIR/chromium.desktop"
cp "$PLUGIN_DIR/config/omarchy-pdf.desktop" "$APP_DIR/omarchy-pdf.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
echo "  Installed desktop entries into $APP_DIR"

# ── 3b. The viewer package, under a stable share path the launcher finds ──────
if (( EUID == 0 )); then
  rm -rf "$SHARE_DIR/pdf"; mkdir -p "$SHARE_DIR"; cp -r "$PLUGIN_DIR/pdf" "$SHARE_DIR/pdf"
  echo "  Installed the pdf package to $SHARE_DIR"
elif command -v sudo >/dev/null 2>&1; then
  sudo bash -c "rm -rf '$SHARE_DIR/pdf' && mkdir -p '$SHARE_DIR' && cp -r '$PLUGIN_DIR/pdf' '$SHARE_DIR/pdf'"
  echo "  Installed the pdf package to $SHARE_DIR"
fi

# ── 3c. QtPdf ABI compat shim ─────────────────────────────────────────────────
# PyQt6's QtPdf module is generated against the Qt it was BUILT against but links the
# libQt6Pdf present at runtime; where the system's QtPdf is older than that, the import
# fails on one undefined QPdfDocument::render overload and the viewer cannot render at
# all. The shim supplies exactly that symbol, and bin/omarchy-pdf-qtpdf-compat decides
# when to preload it, so it is inert on a coherent system. Needs a C++ compiler and the
# QtPdf headers of the installed Qt.
SHIM_DIR="$SHARE_DIR/qtpdf-compat"
shim_rc=0
build_out="$("$PLUGIN_DIR/tools/build-qtpdf-compat.sh" --out "$PLUGIN_DIR/shim/build" 2>&1)" || shim_rc=$?
if (( shim_rc == 0 )); then
  echo "  ${build_out#qtpdf-compat: }"
  SHIM_SO="$PLUGIN_DIR/shim/build/libqt6pdf-compat.so"
  if (( EUID == 0 )); then
    mkdir -p "$SHIM_DIR" && cp "$SHIM_SO" "$SHIM_DIR/"
    echo "  Installed the QtPdf compat shim to $SHIM_DIR"
  elif command -v sudo >/dev/null 2>&1; then
    sudo bash -c "mkdir -p '$SHIM_DIR' && cp '$SHIM_SO' '$SHIM_DIR/'"
    echo "  Installed the QtPdf compat shim to $SHIM_DIR"
  else
    echo "  WARNING: could not install the QtPdf compat shim to $SHIM_DIR (need root)."
  fi
elif (( shim_rc == 3 )); then
  echo "  WARNING: QtPdf compat shim not built (no C++ compiler or no QtPdf headers)."
  echo "           Only needed while python-pyqt6 is built against a newer Qt than libQt6Pdf."
else
  echo "  WARNING: QtPdf compat shim build failed:"
  echo "           $build_out"
fi

# ── 4. Default PDF handler ────────────────────────────────────────────────────
# The handler that was in place is recorded first, so --uninstall can put it back
# instead of leaving the user with no PDF handler at all. Recorded once: a re-install
# must not overwrite the original with our own entry.
if command -v xdg-mime >/dev/null 2>&1; then
  mkdir -p "$STATE_DIR"
  [[ -f $MIME_STATE ]] || xdg-mime query default "$PDF_MIME" > "$MIME_STATE" 2>/dev/null || : > "$MIME_STATE"
  xdg-mime default omarchy-pdf.desktop "$PDF_MIME" >/dev/null 2>&1 || true
  echo "  Default PDF handler -> omarchy-pdf."
fi

# ── 5. Night mode on by default (dark rendering) ──────────────────────────────
if command -v gsettings >/dev/null 2>&1; then
  if gsettings set org.gnome.Papers night-mode true 2>/dev/null; then
    echo "  Papers night mode enabled by default."
  else
    echo "  WARNING: could not set Papers night mode (gsettings write failed) — set it in Papers manually."
  fi
fi

# ── 6. Register keybindings in ~/.config/hypr/bindings.lua ────────────────────
if [[ -f $BINDINGS ]] && ! grep -q 'omarchy-toggle-pdf-night' "$BINDINGS"; then
  cat >> "$BINDINGS" << 'LUA'

-- omarchy-pdf plugin
o.bind("SUPER + D",         "Documents (omarchy-pdf)",   "/usr/local/bin/omarchy-pdf")
o.bind("SUPER + CTRL + N",  "PDF dark/light toggle",    "/usr/local/bin/omarchy-toggle-pdf-night")
o.bind("SUPER + SHIFT + Q", "sign-me (QES signieren)",  { launch = "qutebrowser --target window https://www.sign-me.de/" })
LUA
  echo "  Added keybindings to $BINDINGS"
elif grep -q 'omarchy-toggle-pdf-night' "${BINDINGS:-/dev/null}" 2>/dev/null; then
  echo "  Keybindings already present."
else
  echo "  No bindings.lua found — add the omarchy-pdf bindings manually."
fi

# ── 7. Reload Hyprland ────────────────────────────────────────────────────────
if command -v hyprctl >/dev/null 2>&1 && [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
  hyprctl reload >/dev/null 2>&1 && echo "  Hyprland reloaded." || echo "  Hyprland reload failed — reload manually."
else
  echo "  Run 'hyprctl reload' to activate."
fi

echo ""
echo "Done!"
echo ""
echo "Keybindings:"
echo "  Super + D          — open a document in omarchy-pdf"
echo "  Super + Ctrl + N   — toggle PDF dark/light rendering"
echo "  Super + Shift + Q  — open the sign-me portal (QES)"
echo ""
echo "QES note: register once at sign-me and identify with the Online-Ausweis;"
echo "the qualified certificate lives at the provider, so signing happens there."
