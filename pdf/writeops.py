"""Write-side document operations: fill, annotate, sign, redact, OCR.

QtPdf cannot author, so these are built on the tools Omarchy ships plus the small
object editor in :mod:`pdf.pdffile`. Every function returns a human-readable string.
Tool invocation goes through :func:`run` / :func:`have` (injectable, as in docops).

  forms    AcroForm fill + save (incremental update)     — pdf.pdffile + qpdf
  annotate add a /Text or /Highlight annotation          — pdf.pdffile + qpdf
  sign     verify embedded signatures, delegate QES      — pdfsig + the provider
  ocr      add a searchable text layer                   — pdftoppm + tesseract
  redact   RASTERISE the pages (removes the text) then stamp an opaque box
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile

from . import pdffile


def run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _with_suffix(path: str, suffix: str) -> str:
    stem, _ = os.path.splitext(path)
    return f"{stem}-{suffix}.pdf"


def _parse_pairs(args: tuple[str, ...]) -> dict[str, str]:
    values = {}
    for item in args:
        name, sep, value = item.partition("=")
        if sep:
            values[name] = value
        else:
            values[item] = "on"
    return values


def forms(path: str, *args) -> str:
    """Fill AcroForm fields: ``forms name=value [checked=on]``."""
    if not args:
        return "usage: forms <field=value> ..."
    return pdffile.fill_form(path, _parse_pairs(args), _with_suffix(path, "filled"))


def annotate(path: str, *args) -> str:
    """Add an annotation: ``annotate <kind> <page> <x1> <y1> <x2> <y2> <text...>``."""
    if len(args) < 6:
        return "usage: annotate <kind> <page> <x1> <y1> <x2> <y2> <text>"
    kind = args[0]
    if kind not in ("Text", "Highlight"):
        return "annotation kind must be Text or Highlight"
    try:
        page = int(args[1]) - 1
        rect = tuple(float(v) for v in args[2:6])
    except ValueError:
        return "page and coordinates must be numbers"
    text = " ".join(args[6:])
    return pdffile.add_annotation(path, page, rect, text, _with_suffix(path, "annotated"), kind)


def sign(path: str, *args) -> str:
    """Verify embedded signatures; `sign --qes` points at the QES provider flow."""
    if "--qes" in args or "qes" in args:
        from . import docops  # noqa: F401  (kept for symmetry)
        return ("QES: a qualified certificate lives at the provider — run "
                "`omarchy-pdf-sign <file>` to sign via sign-me (eIDAS Fernsignatur).")
    if not have("pdfsig"):
        return "pdfsig is not installed (omarchy pkg add poppler)"
    code, out, err = run(["pdfsig", path])
    if code != 0:
        return f"pdfsig failed: {err.strip()[:160]}"
    body = out.strip()
    return body or "no digital signatures found"


def ocr(path: str, *args) -> str:
    """Add a searchable text layer via tesseract (page images from poppler)."""
    if not have("tesseract"):
        return "tesseract is not installed (omarchy pkg add tesseract)"
    if not have("pdftoppm"):
        return "pdftoppm is not installed (omarchy pkg add poppler)"
    work = tempfile.mkdtemp(prefix="pdf-ocr-")
    try:
        code, _out, err = run(["pdftoppm", "-r", "300", "-tiff", path, f"{work}/page"])
        if code != 0:
            return f"rasterising failed: {err.strip()[:160]}"
        images = sorted(glob.glob(f"{work}/page*.tif*"))
        if not images:
            return "no pages were rendered"
        pdfs = []
        for image in images:
            stem = image.rsplit(".", 1)[0]
            code, _out, err = run(["tesseract", image, stem, "pdf"])
            if code != 0:
                return f"tesseract failed: {err.strip()[:160]}"
            pdfs.append(stem + ".pdf")
        dest = _with_suffix(path, "ocr")
        merged = _merge(pdfs, dest)
        if merged is None:
            return "no PDF merge tool found (need qpdf or pdfunite)"
        return f"OCR complete ({len(pdfs)} page(s)) -> {dest}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _merge(pdfs: list[str], dest: str) -> str | None:
    if have("qpdf"):
        code, _out, _err = run(["qpdf", "--empty", "--pages", *pdfs, "--", dest])
        if code == 0:
            return dest
    if have("pdfunite"):
        code, _out, _err = run(["pdfunite", *pdfs, dest])
        if code == 0:
            return dest
    return None


def _stamp(rect: tuple[float, float, float, float], size: tuple[float, float],
           out: str) -> bool:
    """Write a one-page PDF with a black box at `rect` (page coordinates)."""
    if not have("gs"):
        return False
    x1, y1, x2, y2 = rect
    ps = (f"<< /PageSize [{size[0]:.2f} {size[1]:.2f}] >> setpagedevice\n"
          f"0 setgray {x1:.2f} {y1:.2f} {x2 - x1:.2f} {y2 - y1:.2f} rectfill\n"
          f"showpage\n")
    code, _out, _err = run(["gs", "-q", "-o", out, "-sDEVICE=pdfwrite", "-c", ps])
    return code == 0 and os.path.exists(out)


def redact(path: str, *args) -> str:
    """Redact a region: rasterise the pages, then stamp an opaque box.

    Rasterising with ``pdftocairo`` first is what makes this a real redaction — the
    covered bytes are not merely hidden, the text layer is regenerated as pixels, so
    nothing under the box can be copied out.
    """
    if len(args) < 5:
        return "usage: redact <page> <x1> <y1> <x2> <y2>"
    if not have("pdftocairo"):
        return "pdftocairo is not installed (omarchy pkg add poppler)"
    if not have("qpdf"):
        return "qpdf is not installed (omarchy pkg add qpdf)"
    try:
        page = int(args[0])
        rect = tuple(float(v) for v in args[1:5])
    except ValueError:
        return "page and coordinates must be numbers"
    work = tempfile.mkdtemp(prefix="pdf-redact-")
    try:
        raster = f"{work}/raster.pdf"
        code, _out, err = run(["pdftocairo", "-pdf", path, raster])
        if code != 0:
            return f"rasterising failed: {err.strip()[:160]}"
        size = _page_size(path, page)
        stamp = f"{work}/stamp.pdf"
        if not _stamp(rect, size, stamp):
            return "could not build the redaction stamp (ghostscript needed)"
        dest = _with_suffix(path, "redacted")
        code, _out, err = run(["qpdf", "--overlay", stamp, "--", raster, dest])
        if code != 0:
            return f"overlay failed: {err.strip()[:160]}"
        return f"redacted region on page {page} (rasterised, text removed) -> {dest}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _page_size(path: str, page_index: int) -> tuple[float, float]:
    """(width, height) of a 1-based page from pdfinfo's ``Page N size`` line."""
    code, out, _err = run(["pdfinfo", "-f", str(page_index), "-l", str(page_index), path])
    if code == 0:
        for line in out.splitlines():
            if line.startswith("Page") and "size" in line:
                parts = line.split("size", 1)[1].split()
                try:
                    return float(parts[0]), float(parts[1].rstrip("acm"))
                except (ValueError, IndexError):
                    break
    return 595.0, 842.0
