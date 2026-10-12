"""The application window and entry point.

qutebrowser-shaped: a QMainWindow whose central widget is the engine (here a
:class:`pdf.view.PdfView`), a status bar, an outline dock, and a hidden command
line that appears for `:` / `/` prompts. Key events reach the view, which resolves
them through the pure keymap and dispatches to the command layer.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote_plus

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDockWidget, QTreeWidget,
                             QTreeWidgetItem, QWidget, QVBoxLayout)

from . import theme, view as view_mod, statusbar, commandbar


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None, palette: dict | None = None):
        super().__init__()
        self.palette_dict = palette if palette is not None else theme.load_palette()
        self.setWindowTitle("omarchy-pdf")
        self.resize(1000, 1100)

        self.view = view_mod.PdfView(self, self.palette_dict)
        self.bar = commandbar.CommandBar(self, self.palette_dict)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.bar)
        self.setCentralWidget(container)

        self.status = statusbar.StatusBar(self, self.palette_dict)
        self.setStatusBar(self.status)

        self.outline = QTreeWidget(self)
        self.outline.setHeaderHidden(True)
        self.outline.itemActivated.connect(self._outline_activated)
        self.outline.itemClicked.connect(self._outline_activated)
        self.dock = QDockWidget("Outline", self)
        self.dock.setWidget(self.outline)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.dock.hide()

        self._wire()
        self._refresh()
        if path:
            self.view.load(path)

    # ── wiring ────────────────────────────────────────────────────────────
    def _wire(self):
        v = self.view
        v.messageRaised.connect(self._message)
        v.pageChanged.connect(lambda *_a: self._refresh())
        v.zoomChanged.connect(lambda *_a: self._refresh())
        v.rotationChanged.connect(lambda *_a: self._refresh())
        v.modeChanged.connect(lambda *_a: self._refresh())
        v.pathChanged.connect(self._path_changed)
        v.outlineChanged.connect(self._reload_outline)
        v.promptRequested.connect(self._prompt)
        v.sidebarToggled.connect(self._toggle_sidebar)
        self.bar.accept.connect(self._prompt_accept)
        self.bar.cancel.connect(self._prompt_cancel)

    def _message(self, text, level="info"):
        self.status.showMessage(text.replace("\n", "  "), 5000)

    def _path_changed(self, path):
        self.status.set_document(path)
        self.setWindowTitle(f"{os.path.basename(path)} — omarchy-pdf")

    def _refresh(self):
        self.status.set_page(self.view.current_page(), self.view.page_count())
        self.status.set_zoom(self.view.zoom_percent())
        self.status.set_rotation(self.view.rotation())
        self.status.set_mode(self.view.mode())

    # ── outline ───────────────────────────────────────────────────────────
    def _reload_outline(self):
        self.outline.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for row, title, _page, level in self.view.outline():
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.outline.addTopLevelItem(item)
            stack.append((level, item))

    def _outline_activated(self, item, _column=None):
        row = item.data(0, Qt.ItemDataRole.UserRole)
        if row is not None:
            self.view.outline_goto(int(row))

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self._reload_outline()

    # ── prompts ───────────────────────────────────────────────────────────
    def _prompt(self, kind):
        self.view.set_mode("search" if kind.startswith("search") else "command")
        self.bar.start(kind)

    def _prompt_cancel(self):
        self.view.set_mode("normal")
        self.view.setFocus()
        self._refresh()

    def _prompt_accept(self, kind, text):
        self.view.set_mode("normal")
        self.view.setFocus()
        if kind == "search":
            self.view.search(text)
        elif kind == "search-prev":
            self.view.search(text)
            self.view.search_prev()
        elif kind == "open":
            self.view.run_command(f"open {text}")
        elif kind == "web-search":
            self.view.open_url(f"https://search.brave.com/search?q={quote_plus(text)}")
        elif kind == "mark":
            self.view.run_command(f"mark-set {text}")
        elif kind == "mark-jump":
            self.view.run_command(f"mark-go {text}")
        else:
            self.view.run_command(text)
        self._refresh()


def _split_commands(spec: str) -> list[str]:
    return [part.strip() for part in spec.split(";") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    """Entry point for bin/omarchy-pdf."""
    args = list(sys.argv[1:] if argv is None else argv)

    paths, commands, exit_after = [], [], False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("--command", "-c") and index + 1 < len(args):
            commands.extend(_split_commands(args[index + 1]))
            index += 2
            continue
        if arg == "--exit":
            exit_after = True
            index += 1
            continue
        if arg in ("-h", "--help"):
            print(__doc__)
            return 0
        paths.append(arg)
        index += 1

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("omarchy-pdf")
    palette = theme.load_palette()
    window = MainWindow(path=paths[0] if paths else None, palette=palette)

    if commands:
        for command in commands:
            window.view.run_command(command)
        window._refresh()
    if exit_after:
        return 0

    window.show()
    if paths:
        window.view.setFocus()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
