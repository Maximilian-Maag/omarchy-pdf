# omarchy-pdf — architecture

`omarchy-pdf` is a **native, keyboard-driven PDF application** for Omarchy. It is
modelled on qutebrowser: a thin Qt window around a strong engine, with the entire
interaction surface expressed as a *keymap* over a *command* layer.

This document is the contract. Every claim here is enforced by a test somewhere in
`tests/`; the repo's policy checker refuses a source file that is neither a mutation
target nor an explicit exemption.

---

## 1. Why an engine, not a re-implementation

"The PDF standard, completely" means *ISO 32000-2* in practice: the rendering content
model, every stream filter, the 14 standard fonts plus embedded/CMap'd fonts, colour
spaces, transparency and blend groups, optional-content groups, encryption
revisions and the AcroForm/annotation object graphs. Re-implementing that by hand is a
multi-year project and would render worse than every existing engine. The honest
architecture is therefore:

- **Render + parse with a spec-complete engine.** `QtPdf` (`QPdfDocument`) is backed by
  **PDFium**, the Chromium PDF engine — the most complete permissively-licensed renderer
  available, and already present on this machine (Qt 6.11 + PyQt6 on the *system*
  interpreter, `/usr/bin/python3`).
- **Own the interaction.** The viewer, the keymap, the command bar, hint mode, search,
  the outline sidebar and theming are ours. That is the part qutebrowser owns over
  QtWebEngine, and it is the part this plugin owns over QtPdf.

QtPdf gives us, out of the box, and we use all of it:

| QtPdf object | Gives us |
|---|---|
| `QPdfDocument` | page count, page boxes (`pagePointSize`), page **labels**, metadata (Info + XMP), `getAllText`, `getSelection`, `render`, `setPassword`, `pageModel` |
| `QPdfSearchModel` | full-document text search with per-page hits |
| `QPdfLinkModel` | link annotations per page (internal destinations + external URIs) |
| `QPdfBookmarkModel` | the document outline / bookmarks tree |
| `QPdfPageNavigator` | page navigation history |

One thing QtPdf does **not** do for us: `QPdfDocument::render()` returns the page with a
**transparent** background — a PDF normally draws only content and never the white sheet.
The view therefore composites every page onto an opaque `paper` colour (`PdfView._page_pixmap`)
before displaying it. Without that the scene background shows through, and on a dark theme a
page of black text is rendered black-on-black. Enforced by
`tests/test_integration_viewer.py::test_page_composited_on_paper` and the viewer e2e's paper check.

### The one ABI assumption, and how it is kept

PyQt6's QtPdf module is generated against the Qt it was **built** against but links the
`libQt6Pdf.so.6` present at runtime, so the two can disagree. Arch shipped `python-pyqt6
6.11.0-4` built against Qt 6.12 — and without declaring a dependency on the Qt package whose
library it needs — onto systems whose `libQt6Pdf` was still 6.11. The bindings then ask for
the Qt 6.12 overload `QPdfDocument::render(page, size, options, QImage::Format, QColor)`, the
import fails on that undefined symbol, and *every* render path is dead while `pacman` reports
a consistent system. Nothing in the plugin can see that coming from a version string.

`shim/qtpdf-compat.cpp` supplies that single symbol, forwarding to the 4-arg overload both Qt
6.11 and 6.12 export, so it stays correct after the system catches up. The decision to load it
is one script: `bin/omarchy-pdf-qtpdf-compat` prints the library only when the interpreter's
`import PyQt6.QtPdf` fails **on that symbol** *and* preloading the shim makes the very same
interpreter import successfully — an unrecognised ABI gap therefore reports nothing rather
than a bogus fix. The launcher, `tools/run_tests.sh` and `install.sh` all go through that one
decision, so on a coherent system nothing is ever preloaded, and the shim is never loaded.

Enforced by `tests/shell/test_qtpdf_compat.sh` (the decision, plus that the built artifact
really exports the overload under the `Qt_6` version tag) and
`tests/test_integration_qtpdf_binding.py` (a PyQt6 that is installed but cannot import QtPdf
FAILS the suite instead of letting the Qt tests skip it — the silent green that hid exactly
this breakage).

## 2. What PDFium does *not* expose, and how we cover it

QtPdf is a **viewer** engine. Authoring (fill, annotate, sign, redact) is not in its
Python API. Those operations are wired as `:` commands over the CLI tools already on the
machine — `qpdf`, `ghostscript`, `poppler-utils`, `tesseract` — plus the provider-side
QES flow. The split is deliberate and tested: engine for read, tools for write.

| ISO 32000 area | Covered by |
|---|---|
| content rendering, filters, fonts, colour, transparency | PDFium (QtPdf) |
| optional content groups (layers) | PDFium renders; visibility toggled via `qpdf`/state |
| encryption (RC4/AES rev 2–6), open password | `QPdfDocument.setPassword` |
| text extraction / selection / search | QtPdf models + `pdftotext` fallback |
| outline, links, destinations | QtPdf models |
| metadata (Info + XMP) | QtPdf `metaData` + `pdfinfo`/XMP read |
| **forms (AcroForm) fill + save** | `qpdf` structural rewrite + field writer (write-side) |
| **annotations (highlight / text) authoring** | incremental-update writer (write-side) |
| **digital signatures** verify + create | `openssl` CMS/PKCS#7 + `qpdf` byte-range (write-side) |
| **QES / eIDAS Fernsignatur** | provider portal via `omarchy-pdf-sign` (unchanged) |
| OCR (scanned pages) | `tesseract` (write-side) |
| redaction | `ghostscript`/`qpdf` content rewrite (write-side) |

## 3. Layout

```
pdf/                     importable package (installed under share/omarchy-pdf)
  keymap.py     PURE   modes, key-sequence parsing, the bind table, the resolver
  nav.py        PURE   page/scroll/zoom/rotation arithmetic
  hints.py      PURE   hint-label generation and matching
  theme.py      PURE   Omarchy colors.toml -> palette
  commands.py   PURE   command registry, dispatch, completion (over a View protocol)
  docops.py            read-side document operations (qpdf/poppler/pdfinfo)
  pdffile.py           AcroForm fill + annotation authoring (qdf-normalised editor)
  writeops.py          write-side: forms, annotations, signing, redaction, OCR
  view.py              QGraphicsView page renderer (QtPdf-backed)
  statusbar.py         qutebrowser-style status bar
  commandbar.py        ':' command line with completion
  app.py               QMainWindow wiring + entry point
bin/omarchy-pdf          launcher (picks an interpreter that has PyQt6.QtPdf)
bin/omarchy-pdf-qtpdf-compat  decides when the QtPdf ABI compat shim is preloaded
bin/omarchy-toggle-pdf-night, bin/omarchy-pdf-sign, bin/omarchy-webapp-qutebrowser
shim/qtpdf-compat.cpp    the one QtPdf symbol a newer PyQt6 needs and an older Qt lacks
tools/build-qtpdf-compat.sh   builds it (C++ compiler + QtPdf headers)
```

PURE modules import **no Qt** and no third-party package: they are unit-tested directly
and are the mutation targets. The Qt-adjacent modules (`view`, `app`, `statusbar`,
`commandbar`, `hintoverlay`) are exercised by the **offscreen** integration/e2e suites
(`QT_QPA_PLATFORM=offscreen`) and are mutation-`exempt` with a stated reason. The QtPdf
compat helper is a mutation target too — it is the one piece of shell logic whose wrong
answer silently costs you the viewer (see §1).

## 4. The View protocol

`commands.py` never imports Qt. Every command is a function
`(view, argv) -> None` where `view` satisfies a small protocol:

```
view.page_count() -> int            view.current_page() -> int
view.goto_page(n)                   view.page_label(n) -> str
view.scroll(dy, dx)                 view.scroll_pages(dy)
view.zoom(delta_pct=None, set_pct=None, mode=None)   view.zoom_percent() -> int
view.rotate(delta)                  view.rotation() -> int
view.search(text)                   view.search_next()   view.search_prev()
view.clear_search()                 view.search_query() -> str
view.mode() / view.set_mode(mode)   view.message(text, level="info")
view.open_hints(kind="follow")      view.activate_hint(label)
view.yank(text)                     view.open_url(url)
view.outline() -> list[tuple[int,str,int]]   view.toggle_sidebar()
view.load(path, password=None)      view.path() -> str
view.quit()
```

This is what lets the *entire* vim workflow be tested head-less against a fake view, and
why the keymap/command layer can reach 100 % mutation kill without a display.

## 5. Keymap

Modes: `normal`, `command` (the `:` line), `search` (the `/` line), `hint`, `visual`.

A *key sequence* is a string; `<C-d>` and `<Esc>` are single tokens, `gg` is two. The
resolver is prefix-aware, exactly like vim: a buffer that is a complete binding **and** a
prefix of a longer binding stays `PENDING` until the next key (or the timeout `flush()`
fires the shorter binding). This is what lets `g` (unbound) precede `gg`/`gu`.

Default bindings (a superset of the proposal; the authoritative list is `keymap.py`):

```
motion     j k h l  <C-d> <C-u> <C-f> <C-b>  J K  gg G  H M L  <Space>
zoom       + - =    zi zo zw  zp
rotate     r R
search     / ?      n N      <Esc>
hints      f F
open       o O t w
yank       y Y
marks      m        '        ``(backtick)
doc ops    i (info)  s (save)  p (print)  a (attachments)  l (layers)
write ops  e (forms)  A (annotate)  S (sign)  x (redact)  C (ocr)   [write-side tier]
command    :        q (quit)  ? (help)
```

## 6. Commands

`:` opens the command bar with tab-completion over the registry. Commands map 1:1 onto
both the keymap and the CLI, so `omarchy-pdf --command "goto 12"` can drive a *running*
instance (single-instance, over a UNIX socket) for scripting and tests.

## 7. Testing

Every kind the repo promises, in `tools/run_tests.sh`:

- **unit** (`tests/test_unit_*.py`) — pure modules against a fake view.
- **regression** (`tests/test_regression_*.py`) — the v1 commands (night toggle, sign,
  webapp shim) still behave.
- **integration** — offscreen Qt: build the real window against a throwaway config,
  drive it with synthesized keys, assert document state; plus the guard that a PyQt6
  which is installed but cannot import QtPdf fails here instead of skipping.
- **e2e** (`tests/e2e/*.sh`) — boot the real app heads-down, render a fixture PDF,
  quit; plus the v1 wiring chains.
- **mutation** (`tools/mutator.py`, `tests/mutation.json`) — floor 0.85 over the PURE
  modules and the `bin/` shell targets, with proven `equivalent` survivors only.
- **policy as code** (`tools/policy_check.py`) — the usual plugin rules, plus a
  no-test-gaps gate that forces every shipped source to be mutated or exempted.

## 8. Theming

The palette is read from the **applied** theme
(`~/.local/state/omarchy/current/theme/colors.toml`), never a hardcoded table. The
`theme-set` hook re-reads it, so switching the desktop theme recolours the viewer with
no config edit. `theme.py` is pure and tested against fixtures.
