"""omarchy-pdf — a native, keyboard-driven PDF application for Omarchy.

The package is split so that everything interesting is testable without a display:

  keymap, nav, hints, theme, commands   ->  pure Python, no Qt, mutation targets
  docops, writeops                      ->  document operations over CLI tools
  view, statusbar, commandbar, app      ->  the Qt shell (offscreen-tested, exempt)

`omarchy_pdf.main()` is the single entry point used by bin/omarchy-pdf.
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
