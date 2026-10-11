#!/bin/bash
# omarchy-pdf install script
# Wires the plugin into the live Omarchy/Hyprland config.
# Safe to re-run — all steps are idempotent.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
HYPR_CONFIG_DIR="$CONFIG_HOME/hypr"
BINDINGS="$HYPR_CONFIG_DIR/bindings.lua"
BIN_DIR="/usr/local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

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

for tool in omarchy-toggle-pdf-night omarchy-webapp-qutebrowser omarchy-pdf-sign; do
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

# ── 3. Desktop entries: QES signer + Chromium-free web-app fallback ───────────
mkdir -p "$APP_DIR"
cp "$PLUGIN_DIR/config/sign-me-qes.desktop" "$APP_DIR/sign-me-qes.desktop"
cp "$PLUGIN_DIR/config/chromium.desktop" "$APP_DIR/chromium.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
echo "  Installed desktop entries into $APP_DIR"

# ── 4. Papers as the default PDF handler ──────────────────────────────────────
if command -v xdg-mime >/dev/null 2>&1 && command -v papers >/dev/null 2>&1; then
  xdg-mime default org.gnome.Papers.desktop application/pdf >/dev/null 2>&1 || true
  echo "  Default PDF handler -> Papers."
fi

# ── 5. Night mode on by default (dark rendering) ──────────────────────────────
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.Papers night-mode true 2>/dev/null || true
  echo "  Papers night mode enabled by default."
fi

# ── 6. Register keybindings in ~/.config/hypr/bindings.lua ────────────────────
if [[ -f $BINDINGS ]] && ! grep -q 'omarchy-toggle-pdf-night' "$BINDINGS"; then
  cat >> "$BINDINGS" << 'LUA'

-- omarchy-pdf plugin
o.bind("SUPER + D",         "Documents (Papers)",       "papers")
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
echo "  Super + D          — open a document in Papers"
echo "  Super + Ctrl + N   — toggle PDF dark/light rendering"
echo "  Super + Shift + Q  — open the sign-me portal (QES)"
echo ""
echo "QES note: register once at sign-me and identify with the Online-Ausweis;"
echo "the qualified certificate lives at the provider, so signing happens there."
