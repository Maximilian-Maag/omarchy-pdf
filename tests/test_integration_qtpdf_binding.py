"""Integration guard: PyQt6's QtPdf module must load whenever PyQt6 is installed.

Every other test in the Qt suite SKIPS when ``import PyQt6.QtPdf`` fails. That is right
for a machine with no PyQt6 at all, and wrong for the state this guard exists for: the
package is installed, only its QtPdf bindings cannot load (they were generated against
a newer Qt than the installed ``libQt6Pdf`` exports — the symbol PyQt6 6.11.0-4 asks
for, ``QPdfDocument::render(int, QSize, QPdfDocumentRenderOptions, QImage::Format,
QColor)``, is a Qt 6.12 addition). Then the entire viewer is dead — every render path
needs QtPdf — while the suite reports a green run with most tests skipped. That silent
green is exactly what this test refuses.

tools/run_tests.sh preloads ``shim/qtpdf-compat.cpp`` when bin/omarchy-pdf-qtpdf-compat
reports that gap, so the normal harness passes here; running the Qt suite by hand
without that preload is what this catches.
"""
import importlib.util
import unittest


def pyqt6_installed() -> bool:
    """True when the PyQt6 package is present — without importing its Qt modules."""
    try:
        return importlib.util.find_spec("PyQt6") is not None
    except (ImportError, ValueError):
        return False


class QtPdfBindingCase(unittest.TestCase):
    def test_qtpdf_loads_when_pyqt6_is_installed(self):
        try:
            import PyQt6.QtPdf  # noqa: F401
        except ImportError as exc:
            if not pyqt6_installed():
                self.skipTest("PyQt6 is not installed at all")
            self.fail(
                "PyQt6 is installed, but its QtPdf module cannot load, so nothing in "
                "this viewer can render: %s\n"
                "When the symbol is QPdfDocument::render, the bindings were built "
                "against a newer QtPdf than this system's libQt6Pdf exports: build the "
                "compat shim with tools/build-qtpdf-compat.sh, install it "
                "(install.sh puts it under the plugin's share dir) and let "
                "bin/omarchy-pdf-qtpdf-compat point the launcher at it." % exc
            )
        else:
            self.assertTrue(hasattr(PyQt6.QtPdf, "QPdfDocument"),
                            "PyQt6.QtPdf imported but exposes no QPdfDocument")


if __name__ == "__main__":
    unittest.main()
