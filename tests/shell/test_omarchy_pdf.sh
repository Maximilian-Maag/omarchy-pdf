#!/bin/bash
# Shell tests: the bin/omarchy-pdf launcher picks an interpreter and execs the app.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  PASS: $1"; }
no() { fail=$((fail + 1)); echo "  FAIL: $1"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# A stub "python3" that answers the capability probe (-c) and, for a real launch,
# prints the argv it was exec'd with — so the launcher's exec line is observable.
cat > "$tmp/python3" <<'PY'
#!/bin/bash
if [[ ${1:-} == -c ]]; then
  exit "${STUB_IMPORT_RC:-0}"
fi
printf 'EXEC %s\n' "$*"
printf 'PYTHONPATH=%s\n' "${PYTHONPATH:-}"
PY
chmod +x "$tmp/python3"

out="$(OMARCHY_PDF_PYTHON="$tmp/python3" OMARCHY_PDF_DIR="$REPO" bash "$REPO/bin/omarchy-pdf" doc.pdf 2>&1)"
if [[ $out == *"EXEC -m pdf.app doc.pdf"* ]]; then
  ok "launcher execs the app with the document"
else
  no "launcher exec line: $out"
fi
if [[ $out == *"PYTHONPATH=$REPO"* ]]; then
  ok "launcher puts the package on PYTHONPATH"
else
  no "PYTHONPATH not set to the package dir: $out"
fi

out2="$(OMARCHY_PDF_PYTHON="$tmp/python3" OMARCHY_PDF_DIR="$REPO" \
        bash "$REPO/bin/omarchy-pdf" --command "goto 2" --exit 2>&1)"
if [[ $out2 == *"-m pdf.app --command goto 2 --exit"* ]]; then
  ok "launcher passes options through"
else
  no "options not forwarded: $out2"
fi

echo "shell: $pass passed, $fail failed"
(( fail == 0 ))
