# omarchy-pdf

A better PDF experience for [Omarchy](https://omarchy.org/): a modern viewer with
form filling, a one-key dark/light render toggle, and a straight path to signing
documents with a **qualified electronic signature (QES)**.

Three small pieces, each a normal Omarchy CLI:

| Command | What it does |
|---------|--------------|
| `omarchy-toggle-pdf-night [on\|off\|toggle\|--status]` | Flips Papers' night mode — dark ⇄ light **rendering** of the document |
| `omarchy-webapp-qutebrowser --app=<url>` | Launches a URL as a web app in qutebrowser (the Chromium-free fallback) |
| `omarchy-pdf-sign [pdf-file]` | Opens the D-Trust **sign-me** portal in your default browser to sign a PDF with a QES |

## What it sets up

- **Reading / forms** — [Papers](https://apps.gnome.org/Papers/) becomes the default
  `application/pdf` handler. It is GTK4/libadwaita, so it inherits the active Omarchy
  theme, and it fills AcroForm fields and saves the result.
- **Dark by default** — Papers' `night-mode` GSetting is turned on, so PDFs render
  inverted for night reading. `Super+Ctrl+N` toggles back to light.
- **QES** — a QES certificate lives at a *Vertrauensdiensteanbieter*, never locally,
  so `omarchy-pdf-sign` opens the sign-me portal and reminds you which file to upload.
  Identify once with the Online-Ausweis; sign in the portal thereafter.

## Install

```bash
git clone https://github.com/Maximilian-Maag/omarchy-pdf
cd omarchy-pdf
./install.sh
```

The installer copies the three binaries to `/usr/local/bin`, installs the desktop
entries, points `application/pdf` at Papers, enables night mode, and registers the
keybindings below. It is idempotent — re-running is safe.

Requires `papers` (`omarchy pkg add papers`). `ausweisapp` + `ccid` are needed for
on-device eID identification; a smartphone with the AusweisApp (NFC) works too.

## Keybindings

| Keys | Action |
|------|--------|
| `Super + D` | Open a document (Papers) |
| `Super + Ctrl + N` | Toggle PDF dark/light rendering |
| `Super + Shift + Q` | Open sign-me (QES) |

## Why a web-app shim?

Omarchy's `omarchy-launch-webapp` forces a Chromium-family browser for its `--app=`
windows. With Chromium removed, `omarchy-webapp-qutebrowser` is installed as the
`Exec` of a user-level `chromium.desktop`, so that path opens in qutebrowser instead
and every built-in web-app shortcut keeps working.

## Tests

```bash
bash tools/run_tests.sh        # every kind; SKIP_MUTATION=1 skips the slow pass
```

Unit, regression, integration, shell and e2e suites plus a mutation pass
(`tools/mutator.py`) with a kill-rate floor of 0.85, and policy-as-code enforcement
(`tools/policy_check.py`) in the pre-commit hook and CI. Survivors that cannot change
behaviour are proven equivalent by diffing the full test output and recorded with a
reason in `tests/mutation.json`.

## License

MIT — see [LICENSE](LICENSE).
