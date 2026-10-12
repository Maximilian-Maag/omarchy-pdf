"""qutebrowser-style status bar: page, zoom, rotation, mode and messages."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QStatusBar


class StatusBar(QStatusBar):
    """A one-line status bar showing the document state, plus a transient message."""

    def __init__(self, parent=None, palette: dict | None = None):
        super().__init__(parent)
        self.palette_dict = palette or {}
        self._page = QLabel("–")
        self._zoom = QLabel("100%")
        self._rotation = QLabel("0°")
        self._mode = QLabel("normal")
        self._path = QLabel("no document")
        for widget in (self._path,):
            widget.setMinimumWidth(160)
        self.addWidget(self._path, 1)
        self.addPermanentWidget(self._page)
        self.addPermanentWidget(self._zoom)
        self.addPermanentWidget(self._rotation)
        self.addPermanentWidget(self._mode)
        self._style()

    def _style(self):
        bg = self.palette_dict.get("bg_dark", "#161622")
        fg = self.palette_dict.get("fg", "#cdd6f4")
        dim = self.palette_dict.get("fg_dim", "#6c7086")
        self.setStyleSheet(
            f"QStatusBar {{ background:{bg}; color:{fg}; }}"
            f"QStatusBar QLabel {{ color:{fg}; padding:0 8px; }}"
            f"QStatusBar QLabel#mode {{ color:{dim}; font-weight:bold; }}")

    def set_document(self, path):
        self._path.setText(path or "no document")

    def set_page(self, index, count):
        self._page.setText(f"{index + 1}/{count}")

    def set_zoom(self, percent):
        self._zoom.setText(f"{percent}%")

    def set_rotation(self, degrees):
        self._rotation.setText(f"{degrees}°")

    def set_mode(self, mode):
        self._mode.setText(mode)
        self._mode.setObjectName("mode")
