#!/bin/bash
# End-to-end: boot the REAL app through the REAL launcher, heads-down, and drive it.
#
# No display is needed (QT_QPA_PLATFORM=offscreen). This exercises the whole chain:
# launcher -> interpreter discovery -> pdf.app -> MainWindow -> PdfView -> PDFium
# render + a command run, then exit.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Pick an interpreter that actually has PyQt6.QtPdf (the system python may; a
# mise/pyenv python may not; CI installs the PyQt6 wheel). Where none exists the
# suite SKIPS rather than failing, matching the other environment-gated e2e.
PY="${OMARCHY_PDF_TEST_PYTHON:-}"
if [[ -z $PY ]]; then
  for candidate in /usr/bin/python3 python3; do
    if "$candidate" -c 'import PyQt6.QtPdf' >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [[ -z $PY ]]; then
  echo "  skip: no python3 with PyQt6.QtPdf (install PyQt6 / python-pyqt6)"
  exit 0
fi
export QT_QPA_PLATFORM=offscreen

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  PASS: $1"; }
no() { fail=$((fail + 1)); echo "  FAIL: $1"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

PDF="$tmp/doc.pdf"
if ! "$PY" - "$PDF" "$REPO" <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[2] + "/tests")
import fixtures
fixtures.write(sys.argv[1], fixtures.text_pdf())
PY
then
  echo "  FAIL: could not build the fixture"; exit 1
fi

# 1. A full run: load, jump, zoom, fit, exit cleanly.
out="$(OMARCHY_PDF_DIR="$REPO" OMARCHY_PDF_PYTHON="$PY" \
      bash "$REPO/bin/omarchy-pdf" "$PDF" \
      --command "goto 3; zoom-fit-width; info" --exit 2>&1)"
rc=$?
if (( rc == 0 )); then
  ok "app booted, rendered and exited cleanly (rc=0)"
else
  no "app exit code $rc: $out"
fi

# 2. It really rendered: the render path must not raise for each page.
out2="$(OMARCHY_PDF_DIR="$REPO" OMARCHY_PDF_PYTHON="$PY" \
       bash "$REPO/bin/omarchy-pdf" "$PDF" \
       --command "page-next; page-next; rotate-cw; zoom-in" --exit 2>&1)"
rc2=$?
if (( rc2 == 0 )) && [[ $out2 != *Traceback* ]]; then
  ok "navigation/render commands run without error"
else
  no "render commands error: $out2"
fi

# 3. A bad command is reported, not fatal.
out3="$(OMARCHY_PDF_DIR="$REPO" OMARCHY_PDF_PYTHON="$PY" \
       bash "$REPO/bin/omarchy-pdf" "$PDF" --command "frobnicate" --exit 2>&1)"
rc3=$?
if (( rc3 == 0 )) && [[ $out3 != *Traceback* ]]; then
  ok "an unknown command does not crash the app"
else
  no "unknown command was fatal: $out3"
fi

# 4. The engine really renders pixels (offscreen), through the real view.
render_out="$("$PY" - "$PDF" "$REPO" <<'PY' 2>&1
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[2]); sys.path.insert(0, sys.argv[2] + "/tests")
from PyQt6.QtWidgets import QApplication
from pdf import view as V, theme
app = QApplication(["e2e"])
w = V.PdfView(None, dict(theme.DEFAULT_PALETTE))
w.resize(900, 1200)
w.load(sys.argv[1])
app.processEvents()
w._render_visible()
rendered = [i for i in w._pages.values() if not i.pixmap().isNull()]
print("RENDERED", len(rendered))
PY
)"
if [[ $render_out == *"RENDERED"* ]]; then
  rendered_n="$(printf '%s\n' "$render_out" | sed -n 's/^RENDERED \([0-9][0-9]*\)$/\1/p' | tail -1)"
  if [[ -n $rendered_n ]] && (( rendered_n >= 1 )); then
    ok "PDFium rendered page pixels offscreen ($rendered_n page(s))"
  else
    no "render produced no pixmap: $render_out"
  fi
else
  no "render produced no pixmap: $render_out"
fi

echo "e2e: $pass passed, $fail failed"
(( fail == 0 ))
