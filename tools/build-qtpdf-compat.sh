#!/bin/bash
# Build the QtPdf ABI compatibility shim (shim/qtpdf-compat.cpp).
#
# The shim is only useful where the installed libQt6Pdf is older than the Qt the
# PyQt6 QtPdf bindings were generated against; on a coherent system it is simply never
# loaded (see bin/omarchy-pdf-qtpdf-compat). Building it therefore needs the QtPdf
# *headers* of the installed Qt — nothing else, and no source download.
#
# Usage: tools/build-qtpdf-compat.sh [--out DIR]
# Exit:  0 built   1 build failed   3 nothing to build (no compiler / no QtPdf headers)

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO/shim/build"
LIB_NAME="libqt6pdf-compat.so"

while (( $# > 0 )); do
  case "$1" in
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    *) echo "usage: build-qtpdf-compat.sh [--out DIR]" >&2; exit 2 ;;
  esac
done

CXX="${CXX:-}"
if [[ -z $CXX ]]; then
  for candidate in g++ c++; do
    if command -v "$candidate" >/dev/null 2>&1; then CXX="$candidate"; break; fi
  done
fi
if [[ -z $CXX ]]; then
  echo "qtpdf-compat: no C++ compiler (g++/c++) — the shim is not built." >&2
  exit 3
fi

CFLAGS=""
LIBS=""
if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists Qt6Pdf Qt6Gui Qt6Core; then
  CFLAGS="$(pkg-config --cflags Qt6Pdf Qt6Gui Qt6Core)"
  LIBS="$(pkg-config --libs Qt6Pdf Qt6Gui Qt6Core)"
elif [[ -f /usr/include/qt6/QtPdf/qpdfdocument.h ]]; then
  CFLAGS="-I/usr/include/qt6 -I/usr/include/qt6/QtPdf -I/usr/include/qt6/QtGui -I/usr/include/qt6/QtCore"
  LIBS="-lQt6Pdf -lQt6Gui -lQt6Core"
else
  echo "qtpdf-compat: Qt6 QtPdf headers are not installed — the shim is not built." >&2
  exit 3
fi

mkdir -p "$OUT_DIR" || exit 1
# shellcheck disable=SC2086  # the flags are pkg-config's word-split output, by design
if ! "$CXX" -shared -fPIC -O2 -o "$OUT_DIR/$LIB_NAME" "$REPO/shim/qtpdf-compat.cpp" \
        $CFLAGS -Wl,--version-script="$REPO/shim/qtpdf-compat.map" $LIBS; then
  echo "qtpdf-compat: build failed." >&2
  exit 1
fi

echo "qtpdf-compat: built $OUT_DIR/$LIB_NAME"
