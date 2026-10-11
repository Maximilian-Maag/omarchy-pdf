# Changelog

All notable changes to omarchy-pdf are documented here.

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
