"""Unit tests: pdf/docops — tool-invoking read-side operations, with a fake runner."""
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import docops  # noqa: E402

PDFINFO = """Title:          Vertrag
Pages:          3
Encrypted:      no
Page size:      595.28 x 841.89 pts (A4)
File size:      1234 bytes
PDF version:    1.7
Producer:       LibreOffice
"""


class FakeToolsCase(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.outputs = {}
        self.missing = set()
        self._run, self._have = docops.run, docops.have
        docops.run = self._fake_run
        docops.have = lambda tool: tool not in self.missing
        self.addCleanup(setattr, docops, "run", self._run)
        self.addCleanup(setattr, docops, "have", self._have)

    def _fake_run(self, cmd):
        self.calls.append(cmd)
        return self.outputs.get(tuple(cmd), (0, "", ""))

    def last(self):
        return self.calls[-1]


class RealToolsCase(unittest.TestCase):
    def test_run_success(self):
        self.assertEqual(docops.run(["echo", "hi"]), (0, "hi\n", ""))

    def test_run_nonzero(self):
        self.assertEqual(docops.run(["false"])[0], 1)

    def test_have_true_and_false(self):
        self.assertTrue(docops.have("sh"))
        self.assertFalse(docops.have("definitely-not-a-real-binary-xyz"))


class InfoCase(FakeToolsCase):
    def test_parses_fields(self):
        self.outputs[("pdfinfo", "/x.pdf")] = (0, PDFINFO, "")
        text = docops.info_text("/x.pdf")
        self.assertIn("Pages: 3", text)
        self.assertIn("Title: Vertrag", text)

    def test_missing_tool(self):
        self.missing.add("pdfinfo")
        self.assertIn("pdfinfo is not installed", docops.info_text("/x.pdf"))

    def test_failure(self):
        self.outputs[("pdfinfo", "/x.pdf")] = (1, "", "boom")
        self.assertIn("pdfinfo failed", docops.info_text("/x.pdf"))


class CopyCase(FakeToolsCase):
    def test_uses_qpdf(self):
        self.outputs[("qpdf", "--linearize", "--decrypt", "/a.pdf", "/b.pdf")] = (0, "", "")
        self.assertEqual(docops.copy("/a.pdf", "/b.pdf"), "saved /b.pdf")
        self.assertEqual(self.last(), ["qpdf", "--linearize", "--decrypt", "/a.pdf", "/b.pdf"])

    def test_needs_target(self):
        self.assertIn("needs a target", docops.copy("/a.pdf", ""))

    def test_qpdf_failure(self):
        self.outputs[("qpdf", "--linearize", "--decrypt", "/a.pdf", "/b.pdf")] = (1, "", "nope")
        self.assertIn("qpdf failed", docops.copy("/a.pdf", "/b.pdf"))


class PrintCase(FakeToolsCase):
    def test_lp(self):
        self.outputs[("lp", "/a.pdf")] = (0, "request id is X", "")
        self.assertIn("X", docops.print_document("/a.pdf"))

    def test_no_lp(self):
        self.missing.add("lp")
        self.assertIn("no print system", docops.print_document("/a.pdf"))


class AttachmentsCase(FakeToolsCase):
    def test_pdfdetach(self):
        self.outputs[("pdfdetach", "-list", "/a.pdf")] = (0, "1: a.txt\n2: b.bin\n", "")
        self.assertIn("a.txt", docops.attachments("/a.pdf"))

    def test_none(self):
        self.outputs[("pdfdetach", "-list", "/a.pdf")] = (0, "", "")
        self.assertEqual(docops.attachments("/a.pdf"), "no embedded files")

    def test_qpdf_fallback(self):
        self.missing.add("pdfdetach")
        self.outputs[("qpdf", "--list-attachments", "/a.pdf")] = (0, "a.txt\n", "")
        self.assertIn("a.txt", docops.attachments("/a.pdf"))

    def test_qpdf_fallback_empty(self):
        self.missing.add("pdfdetach")
        self.outputs[("qpdf", "--list-attachments", "/a.pdf")] = (0, "", "")
        self.assertEqual(docops.attachments("/a.pdf"), "no embedded files")

    def test_no_tool_at_all(self):
        self.missing.add("pdfdetach")
        self.missing.add("qpdf")
        self.assertEqual(docops.attachments("/a.pdf"), "no attachment tool found")


class LayersCase(FakeToolsCase):
    def test_exposes_ocg_names(self):
        payload = {"qpdf": [{"objects": {
            "5 0 R": {"/Type": "/OCG", "/Name": "Watermark"},
            "6 0 R": {"/Type": "/Page"},
        }}]}
        self.outputs[("qpdf", "--json", "/a.pdf")] = (0, json.dumps(payload), "")
        self.assertIn("Watermark", docops.layers("/a.pdf"))

    def test_none(self):
        self.outputs[("qpdf", "--json", "/a.pdf")] = (0, json.dumps({"qpdf": []}), "")
        self.assertIn("no optional-content", docops.layers("/a.pdf"))

    def test_non_dict_section_ignored(self):
        payload = {"qpdf": [["objects"]]}
        self.outputs[("qpdf", "--json", "/a.pdf")] = (0, json.dumps(payload), "")
        self.assertIn("no optional-content", docops.layers("/a.pdf"))

    def test_ocg_helper_ignores_non_dicts(self):
        self.assertEqual(docops._ocg_names({"1": "not a dict", "2": {"/Type": "/OCG",
                                                                     "/Name": "L"}}), ["L"])


if __name__ == "__main__":
    unittest.main()
