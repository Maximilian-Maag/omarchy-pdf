# Changelog

All notable changes to omarchy-pdf are documented here.

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
