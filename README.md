# omarchy-pdf

A **native, keyboard-driven PDF application** for [Omarchy](https://omarchy.org/) —
a qutebrowser-shaped viewer with a **vim workflow**, plus a straight path to
signing, filling, redacting and OCR-ing documents.

Reading and rendering are done by **QtPdf (PDFium)**, the same spec-complete engine
Chromium ships: every stream filter, the standard and embedded fonts, colour spaces,
transparency and blend groups, optional-content groups, and encryption revisions. The
*vim interaction* — hint mode, the `:` command bar, `/search`, marks — is ours, exactly
the way qutebrowser owns its interaction over QtWebEngine.

## The viewer

| Keys | Action |
|------|--------|
| `j` `k` `h` `l` | scroll |
| `<Ctrl-d>` `<Ctrl-u>` | half-page down / up |
| `<Ctrl-f>` `<Ctrl-b>`, `J` `K`, `<Space>` | next / previous page |
| `gg` `G` | first / last page |
| `H` `M` `L` | top / middle / bottom of the page |
| `+` `-` `=` | zoom in / out / reset |
| `zw` `zp` | fit width / fit page |
| `r` `R` | rotate 90° cw / ccw |
| `/` `?` | search forward / backward (then `n` `N`) |
| `f` `F` | **hint mode** — follow / open links by label |
| `<Ctrl-o>` `<Ctrl-i>` | history back / forward |
| `o` | open a document |
| `t` `b` | toggle the outline sidebar |
| `y` `Y` | yank the selection / the page text |
| `m` `'` | set / jump to a mark |
| `i` `s` `p` `a` `<Ctrl-l>` | info, save-as, print, attachments, layers |
| `e` `A` `x` `C` `S` | forms, annotate, redact, OCR, sign/verify |
| `:` | command line (with tab-completion) |
| `q` | quit |

Run `:` and type a command, or drive it from the shell:

```bash
omarchy-pdf Vertrag.pdf
omarchy-pdf Vertrag.pdf --command "goto 3; zoom-fit-width; info" --exit
```

## Command line

```
info              document metadata (Info dict, page count, encryption, version)
save-as <path>    linearised, decrypted copy (qpdf)
print             send to the default CUPS printer
attachments       list embedded files (pdfdetach)
layers            list optional-content groups (/OCG)
forms k=v ...     fill AcroForm text fields (k=on for a checkbox) and save
annotate Text 2 72 600 132 660 Note   add an annotation to a page
redact 2 72 600 132 660               rasterise + stamp an opaque box (text removed)
ocr               add a searchable text layer (pdftoppm + tesseract)
sign              verify embedded signatures (pdfsig);  sign --qes -> sign-me
search <text> / goto <page|label> / zoom-set <pct> / rotate-cw ...
```

## The rest of the plugin

| Command | What it does |
|---------|--------------|
| `omarchy-toggle-pdf-night [on\|off\|toggle\|--status]` | Papers' dark/light render toggle (`Super+Ctrl+N`) |
| `omarchy-pdf-sign [pdf]` | open the D-Trust **sign-me** portal to sign with a QES (eIDAS) |
| `omarchy-webapp-qutebrowser --app=<url>` | Chromium-free web-app fallback |

## Install

```bash
git clone https://github.com/Maximilian-Maag/omarchy-pdf
cd omarchy-pdf && ./install.sh
```

The installer puts the binaries on `PATH`, installs the `pdf` package under
`/usr/local/share/omarchy-pdf`, adds the desktop entry, and makes `omarchy-pdf` the
default `application/pdf` handler.

**Requirements:** `python-pyqt6` (system python — the viewer is Qt), `qpdf`,
`poppler` (`pdfinfo`/`pdfsig`/`pdfdetach`/`pdftoppm`/`pdftocairo`/`pdfunite`),
`ghostscript`, `tesseract`, `cups`. Papers is optional.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) — the engine/authoring split, the
view protocol, the keymap rules, and what PDFium covers versus the CLI tools.

## Tests

```bash
bash tools/run_tests.sh          # every kind; SKIP_MUTATION=1 skips the slow pass
```

Policy as code, then unit → regression → integration (offscreen Qt, driving the real
window) → shell → e2e (boots the real app through the launcher and renders pixels) →
mutation (`tools/mutator.py`, floor 0.85 over the pure modules and the shell CLIs).
Every shipped source is either a mutation target or exempted with a stated reason.

## License

MIT — see [LICENSE](LICENSE).
