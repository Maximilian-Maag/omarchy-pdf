# Changelog

All notable changes to omarchy-pdf are documented here.

## [Unreleased]

### Added
- **Page colour: `off`, `invert` and the accessible `contrast` effect** (`<Ctrl-n>`,
  `:night <on|off|invert|contrast|toggle>`). The page is composited onto paper first and the
  effect is applied to that sheet, so an inverted page is black paper with light text rather
  than transparent paper showing the dark scene behind it. `contrast` maps the sheet's light
  areas onto the theme foreground and its dark areas onto black — yellow-on-black under the
  stock theme — which is what makes a page readable at high magnification; a plain channel
  flip is available as `invert`. The grey-to-colour table is built by the new pure
  `pdf/night.py`, and the Qt side applies it as a palette swap, not a per-pixel Python loop.
- **`Super+Ctrl+N` now reaches this viewer.** `omarchy-toggle-pdf-night` writes
  `org.gnome.Papers night-mode`, which is Papers' key: the PDFs on this machine open in
  omarchy-pdf, so the key did nothing visible in the app the reader was looking at. The
  viewer reads that key at start-up and follows it live with `gsettings monitor`, so one
  switch drives whichever reader is open. Where gsettings is absent the key is simply off, and
  `OMARCHY_PDF_GSETTINGS=0` turns the whole wiring off for tests and bare hosts.

### Fixed
- **`f` dead-ended on pages without link annotations.** Most prose pages of a book have no
  annotations at all — 105 of 188 in the reference book do — so the key the workflow is built
  around answered `no links in view` exactly where the reader stood, and there was no way to
  reach the table of contents or the bibliography from there. `f` now falls back to the
  document's outline: every entry becomes a label, and typing it jumps to that chapter.
  `F` (external links only) keeps its strict meaning.
- **Hint destinations were only ever shown as boxes on the page.** A magnified reader sees a
  fragment of the sheet, so the labels can be somewhere other than the visible area — and an
  outline entry has no box to paint on at all. They are also spoken in the status line
  (`a→S.12  s→S.31`), and the destinations have their own keys: `<Ctrl-t>` and `T` (`:places`)
  open them as a
  panel in the **centre** of the window, in type larger than the window's own, chapters with
  their sub-sections nested underneath. `Up`/`Down` walk it, `Right`/`Left` open and close a
  chapter, `Return` jumps to the entry, `Esc` closes. It is not `f`: a panel over the page
  would cover the letters `f` paints.
- **The `:` prompt accepted nothing it could have suggested.** Typing a command meant
  remembering its exact name. The prompt now lists what matches as you type, with each
  command's help beside it: `Up`/`Down` choose, `Tab` completes, `Return` runs the chosen one
  (or exactly what you typed, if it takes arguments).
- **`omarchy-pdf` is a long name for the command you type most.** `opf` is installed as a
  symlink to the same launcher, so both spellings exist and there is still one program.
- **"That key did nothing" feedback expired before it could be read.** Errors (no links, no
  outline, bad command) now stay on the status bar for ten seconds instead of five.
- **The e2e suite skipped itself on exactly the hosts that need the QtPdf shim.** Its
  interpreter probe ran the bare `import PyQt6.QtPdf`, which fails while the compat library
  is not preloaded — so on this machine the whole end-to-end pass reported "skip" instead of
  booting the app. The probe now tries the shim as well, and the real window is exercised.
- **Internal links and outline entries jumped to the page, not to the mark.** `goto_page`
  centred the *page*, so on a page taller than the window the page top sat above the
  viewport and a heading 50 pt below it ended up off-screen: on a real 56-page book at
  fit-width, 8 of the first 24 outline entries landed outside the window. The destination
  point (`QPdfLink.location()`, `QPdfBookmarkModel.Role.Location`) is now mapped through
  the page's zoom and rotation and placed near the top of the window, which is what every
  other reader does.
- **The outline sidebar was mouse-only.** `t` revealed the dock and left the focus in the
  view, so arrow keys went to the page and `itemActivated` — the only keyboard path into
  the tree — was unreachable. `t` now focuses the tree on the entry for the page being
  read, `Enter` jumps and returns the keys to the page, and `Esc` leaves the outline.
- **`f` showed no hints on a page whose links sat on the sheet above it.** Targets were
  collected from `_page` — the page nearest the viewport centre — so on a fit-page spread
  (or a document whose links end on the neighbouring sheet) pressing `f` reported "0 hints"
  with the links plainly on screen. Every page intersecting the viewport is hinted now, the
  current one first, and only the link boxes that are actually inside it — so a page taller
  than the window no longer counts links below the fold.
- **Hint labels could be painted under the page.** Page pixmaps go into the scene at z 0 and
  are removed and re-inserted on every layout rebuild (`+ - zw zp`, `r R`), so an overlay at
  the same z ended up *below* the pages after a re-render: mode still `hint`, the labels
  still matched keys, nothing visible. Overlay chrome now carries `OVERLAY_Z`, so it stays
  above the paper — search highlights included.
- **Hint labels were 11 pt whatever the zoom.** They are placed in scene units, next to page
  text that a magnified reading session has scaled to 200–300 %, so a label was a few
  pixels wide and read as "the hints never appear". The font now follows the zoom, and each
  label is centred on its link on an accent plate, so it stays legible over a coloured page
  area as well as over text.
- **`f` on a page with nothing to hint entered a mode that ate the next keystroke.** Opening
  hint mode with zero targets left an empty page, and the next key was consumed as a bad
  label ("no such hint") — a scroll that silently did not happen. It now reports "no links
  in view" and stays in normal mode.
- **Pressing `q` aborted the whole viewer instead of closing it.** `h_quit` called
  `view.quit()`, a method `PdfView` never had; the `AttributeError` was raised inside the
  reimplemented `keyPressEvent`, where PyQt6 escalates an unhandled exception to `qFatal()`
  — so `q` and `<C-q>` dumped core with SIGABRT from 2.0.0 onwards. The view now closes its
  window, and the integration suite drives the real key rather than the fake view that had
  a `quit()` the real one lacked.
- **Clicking a link in a PDF did nothing.** `pdf/view.py` had no mouse handling at all, so
  a click on a link annotation was swallowed by `QGraphicsView` and a perfectly healthy
  link read as broken — the keyboard hint (`f` + label) was the only way in, and nothing
  on screen said so. A plain left click now follows the link (internal destination → jump,
  external URI → browser), the pointer turns into a hand over one, and hint mode keeps the
  click for itself so a label can still be typed.
- **Hint labels drifted off the link as soon as the page was zoomed.** `open_hints()` placed
  `QPdfLinkModel` rectangles — which are always in PDF points — by translating them with the
  page origin and nothing else, which is only right at 100 % and 0°. They are now mapped
  through the page's zoom and, on a rotated page, rotated about the page centre; the pointer
  hit-test uses the same mapping, so the box that names a link is the box that clicks it.
- **`F` (`hint-open`) did exactly the same thing as `f`.** `open_hints(kind)` accepted the
  kind and never read it, so "open a link in the browser" could not differ from "follow a
  link". `F` now lists only the links that have a URL, which is what it promises.

## [2.0.6] — 2026-11-02

### Fixed
- **A viewer that was dead while the suite reported a green run.** PyQt6's QtPdf module is
  generated against the Qt it was *built* against but links the `libQt6Pdf.so.6` present at
  runtime. `python-pyqt6 6.11.0-4` was built against Qt 6.12 and therefore asks for the Qt 6.12
  overload `QPdfDocument::render(int, QSize, QPdfDocumentRenderOptions, QImage::Format, QColor)`
  — a symbol a system whose QtPdf is still 6.11 does not export. `import PyQt6.QtPdf` then dies
  with an undefined symbol, so *every* render path was dead (Super+D printed "no python3 with
  PyQt6.QtPdf"), while `pacman` saw a consistent system: `python-pyqt6` declares no dependency
  on the Qt package whose library it needs. Worse, the Qt integration suite silently skipped
  its 20 Qt tests and still said OK, so the breakage was invisible from the test output.

### Added
- **`shim/qtpdf-compat.cpp` — a one-symbol ABI compat library.** It defines the Qt 6.12
  `QPdfDocument::render` overload (emitted from a free function carrying the exact mangled
  name, since the installed header declares no such member) and forwards to the 4-arg overload
  that both Qt 6.11 and 6.12 still export, so it stays correct after the system catches up.
  Verified byte-identical to the render through the older bindings, and the plugin's own
  integration suite (24 tests) plus the viewer e2e render real pages under it.
- **`bin/omarchy-pdf-qtpdf-compat` — the one decision about it.** It prints the library only
  when the interpreter's `import PyQt6.QtPdf` fails *on that symbol* and preloading the shim
  makes that very interpreter import — proven, not assumed — so an unrecognised ABI gap (or a
  missing PyQt6) reports nothing instead of handing the launcher a bogus fix. The launcher,
  `tools/run_tests.sh` and `install.sh` all go through it; on a coherent system nothing is ever
  preloaded. `tools/build-qtpdf-compat.sh` builds the shim (C++ compiler + QtPdf headers), and
  `install.sh` installs it beside the plugin; no package is downgraded and no Qt file is
  replaced.
- **`tests/test_integration_qtpdf_binding.py` — the guard against the silent green.** PyQt6
  installed but unable to import QtPdf is now a FAILED test that names the cause and the fix,
  instead of a skipped Qt suite. `tests/shell/test_qtpdf_compat.sh` drives the decision with
  stub interpreters and checks the built artifact really exports the overload under the `Qt_6`
  version tag; `tools/run_tests.sh` preloads the shim so the Qt tests RUN rather than skip
  (20 skipped tests → 24 that execute).

## [2.0.5] — 2026-10-17

### Fixed
- **The Qt-driving tests depended on the caller's environment for their platform.** They set
  `QT_QPA_PLATFORM` with `setdefault`, and the desktop session exports
  `QT_QPA_PLATFORM=wayland;xcb`, so the intended offscreen platform never applied — the tests
  then ran against a real display (and could take the user's focus). Both `test_integration_viewer.py`
  and `test_viewer_e2e.sh` now assign it outright. Found while chasing the same bug in
  omarchy-qutebrowser's JS harness, where it produced a different set of failures every run.

## [2.0.4] — 2026-10-17

### Fixed
- **`l` did not scroll right — it listed layers, and the vim motion was dead.** `l` was in
  the normal-mode bind table **twice** (`scroll-right`, then `layers`); in a dict literal the
  later key wins silently, so `l` listed optional-content groups and `scroll-right` could
  never fire. Layers moved to **`<Ctrl-l>`**, and `l` is scroll-right again.
- Guarded by a test that reads the bind table's **source** (a duplicate is invisible after
  import, because the literal collapses): it fails with
  `duplicate bindings in mode 'normal': ['l']` if the collision returns — proven by
  reintroducing it. Plus `l`/`<Ctrl-l>` resolution tests, and the docs updated.

## [2.0.3] — 2026-10-17

### Fixed
- **`:layers` (the `l` key) was a silent no-op — it always answered "no optional-content
  layers".** `qpdf >= 11` defaults `--json` to version 2, a format with **no object table**,
  so the OCG scan had nothing to read. The unit tests passed because their fake runner
  returned the pre-11 shape (`qpdf[*].objects`) that a real qpdf no longer emits — the tests
  had pinned the bug. `layers()` now requests the object table explicitly
  (`--json=1 --json-key=objects`) and accepts both the top-level and nested shapes, with a
  fallback for a qpdf too old to know the flag. Found by opening a real document that carries
  an OCG. Guarded by a **real-qpdf** test over a new `layer_pdf` fixture (plus the
  top-level / nested / fallback / bad-json cases).

## [2.0.2] — 2026-10-17

### Fixed
- **Pages rendered black-on-black on a dark theme.** `QPdfDocument::render()` returns a
  page with a **transparent** background (a PDF draws only its content and never paints
  the white sheet), so that transparent area revealed the scene background — the dark
  theme colour — and a page of black text was rendered black-on-black, illegible.
  Measured on the real desktop with `Ghostscript.pdf`: page 1 came out black, and the
  render differed from poppler (`pdftoppm`) by **RMSE 0.965**. The view now composites
  every page onto opaque `paper` (`PdfView._page_pixmap`) before displaying it; the same
  page now matches poppler to **RMSE 0.039**. Guarded by
  `tests/test_integration_viewer.py::test_page_composited_on_paper` and the viewer e2e's
  paper check — both fail on the transparent render.

## [2.0.1] — 2026-10-12

### Fixed
- **CI was red on the 2.0.0 commit** for a reason the local run hid: the workflow
  installed nothing, so `qpdf` and PyQt6/QtPdf were absent on the runner. The
  authoring path (`pdf/pdffile.py`) and the offscreen Qt suites were therefore
  skipped, and `pdf/pdffile.py` read **0.78 < 0.85**. The workflow now installs the
  runtime deps (`qpdf`, the PyQt6 wheel — which carries QtPdf, unlike Ubuntu's
  `python3-pyqt6` — and the libs an offscreen Qt needs).
- `pdf/pdffile.py`'s pure paths (`incremental_update`, `_page_object`, the
  `_normalise` failure branch) now have qpdf-free unit tests, so their mutants die
  even where `qpdf` is absent — the score no longer depends on an external tool
  being installed.
- The offscreen Qt **integration** suite and the **viewer e2e** now SKIP (rather
  than fail) when no interpreter provides `PyQt6.QtPdf`.
- The viewer e2e's render check accepts any number of rendered pages (`>= 1`)
  instead of exactly one — the offscreen viewport renders a different page count
  on the runner than on the dev box.

## [2.0.0] — 2026-10-12

### Added
- **`omarchy-pdf`** — a native, keyboard-driven viewer with a vim workflow, modelled
  on qutebrowser:
  - rendering through **QtPdf / PDFium** (spec-complete; all stream filters, fonts,
    colour, transparency, encryption revisions, page labels and boxes);
  - a pure keymap + command layer (`pdf/keymap.py`, `pdf/commands.py`): `hjkl`,
    `<C-d>/<C-u>`, `<C-f>/<C-b>`, `gg/G`, `H/M/L`, zoom/rotate, marks, history;
  - qutebrowser-shaped chrome: `:` command bar with tab-completion, `/` incremental
    search with `n/N`, `f` **hint mode** over links, an outline sidebar and a status bar;
  - outline/links/text-selection/yank, metadata, attachments, layers, printing,
    password unlocks, `--command` scripting, and a themable surface that reads the
    applied Omarchy `colors.toml`.
- **Write side** (`pdf/pdffile.py`, `pdf/writeops.py`): AcroForm **fill + save** and
  annotation authoring via a qdf-normalised incremental-update object editor;
  **real rasterising redaction** (pdftocairo + stamp + overlay); **OCR** text layer
  (pdftoppm + tesseract); **PKCS#7 verify** (pdfsig) with the QES/sign-me path kept.
- **Read side** (`pdf/docops.py`): `info`, `save-as`, `print`, `attachments`, `layers`.
- Tests for every kind: unit (pure modules + `pdffile`/`docops` with fakes),
  regression (the v1 CLIs), offscreen **integration** driving the real window,
  shell + **e2e** (boots the real app through the real launcher and renders pixels),
  and mutation targets over the pure modules.

### Changed
- `Super+D` now opens the native **omarchy-pdf** viewer (Papers remains available and
  is still the fallback for interactive form workflows).

## [1.0.0] — 2026-10-11

### Added
- `omarchy-toggle-pdf-night` — toggles Papers' night mode (dark ⇄ light rendering),
  reads it back with `--status`, default dark; bound to `Super+Ctrl+N`.
- `omarchy-pdf-sign` — opens the D-Trust sign-me portal in the default browser to
  sign a PDF with a qualified electronic signature (eIDAS Fernsignatur); bound to
  `Super+Shift+Q`, also a PDF "Open With" entry.
- `omarchy-webapp-qutebrowser` — routes Omarchy's Chromium-forced web-app launches
  through qutebrowser, so web-apps keep working with Chromium removed.
- Papers set as the default `application/pdf` handler (reading + AcroForm form fill).
- Test harness: policy as code plus unit, regression, integration, shell, e2e and
  mutation tests, with `tools/run_tests.sh` as the single entry point and CI running
  it (.github/workflows/test.yml). Mutation score is enforced at >= 0.85, and no
  source file may be left neither mutated nor exempted with a reason.

Initial release.
