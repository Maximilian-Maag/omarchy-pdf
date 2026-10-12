"""Read-side document operations, over the CLI tools Omarchy ships.

Pure-stdlib, Qt-free. Every external command goes through :func:`run` (a thin
subprocess wrapper) and every tool presence check goes through :func:`have`, so a
test can inject a fake runner and assert the exact command line without touching a
real PDF. These functions return a human-readable string that the view emits.
"""
from __future__ import annotations

import json
import shutil
import subprocess


def run(cmd: list[str]) -> tuple[int, str, str]:
    """Run `cmd`; return (returncode, stdout, stderr). Swallows a missing binary."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


_INFO_FIELDS = ("Title", "Author", "Subject", "Keywords", "Creator", "Producer",
                "CreationDate", "ModDate", "Pages", "Encrypted", "Page size",
                "File size", "PDF version", "Tagged")


def info_text(path: str) -> str:
    """A short metadata summary from `pdfinfo`."""
    if not have("pdfinfo"):
        return "pdfinfo is not installed (omarchy pkg add poppler)"
    code, out, err = run(["pdfinfo", path])
    if code != 0:
        return f"pdfinfo failed: {err.strip()[:160]}"
    values = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = value.strip()
    lines = [f"{key}: {values[key]}" for key in _INFO_FIELDS if key in values]
    return "\n".join(lines) if lines else "no metadata"


def copy(path: str, dest: str) -> str:
    """Save a (linearised, decrypted) copy via qpdf, falling back to a plain copy."""
    if not dest:
        return "save-as needs a target path"
    if have("qpdf"):
        code, _out, err = run(["qpdf", "--linearize", "--decrypt", path, dest])
        if code == 0:
            return f"saved {dest}"
        return f"qpdf failed: {err.strip()[:160]}"
    try:
        shutil.copy2(path, dest)
    except OSError as exc:
        return f"copy failed: {exc}"
    return f"saved {dest}"


def print_document(path: str) -> str:
    """Send the document to the default CUPS printer."""
    if not have("lp"):
        return "no print system found (install cups)"
    code, out, err = run(["lp", path])
    if code != 0:
        return f"print failed: {err.strip()[:160]}"
    return out.strip() or "sent to printer"


def attachments(path: str) -> str:
    """List embedded files (pdfdetach, falling back to qpdf)."""
    if have("pdfdetach"):
        code, out, err = run(["pdfdetach", "-list", path])
        if code == 0:
            names = out.strip().splitlines()
            return "\n".join(names) if names else "no embedded files"
        return f"pdfdetach failed: {err.strip()[:160]}"
    if have("qpdf"):
        code, out, _err = run(["qpdf", "--list-attachments", path])
        if code == 0:
            return out.strip() or "no embedded files"
    return "no attachment tool found"


def _ocg_names(objects: dict) -> list[str]:
    names = []
    for value in objects.values():
        if not isinstance(value, dict):
            continue
        if value.get("/Type") == "/OCG":
            names.append(str(value.get("/Name", "(unnamed)")))
    return names


def layers(path: str) -> str:
    """List optional-content groups (layers) via qpdf's JSON view."""
    if not have("qpdf"):
        return "qpdf is not installed (omarchy pkg add qpdf)"
    code, out, err = run(["qpdf", "--json", path])
    if code != 0:
        return f"qpdf failed: {err.strip()[:160]}"
    try:
        data = json.loads(out)
    except ValueError:
        return "could not read the document structure"
    objects = {}
    for section in data.get("qpdf", []):
        if isinstance(section, dict) and "objects" in section:
            objects.update(section["objects"])
    names = _ocg_names(objects)
    return "\n".join(names) if names else "no optional-content layers"
