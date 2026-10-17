"""Unit tests: pdf/docops — tool-invoking read-side operations, with a fake runner."""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from pdf import docops  # noqa: E402
import fixtures  # noqa: E402

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
    JSON_V1 = ["qpdf", "--json=1", "--json-key=objects", "/a.pdf"]

    def test_exposes_ocg_names_top_level(self):
        # qpdf >= 11 with --json=1 puts the object table at the TOP level (this is the
        # shape the real tool emits; the old test only knew the nested one, which is why
        # `layers()` was a silent no-op on qpdf 12).
        payload = {"objects": {
            "5 0 R": {"/Type": "/OCG", "/Name": "Watermark"},
            "6 0 R": {"/Type": "/Page"},
        }}
        self.outputs[tuple(self.JSON_V1)] = (0, json.dumps(payload), "")
        self.assertIn("Watermark", docops.layers("/a.pdf"))
        self.assertEqual(self.last(), self.JSON_V1)

    def test_exposes_ocg_names_nested(self):
        # older qpdf nested the object table under qpdf[*].objects — keep working too
        payload = {"qpdf": [{"objects": {
            "5 0 R": {"/Type": "/OCG", "/Name": "Watermark"},
            "6 0 R": {"/Type": "/Page"},
        }}]}
        self.outputs[tuple(self.JSON_V1)] = (0, json.dumps(payload), "")
        self.assertIn("Watermark", docops.layers("/a.pdf"))

    def test_none(self):
        self.outputs[tuple(self.JSON_V1)] = (0, json.dumps({"objects": {}}), "")
        self.assertIn("no optional-content", docops.layers("/a.pdf"))

    def test_non_dict_section_ignored(self):
        payload = {"qpdf": [["objects"]]}
        self.outputs[tuple(self.JSON_V1)] = (0, json.dumps(payload), "")
        self.assertIn("no optional-content", docops.layers("/a.pdf"))

    def test_v1_flag_unsupported_falls_back(self):
        # a very old qpdf rejects --json=1; the bare --json fallback is used instead
        self.outputs[tuple(self.JSON_V1)] = (1, "", "unknown option")
        self.outputs[("qpdf", "--json", "/a.pdf")] = (
            0, json.dumps({"objects": {"5 0 R": {"/Type": "/OCG", "/Name": "Old"}}}), "")
        self.assertIn("Old", docops.layers("/a.pdf"))

    def test_bad_json(self):
        self.outputs[tuple(self.JSON_V1)] = (0, "not json", "")
        self.assertIn("could not read", docops.layers("/a.pdf"))

    def test_qpdf_failure(self):
        self.outputs[tuple(self.JSON_V1)] = (1, "", "boom")
        self.outputs[("qpdf", "--json", "/a.pdf")] = (1, "", "boom")
        self.assertIn("qpdf failed", docops.layers("/a.pdf"))

    def test_ocg_helper_ignores_non_dicts(self):
        self.assertEqual(docops._ocg_names({"1": "not a dict", "2": {"/Type": "/OCG",
                                                                     "/Name": "L"}}), ["L"])

    def test_object_maps_merges_both_shapes(self):
        data = {"objects": {"1": {"/Type": "/OCG", "/Name": "top"}},
                "qpdf": [{"objects": {"2": {"/Type": "/OCG", "/Name": "nested"}}}]}
        self.assertEqual(set(docops._object_maps(data)), {"1", "2"})

    def test_object_maps_ignores_junk(self):
        self.assertEqual(docops._object_maps({"objects": "no", "qpdf": [1, None, {}]}), {})


class RealQpdfLayersCase(unittest.TestCase):
    """The mocked LayersCase pinned a JSON shape qpdf >= 11 never emits, so `l` was a
    silent no-op on the real tool. This drives the REAL qpdf against a real OCG PDF —
    the test that would have caught it."""

    @unittest.skipUnless(docops.have("qpdf"), "qpdf not installed")
    def test_real_qpdf_finds_a_layer(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-layers-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        path = fixtures.write(tmp / "layer.pdf", fixtures.layer_pdf())
        self.assertIn("Watermark", docops.layers(path))

    @unittest.skipUnless(docops.have("qpdf"), "qpdf not installed")
    def test_real_qpdf_reports_none_without_layers(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="pdf-layers-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        path = fixtures.write(tmp / "plain.pdf", fixtures.text_pdf())
        self.assertEqual(docops.layers(path), "no optional-content layers")


if __name__ == "__main__":
    unittest.main()
