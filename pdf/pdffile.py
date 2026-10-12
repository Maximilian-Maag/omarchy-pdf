"""A small PDF object editor for authoring: fill AcroForms, add annotations.

QtPdf (PDFium) is a *viewer* engine with no authoring API, so writing lives here.
The approach is deliberately simple and robust:

  1. normalise the document with ``qpdf --qdf --object-streams=disable`` — that
     yields plain objects and a classic xref table, easy to parse and rebuild;
  2. parse the objects into ``{number: body bytes}``;
  3. mutate the objects we care about (set ``/V`` on a field, append an ``/Annots``
     entry to a page);
  4. write an **incremental update** — the changed objects, a new xref whose trailer
     points at the previous one via ``/Prev`` — so nothing else is disturbed.

The pure functions operate on bytes and are unit-tested against a real fixture; the
tool invocation is thin and injectable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

_OBJ = re.compile(rb"(?s)(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj")
_STARTXREF = re.compile(rb"startxref\s+(\d+)")
_TRAILER = re.compile(rb"trailer\s*<<(.*?)>>\s*startxref", re.S)


def run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


# ── parsing ──────────────────────────────────────────────────────────────

def parse_objects(data: bytes) -> dict[int, bytes]:
    """{object number: body bytes} for every ``N G obj … endobj`` in `data`."""
    return {int(m.group(1)): m.group(3) for m in _OBJ.finditer(data)}


def trailer_dict(data: bytes) -> dict[str, str]:
    """Extract simple ``/Key value`` pairs from the last trailer."""
    match = _TRAILER.search(data)
    if not match:
        return {}
    body = match.group(1)
    out = {}
    for key, value in re.findall(rb"/(\w+)\s+(\d+\s+\d+\s+R|/[\w.]+|\d+|<[^>]*>|\[[^\]]*\])", body):
        out[key.decode()] = value.decode("latin-1")
    return out


def previous_xref(data: bytes) -> int:
    matches = _STARTXREF.findall(data)
    return int(matches[-1]) if matches else 0


# ── field discovery / mutation ───────────────────────────────────────────

def field_names(objects: dict[int, bytes]) -> list[str]:
    """The /T (partial) names of every AcroForm field object."""
    names = []
    for body in objects.values():
        if b"/FT" not in body:
            continue
        match = re.search(rb"/T\s*\(([^)]*)\)", body)
        if match:
            names.append(match.group(1).decode("latin-1"))
    return names


def _decode_pdf_string(raw: bytes) -> str:
    """Decode a PDF string literal or hex string to text (delimiters optional)."""
    if raw.startswith(b"(") and raw.endswith(b")"):
        raw = raw[1:-1]
        raw = raw.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    elif raw.startswith(b"<") and raw.endswith(b">"):
        raw = raw[1:-1]
        try:
            raw = bytes.fromhex(raw.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return raw.decode("latin-1", "replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    return raw.decode("latin-1", "replace")


def _encode_pdf_string(value: str) -> bytes:
    if all(ord(c) < 128 for c in value):
        escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        return b"(" + escaped.encode("latin-1") + b")"
    return b"<feff" + value.encode("utf-16-be").hex().encode("ascii") + b">"


def _set_key(body: bytes, key: bytes, value: bytes) -> bytes:
    """Set ``/key value`` in a dict body, replacing an existing entry or inserting."""
    pattern = re.compile(rb"/" + key + rb"\s*(?:\([^)]*\)|<[^>]*>|/[\w.]+|\[[^\]]*\]|\S+)")
    if pattern.search(body):
        return pattern.sub(b"/" + key + b" " + value, body, count=1)
    close = body.rfind(b">>")
    if close == -1:
        return body + b" /" + key + b" " + value + b" >>"
    return body[:close] + b"/" + key + b" " + value + b" " + body[close:]


def _values_for(objects: dict[int, bytes], name: str,
                value: str) -> tuple[int, bytes] | None:
    """(object number, new body) for the named field, or None.

    The field's /FT decides how the value is interpreted: a /Btn (checkbox/radio)
    gets /V and /AS set to /Yes or /Off; anything else gets a text /V.
    """
    for number, body in objects.items():
        if b"/FT" not in body:
            continue
        match = re.search(rb"/T\s*\(([^)]*)\)", body)
        if not match or _decode_pdf_string(match.group(1)) != name:
            continue
        field_type = re.search(rb"/FT\s*/(\w+)", body)
        if field_type and field_type.group(1) == b"Btn":
            on = b"/Yes" if value.lower() in ("on", "yes", "true", "1", "x") else b"/Off"
            body = _set_key(body, b"V", on)
            body = _set_key(body, b"AS", on)
        else:
            body = _set_key(body, b"V", _encode_pdf_string(value))
        return number, body
    return None


# ── serialisation ────────────────────────────────────────────────────────

def incremental_update(base: bytes, changes: dict[int, bytes], extra=None) -> bytes:
    """Append `changes` as an incremental update to `base` (a normalised PDF)."""
    out = bytearray(base)
    if not out.endswith(b"\n"):
        out += b"\n"
    offsets: dict[int, int] = {}
    for number in sorted(changes):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + changes[number] + b"\nendobj\n"
    extra = extra or {}
    new_objects = {**changes}
    for number, body in extra.items():
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
        new_objects[number] = body
    xref_at = len(out)
    out += b"xref\n"
    for number in sorted(offsets):
        out += b"%d 1\n%010d 00000 n \n" % (number, offsets[number])
    trail = trailer_dict(base)
    size = max(int(trail.get("Size", "0") or 0), max(new_objects) + 1)
    root = trail.get("Root", "1 0 R")
    ident = trail.get("ID")
    id_part = b" /ID %s" % ident.encode("latin-1") if ident else b""
    out += (b"trailer\n<< /Size %d /Root %s%s /Prev %d >>\nstartxref\n%d\n%%%%EOF\n"
            % (size, root.encode("latin-1"), id_part, previous_xref(base), xref_at))
    return bytes(out)


# ── high-level operations (tool-invoking) ────────────────────────────────

def _normalise(path: str) -> tuple[bytes | None, str]:
    if not have("qpdf"):
        return None, "qpdf is not installed (omarchy pkg add qpdf)"
    fd, tmp = tempfile.mkstemp(suffix=".qdf")
    os.close(fd)
    try:
        code, _out, err = run(["qpdf", "--qdf", "--object-streams=disable",
                               "--stream-data=uncompress", path, tmp])
        if code != 0:
            return None, f"qpdf could not normalise the document: {err.strip()[:160]}"
        with open(tmp, "rb") as handle:
            return handle.read(), ""
    finally:
        os.unlink(tmp)


def fill_form(path: str, values: dict[str, str], dest: str) -> str:
    """Fill AcroForm fields and write `dest` as an incremental update."""
    base, error = _normalise(path)
    if base is None:
        return error
    objects = parse_objects(base)
    changes: dict[int, bytes] = {}
    applied, missing = [], []
    for name, value in values.items():
        found = _values_for(objects, name, value)
        if found is None:
            missing.append(name)
        else:
            changes[found[0]] = found[1]
            applied.append(name)
    if not changes:
        return "no matching fields" + (f": {', '.join(missing)}" if missing else "")
    payload = incremental_update(base, changes)
    with open(dest, "wb") as handle:
        handle.write(payload)
    note = f"filled {len(applied)} field(s) -> {dest}"
    if missing:
        note += f" (missing: {', '.join(missing)})"
    return note


def _page_object(objects: dict[int, bytes], page_index: int) -> int | None:
    """Object number of the Nth page (``/Type /Page`` but not ``/Pages``)."""
    pages = [n for n, b in objects.items()
             if re.search(rb"/Type\s*/Page(?![s\w])", b)]
    pages.sort()
    if 0 <= page_index < len(pages):
        return pages[page_index]
    return None


def add_annotation(path: str, page_index: int, rect: tuple[float, float, float, float],
                   text: str, dest: str, kind: str = "Text") -> str:
    """Add a /Text (sticky-note) or /Highlight annotation to a page."""
    base, error = _normalise(path)
    if base is None:
        return error
    objects = parse_objects(base)
    page_number = _page_object(objects, page_index)
    if page_number is None:
        return f"no page {page_index + 1}"
    next_number = max(objects) + 1
    annot = (b"<< /Type /Annot /Subtype /%s /Rect [%s] /Contents %s >>"
             % (kind.encode("ascii"),
                " ".join("%.2f" % v for v in rect).encode("ascii"),
                _encode_pdf_string(text)))
    page = _set_key(objects[page_number], b"Annots",
                    b"[%d 0 R]" % next_number)
    payload = incremental_update(base, {page_number: page}, extra={next_number: annot})
    with open(dest, "wb") as handle:
        handle.write(payload)
    return f"added a {kind} annotation to page {page_index + 1} -> {dest}"
