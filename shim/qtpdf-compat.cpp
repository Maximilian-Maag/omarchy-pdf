// omarchy-pdf — QtPdf ABI compatibility shim.
//
// Why this exists. PyQt6's QtPdf module is generated against the Qt version it was
// BUILT against, but it links the *soname* (libQt6Pdf.so.6) found at runtime. Qt 6.12
// replaced the single
//
//     QImage QPdfDocument::render(int page, QSize imageSize,
//                                 QPdfDocumentRenderOptions options = {});
//
// with
//
//     QImage QPdfDocument::render(int page, QSize imageSize,
//                                 QPdfDocumentRenderOptions options = {},
//                                 QImage::Format format = QImage::Format_ARGB32,
//                                 QColor fillColor = Qt::transparent);
//
// keeping the old 4-arg symbol for binary compatibility. A PyQt6 built against 6.12
// (Arch shipped python-pyqt6 6.11.0-4 that way, without declaring a dependency on the
// Qt package whose library it needs) therefore asks for the 5-arg symbol, and on a
// system whose libQt6Pdf is still 6.11 the import dies with
//
//     undefined symbol: _ZN12QPdfDocument6renderEi5QSize25QPdfDocumentRenderOptions
//                       N6QImage6FormatE6QColor, version Qt_6
//
// and the whole viewer with it. This file supplies exactly that one symbol and
// forwards to the 4-arg overload — which BOTH Qt 6.11 and 6.12 export — so the shim
// keeps working after the system catches up, and is simply no longer loaded then
// (bin/omarchy-pdf-qtpdf-compat only asks for the preload while the gap exists).
//
// The class in the installed (6.11) header declares no such member, so the symbol is
// emitted from a free function carrying the exact mangled name; the implicit `this`
// is the first argument. Nothing else is exported (see qtpdf-compat.map), and the
// version tag Qt_6 has to match the reference.
//
// Build: tools/build-qtpdf-compat.sh    Test: tests/shell/test_qtpdf_compat.sh

#include <QtPdf/QPdfDocument>
#include <QtGui/QColor>
#include <QtGui/QImage>
#include <QtGui/QPainter>

extern "C" QImage shim_render(QPdfDocument *self, int page, QSize imageSize,
                              QPdfDocumentRenderOptions options, QImage::Format format,
                              QColor fillColor)
    asm("_ZN12QPdfDocument6renderEi5QSize25QPdfDocumentRenderOptionsN6QImage6FormatE6QColor");

// The 5-arg overload, in terms of the 4-arg one.
extern "C" QImage shim_render(QPdfDocument *self, int page, QSize imageSize,
                              QPdfDocumentRenderOptions options, QImage::Format format,
                              QColor fillColor)
{
  const QImage rendered = self->render(page, imageSize, options);
  // Qt's own default: hand the page back untouched, so a caller that passes the
  // documented defaults gets byte-for-byte what the 4-arg overload returns.
  if (format == QImage::Format_ARGB32 && fillColor == QColor(Qt::transparent)) {
    return rendered;
  }
  QImage out(imageSize, format);
  out.fill(fillColor);
  QPainter painter(&out);
  painter.drawImage(0, 0, rendered);
  painter.end();
  return out;
}
