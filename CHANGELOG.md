# Changelog

All notable changes to omarchy-pdf are documented here.

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
