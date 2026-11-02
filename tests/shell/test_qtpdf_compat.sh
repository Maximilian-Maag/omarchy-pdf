#!/bin/bash
# Shell tests: the QtPdf compat helper decides when the shim is needed, and the shim
# it points at really exports the symbol the bindings ask for.
#
# The decision is driven with stub interpreters (as the launcher test does); the shim
# itself is built for real, because "does it export this exact symbol, with that
# version tag" is the whole point of the artifact and a stub cannot answer it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPAT="$REPO/bin/omarchy-pdf-qtpdf-compat"
MISSING="_ZN12QPdfDocument6renderEi5QSize25QPdfDocumentRenderOptionsN6QImage6FormatE6QColor"
pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  PASS: $1"; }
no() { fail=$((fail + 1)); echo "  FAIL: $1"; }

# tools/run_tests.sh preloads the real shim for the Qt suite it runs earlier in the same
# process; the decision here is about what this script does on its own, so start clean.
unset LD_PRELOAD

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export STUB_ABI_LIB="$tmp/libqt6pdf-compat.so"

# ── stub interpreters ────────────────────────────────────────────────────────────
# A coherent system: the import just works.
cat > "$tmp/py-ok" <<'PY'
#!/bin/bash
exit 0
PY

# The ABI gap: the import fails with the exact undefined symbol, and succeeds only
# once THIS library is preloaded (not any library the environment happened to carry).
cat > "$tmp/py-abi" <<'PY'
#!/bin/bash
if [[ -n ${STUB_ABI_LIB:-} ]] && [[ ${LD_PRELOAD:-} == "$STUB_ABI_LIB" ]]; then
  exit 0
fi
echo "ImportError: PyQt6/QtPdf.abi3.so: undefined symbol: _ZN12QPdfDocument6renderEi5QSize25QPdfDocumentRenderOptionsN6QImage6FormatE6QColor, version Qt_6" >&2
exit 1
PY

# Unrelated breakage: no PyQt6 at all. Preloading a shim cannot fix that.
cat > "$tmp/py-other" <<'PY'
#!/bin/bash
echo "ModuleNotFoundError: No module named 'PyQt6'" >&2
exit 1
PY

# A gap the shim does NOT close: still failing after the preload. The helper must then
# claim nothing rather than hand the launcher a library that does not help.
cat > "$tmp/py-stubborn" <<'PY'
#!/bin/bash
echo "undefined symbol: _ZN12QPdfDocument6renderEi5QSize25QPdfDocumentRenderOptionsN6QImage6FormatE6QColor, version Qt_6" >&2
exit 1
PY

chmod +x "$tmp"/py-*
: > "$tmp/libqt6pdf-compat.so"    # the helper locates and preloads a file; content is the build's business

decide() { # <lib|omit> <interpreter>
  if [[ $1 == "omit" ]]; then
    OMARCHY_PDF_QTDPDF_COMPAT="$tmp/absent.so" "$COMPAT" preload "$2"
  else
    OMARCHY_PDF_QTDPDF_COMPAT="$tmp/$1" "$COMPAT" preload "$2"
  fi
}

out="$(decide libqt6pdf-compat.so "$tmp/py-ok")"
if [[ -z $out ]]; then
  ok "a coherent interpreter needs no preload"
else
  no "preload offered for a working interpreter: $out"
fi

out="$(decide libqt6pdf-compat.so "$tmp/py-abi")"
if [[ $out == "$tmp/libqt6pdf-compat.so" ]]; then
  ok "the QtPdf ABI gap is answered with the compat library"
else
  no "expected the compat library for the ABI gap, got: $out"
fi

out="$(decide libqt6pdf-compat.so "$tmp/py-other")"
if [[ -z $out ]]; then
  ok "no preload for a missing PyQt6 (preloading cannot fix that)"
else
  no "preload for an unrelated import failure: $out"
fi

out="$(decide libqt6pdf-compat.so "$tmp/py-stubborn")"
if [[ -z $out ]]; then
  ok "nothing claimed when the shim does not actually fix the import"
else
  no "unproven preload offered: $out"
fi

out="$(decide omit "$tmp/py-abi")"
if [[ -z $out ]]; then
  ok "no shim built: no preload claimed"
else
  no "preload claimed without a library: $out"
fi

# ── dispatch ─────────────────────────────────────────────────────────────────────
err="$("$COMPAT" 2>&1 >/dev/null)"; rc=$?
if (( rc == 2 )) && [[ $err == *"usage:"* ]]; then
  ok "a missing subcommand is a usage error"
else
  no "missing subcommand: rc=$rc out=$err"
fi

err="$("$COMPAT" bogus x 2>&1 >/dev/null)"; rc=$?
if (( rc == 2 )) && [[ $err == *"usage:"* ]]; then
  ok "an unknown subcommand is a usage error"
else
  no "unknown subcommand: rc=$rc out=$err"
fi

err="$("$COMPAT" preload 2>&1 >/dev/null)"; rc=$?
if (( rc == 2 )) && [[ $err == *"usage:"* ]]; then
  ok "preload without an interpreter is a usage error"
else
  no "preload without an interpreter: rc=$rc out=$err"
fi

# ── the artifact itself ──────────────────────────────────────────────────────────
if [[ -x "$REPO/tools/build-qtpdf-compat.sh" ]]; then
  build_out="$("$REPO/tools/build-qtpdf-compat.sh" --out "$tmp/build" 2>&1)"; build_rc=$?
  if (( build_rc == 3 )); then
    echo "  SKIP: no C++ compiler / Qt6 QtPdf headers here — shim build not exercised"
  elif (( build_rc != 0 )); then
    no "shim build failed: $build_out"
  elif ! command -v nm >/dev/null 2>&1; then
    no "nm is unavailable, cannot inspect the built shim"
  elif nm -D --defined-only "$tmp/build/libqt6pdf-compat.so" | grep -q "$MISSING@@Qt_6"; then
    ok "the built shim exports the missing overload under the Qt_6 version tag"
  else
    no "the built shim does not export $MISSING@@Qt_6"
  fi
else
  no "tools/build-qtpdf-compat.sh is missing"
fi

echo "shell: $pass passed, $fail failed"
(( fail == 0 ))
