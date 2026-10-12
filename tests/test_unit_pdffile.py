"""Unit tests: pdf/pdffile — the pure object-editor functions and the authoring path.

The pure functions are tested directly on bytes; fill_form/add_annotation are
exercised end to end when qpdf is present (the only external dependency).
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import fixtures  # noqa: E402
from pdf import pdffile  # noqa: E402

HAVE_QPDF = shutil.which("qpdf") is not None


class RunCase(unittest.TestCase):
    def test_success(self):
        self.assertEqual(pdffile.run(["echo", "hi"]), (0, "hi\n", ""))

    def test_nonzero(self):
        self.assertEqual(pdffile.run(["false"])[0], 1)

    def test_missing_binary_is_swallowed(self):
        code, out, err = pdffile.run(["definitely-not-a-real-binary-xyz"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err)

    def test_have(self):
        self.assertFalse(pdffile.have("definitely-not-a-real-binary-xyz"))


class ParseCase(unittest.TestCase):
    def setUp(self):
        self.data = fixtures.text_pdf()

    def test_parse_object_count(self):
        objects = pdffile.parse_objects(self.data)
        self.assertEqual(sorted(objects), list(range(1, 13)))

    def test_parse_finds_catalog(self):
        objects = pdffile.parse_objects(self.data)
        self.assertIn(b"/Type /Catalog", objects[1])

    def test_trailer_root_and_size(self):
        trailer = pdffile.trailer_dict(self.data)
        self.assertEqual(trailer.get("Root"), "1 0 R")
        self.assertEqual(trailer.get("Size"), "13")

    def test_previous_xref_is_offset(self):
        self.assertGreater(pdffile.previous_xref(self.data), 0)


class FieldCase(unittest.TestCase):
    def setUp(self):
        self.objects = pdffile.parse_objects(fixtures.form_pdf())

    def test_field_names(self):
        self.assertEqual(sorted(pdffile.field_names(self.objects)), ["agree", "full name"])

    def test_text_field_set(self):
        found = pdffile._values_for(self.objects, "full name", "Ada Lovelace")
        self.assertIsNotNone(found)
        self.assertIn(b"Ada Lovelace", found[1])

    def test_checkbox_set_on(self):
        found = pdffile._values_for(self.objects, "agree", "on")
        self.assertIsNotNone(found)
        self.assertIn(b"/AS /Yes", found[1])

    def test_checkbox_set_off(self):
        found = pdffile._values_for(self.objects, "agree", "no")
        self.assertIn(b"/AS /Off", found[1])

    def test_unknown_field_is_none(self):
        self.assertIsNone(pdffile._values_for(self.objects, "nope", "x"))


class StringCase(unittest.TestCase):
    def test_ascii_round_trip(self):
        self.assertEqual(pdffile._decode_pdf_string(pdffile._encode_pdf_string("hi")),
                         "hi")

    def test_unicode_round_trip(self):
        self.assertEqual(pdffile._decode_pdf_string(pdffile._encode_pdf_string("Grüße")),
                         "Grüße")

    def test_parentheses_escaped(self):
        self.assertIn(b"\\(", pdffile._encode_pdf_string("a(b)c"))

    def test_unterminated_paren_left_alone(self):
        self.assertEqual(pdffile._decode_pdf_string(b"(open"), "(open")

    def test_unterminated_angle_left_alone(self):
        self.assertEqual(pdffile._decode_pdf_string(b"<open"), "<open")

    def test_high_byte_uses_hex(self):
        # ord 128 is the first code point that is NOT plain ASCII -> hex form
        self.assertTrue(pdffile._encode_pdf_string("\x80").startswith(b"<"))


class SetKeyCase(unittest.TestCase):
    def test_replace(self):
        self.assertEqual(pdffile._set_key(b"<< /V (old) >>", b"V", b"(new)"),
                         b"<< /V (new) >>")

    def test_insert_when_absent(self):
        self.assertEqual(pdffile._set_key(b"<< /FT /Tx >>", b"V", b"(x)"),
                         b"<< /FT /Tx /V (x) >>")

    def test_insert_without_close(self):
        self.assertEqual(pdffile._set_key(b"/FT /Tx", b"V", b"(x)"),
                         b"/FT /Tx /V (x) >>")


@unittest.skipUnless(HAVE_QPDF, "qpdf is required for the authoring path")
class AuthorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-author-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src = fixtures.write(self.tmp / "form.pdf", fixtures.form_pdf())

    def test_fill_writes_and_persists(self):
        dest = str(self.tmp / "filled.pdf")
        note = pdffile.fill_form(self.src, {"full name": "Ada", "agree": "on"}, dest)
        self.assertIn("filled 2 field(s)", note)
        base, error = pdffile._normalise(dest)
        self.assertEqual(error, "")
        objects = pdffile.parse_objects(base)
        body = next(b for b in objects.values() if b"/T (full name)" in b)
        self.assertIn(b"Ada", body)

    def test_fill_reports_missing(self):
        note = pdffile.fill_form(self.src, {"full name": "Ada", "ghost": "x"},
                                 str(self.tmp / "f2.pdf"))
        self.assertIn("missing: ghost", note)

    def test_fill_no_match(self):
        note = pdffile.fill_form(self.src, {"ghost": "x"}, str(self.tmp / "f3.pdf"))
        self.assertIn("no matching fields", note)

    def test_add_annotation(self):
        dest = str(self.tmp / "annot.pdf")
        note = pdffile.add_annotation(self.src, 0, (10, 10, 50, 50), "note", dest)
        self.assertIn("Text annotation", note)
        base, _err = pdffile._normalise(dest)
        self.assertIsNotNone(base)
        self.assertIn(b"/Text", base)

    def test_page_object_out_of_range(self):
        objects = pdffile.parse_objects(fixtures.form_pdf())
        self.assertIsNone(pdffile._page_object(objects, 1))

    def test_annotation_bad_page(self):
        note = pdffile.add_annotation(self.src, 99, (0, 0, 1, 1), "x",
                                      str(self.tmp / "a2.pdf"))
        self.assertIn("no page", note)


if __name__ == "__main__":
    unittest.main()
