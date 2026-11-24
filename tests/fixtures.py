"""Hand-built PDF fixtures — a text/link/outline document and an AcroForm form.

Written as explicit objects so the tests do not depend on any external tool to
*create* input; qpdf is used only where a test opts into the authoring path.
"""
from __future__ import annotations

import pathlib


def build(objects: dict[int, bytes], root: int = 1) -> bytes:
    """Assemble a classic-xref PDF from {object number: body}."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    xref_at = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n" % size
    out += b"0000000000 65535 f \n"
    for number in range(1, size):
        if number in offsets:
            out += b"%010d 00000 n \n" % offsets[number]
        else:
            out += b"0000000000 65535 f \n"
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (size, root, xref_at))
    return bytes(out)


def _page(parent: int, contents: int, extra: bytes = b"") -> bytes:
    return (b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 9 0 R >> >> /Contents %d 0 R%s >>"
            % (parent, contents, extra))


def _stream(text: bytes) -> bytes:
    body = b"BT /F1 24 Tf 72 700 Td (" + text + b") Tj ET"
    return b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"


def text_pdf() -> bytes:
    """Three pages, an external link on page 1, one outline entry to page 2."""
    return build({
        1: b"<< /Type /Catalog /Pages 2 0 R /Outlines 10 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>",
        3: _page(2, 4, b" /Annots [11 0 R]"),
        4: _stream(b"Hello page one"),
        5: _page(2, 6),
        6: _stream(b"Page two"),
        7: _page(2, 8),
        8: _stream(b"Page three"),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        10: b"<< /Type /Outlines /First 12 0 R /Last 12 0 R /Count 1 >>",
        11: (b"<< /Type /Annot /Subtype /Link /Rect [72 690 300 730] "
             b"/Border [0 0 1] /A << /S /URI /URI (https://omarchy.org/) >> >>"),
        12: b"<< /Title (Second page) /Parent 10 0 R /Dest [5 0 R /Fit] >>",
    })


def mixed_links_pdf() -> bytes:
    """Two pages; page 1 carries one external URI and one internal destination.

    `f` has to offer both — the internal one jumps within the document — while `F`
    ("open in the browser") has nothing to offer on the internal one. Without that
    split the two keys do exactly the same thing.
    """
    return build({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
        3: _page(2, 4, b" /Annots [11 0 R 12 0 R]"),
        4: _stream(b"Page one"),
        5: _page(2, 6),
        6: _stream(b"Page two"),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        11: (b"<< /Type /Annot /Subtype /Link /Rect [72 690 300 730] "
             b"/Border [0 0 1] /A << /S /URI /URI (https://omarchy.org/) >> >>"),
        12: (b"<< /Type /Annot /Subtype /Link /Rect [72 600 300 640] "
             b"/Border [0 0 1] /A << /S /GoTo /D [5 0 R /Fit] >> >>"),
    })


def form_pdf() -> bytes:
    """One page with a text field and a checkbox."""
    return build({
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [11 0 R 12 0 R] >> >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: _page(2, 4, b" /Annots [11 0 R 12 0 R]"),
        4: _stream(b"Form page"),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        11: (b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (full name) /V () "
             b"/DA (/Helv 0 Tf 0 g) /Rect [72 700 300 720] /P 3 0 R >>"),
        12: (b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (agree) /V /Off "
             b"/AS /Off /Rect [72 660 90 678] /P 3 0 R >>"),
    })


def non_a4_pdf() -> bytes:
    """One page whose MediaBox is 300 x 200 (NOT A4) — for redaction geometry."""
    return build({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Resources << /Font << /F1 9 0 R >> >> /Contents 4 0 R >>"),
        4: _stream(b"Small page"),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    })


def two_page_kids_reordered_pdf() -> bytes:
    """Two pages whose /Kids order is the REVERSE of their object numbering.

    Page 1 is object 5 and page 2 is object 3, so anything that resolves page
    order by object number annotates page 2 when asked for page 1.
    """
    return build({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [5 0 R 3 0 R] /Count 2 >>",
        3: _page(2, 4),          # object 3 = SECOND page
        4: _stream(b"Second page body"),
        5: _page(2, 6),          # object 5 = FIRST page
        6: _stream(b"First page body"),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    })


def layer_pdf() -> bytes:
    """One page plus one optional-content group (a layer named 'Watermark')."""
    return build({
        1: (b"<< /Type /Catalog /Pages 2 0 R "
            b"/OCProperties << /OCGs [6 0 R] /D << /ON [6 0 R] >> >> >>"),
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: _page(2, 4),
        4: _stream(b"Layer page"),
        6: b"<< /Type /OCG /Name (Watermark) >>",
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    })


def write(path: str | pathlib.Path, data: bytes) -> str:
    pathlib.Path(path).write_bytes(data)
    return str(path)
