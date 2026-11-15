"""Regression: pdf.writeops.redact must stamp the REQUESTED page.

Bug pinned: redact() built a one-page stamp and ran ``qpdf --overlay stamp --
raster dest`` with no page range, so qpdf imposed the stamp on the first page of
the destination no matter which page was asked for. A request to redact page 3
darkened page 1 and left the target page untouched — a redaction that silently
lands in the wrong place is worse than none at all.

The test renders the result with pdftoppm and measures the dark fraction per
page, so it observes the pixels the reader sees rather than the qpdf argv.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import fixtures  # noqa: E402
from pdf import writeops  # noqa: E402

NEEDED = ("pdftocairo", "qpdf", "gs", "pdftoppm", "pdfinfo")


def _render_gray(pdf: str, page: int, dpi: int, out_stem: str) -> str:
    """Render one page to a PGM and return its path."""
    subprocess.run(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(page),
                    "-l", str(page), pdf, out_stem], check=True,
                   capture_output=True)
    matches = sorted(pathlib.Path(out_stem).parent.glob(
        pathlib.Path(out_stem).name + "*.pgm"))
    return str(matches[0])


def _pgm_pixels(pgm_path: str):
    """(width, height, pixel bytes) for a binary PGM (P5)."""
    data = pathlib.Path(pgm_path).read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError("not a P5 PGM")
    idx = 2
    values = []

    def token() -> bytes:
        nonlocal idx
        # skip whitespace and '#' comments
        while idx < len(data):
            if data[idx:idx + 1].isspace():
                idx += 1
            elif data[idx:idx + 1] == b"#":
                while idx < len(data) and data[idx:idx + 1] not in (b"\n", b""):
                    idx += 1
            else:
                break
        start = idx
        while idx < len(data) and not data[idx:idx + 1].isspace():
            idx += 1
        return data[start:idx]

    width, height, _max = (int(token()) for _ in range(3))
    idx += 1  # the single whitespace byte after maxval
    return width, height, data[idx:idx + width * height]


def _dark_fraction(pgm_path: str) -> float:
    """Fraction of pixels darker than mid-grey in a binary PGM (P5)."""
    width, height, pixels = _pgm_pixels(pgm_path)
    dark = sum(1 for b in pixels if b < 128)
    return dark / (width * height)


@unittest.skipUnless(all(shutil.which(t) for t in NEEDED),
                     "poppler/qpdf/ghostscript are required for the redaction path")
class RedactPageCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-redact-reg-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src = fixtures.write(self.tmp / "doc.pdf", fixtures.text_pdf())

    def test_box_lands_on_the_requested_page_and_not_the_first(self):
        note = writeops.redact(self.src, "3", "100", "100", "300", "300")
        self.assertIn("page 3", note)
        dest = str(self.tmp / "doc-redacted.pdf")

        fracs = {}
        for page in (1, 2, 3):
            pgm = _render_gray(dest, page, 40, str(self.tmp / f"p{page}"))
            fracs[page] = _dark_fraction(pgm)

        self.assertGreater(fracs[3], 0.02,
                           "the redaction box must darken the requested page 3")
        self.assertLess(fracs[1], fracs[3] / 3.0,
                        "page 1 must NOT carry the box (it did before the fix)")
        self.assertLess(fracs[2], fracs[3] / 3.0,
                        "page 2 must be left alone")


@unittest.skipUnless(all(shutil.which(t) for t in NEEDED),
                     "poppler/qpdf/ghostscript are required for the redaction path")
class RedactNonA4Case(unittest.TestCase):
    """Regression: the redaction box must land at the requested coordinates.

    Bug pinned: _page_size never parsed the real page size (it split on "size",
    took the ":" token and raised), so it returned the hardcoded A4 (595x842) for
    EVERY page. On a 300x200 page the stamp was built in an A4 coordinate space and
    then scaled onto the real page, so the box landed at the wrong place and size.
    """
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-redact-a4reg-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src = fixtures.write(self.tmp / "small.pdf", fixtures.non_a4_pdf())

    def test_page_size_is_parsed_from_pdfinfo(self):
        self.assertEqual(writeops._page_size(self.src, 1), (300.0, 200.0))

    def test_box_lands_at_the_requested_coordinates(self):
        # Rect (150,100)-(250,160) on a 300x200 page. Its centre in PDF space is
        # (200,130); the rendered pixel there must be dark, and a pixel well
        # outside the box must stay light.
        note = writeops.redact(self.src, "1", "150", "100", "250", "160")
        self.assertIn("page 1", note)
        dest = str(self.tmp / "small-redacted.pdf")
        pgm = _render_gray(dest, 1, 72, str(self.tmp / "p"))
        width, height, pixels = _pgm_pixels(pgm)

        def dark_at(pdf_x, pdf_y):
            col = int(pdf_x / 300.0 * width)
            row = int((200.0 - pdf_y) / 200.0 * height)
            return pixels[row * width + col] < 128

        self.assertTrue(dark_at(200, 130), "the box centre must be dark")
        self.assertFalse(dark_at(30, 30), "outside the box must stay light")

        # The covered area is (100 x 60) / (300 x 200) == exactly 10%. The A4-size
        # bug scaled the box down to ~0.6%, which this bound excludes.
        frac = sum(1 for b in pixels if b < 128) / (width * height)
        self.assertGreater(frac, 0.07, "the box must cover ~10% of the page")
        self.assertLess(frac, 0.13)


if __name__ == "__main__":
    unittest.main()
