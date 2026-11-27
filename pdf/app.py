"""The application window and entry point.

qutebrowser-shaped: a QMainWindow whose central widget is the engine (here a
:class:`pdf.view.PdfView`), a status bar, an outline dock, and a hidden command
line that appears for `:` / `/` prompts. Key events reach the view, which resolves
them through the pure keymap and dispatches to the command layer.
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import quote_plus

from PyQt6.QtCore import QEvent, QProcess, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDockWidget, QTreeWidget,
                             QTreeWidgetItem, QWidget, QVBoxLayout)

from . import night as night_mod, theme, view as view_mod, statusbar, commandbar


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
        self.outline.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.outline.installEventFilter(self)
        self._outline_flat: list[QTreeWidgetItem] = []
        self.outline.itemActivated.connect(self._outline_activated)
        self.outline.itemClicked.connect(self._outline_activated)
        self.dock = QDockWidget("Outline", self)
        self.dock.setWidget(self.outline)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.dock.hide()

        self._wire()
        self._refresh()
        self._night_process = None
        # Tests drive the window offscreen and must not spawn gsettings children.
        if os.environ.get("OMARCHY_PDF_GSETTINGS", "1") != "0":
            effect = self._night_from_gsettings()
            if effect:
                self.view.set_night(effect, announce=False)
            self._watch_night()
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
        # An error is the only feedback for "that key did nothing" (e.g. `f` on a page
        # with no links and no outline), so it has to stay on screen longer than a
        # confirmation — five seconds is not enough to read one at magnification.
        self.status.showMessage(text.replace("\n", "  "), 10000 if level == "error" else 5000)

    # ── night mode ────────────────────────────────────────────────────────
    def _night_from_gsettings(self):
        """Read the shared night-mode key: Papers and this viewer follow one switch.

        `omarchy-toggle-pdf-night` writes `org.gnome.Papers night-mode` for
        `Super+Ctrl+N`. Reading the same key is what makes that key do something in the
        viewer the PDFs actually open in; with no gsettings on the host this stays off.
        """
        try:
            out = subprocess.run(["gsettings", "get", "org.gnome.Papers", "night-mode"],
                                 capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return night_mod.effect_from_gsettings_get(out.stdout)

    def _watch_night(self):
        """Follow the key live, so Super+Ctrl+N recolours an open window."""
        self._night_process = QProcess(self)
        self._night_process.setProgram("gsettings")
        self._night_process.setArguments(["monitor", "org.gnome.Papers", "night-mode"])
        self._night_process.readyReadStandardOutput.connect(self._night_output)
        self._night_process.start()

    def _night_output(self):
        if self._night_process is None:
            return
        chunk = bytes(self._night_process.readAllStandardOutput()).decode("utf-8", "replace")
        for line in chunk.splitlines():
            effect = night_mod.effect_from_gsettings_monitor(line)
            if effect is not None and effect != self.view.night_effect():
                self.view.set_night(effect)

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
        self._outline_flat = []
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for row, title, page, level in self.view.outline():
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, page)
            self._outline_flat.append(item)
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
            # Back to the page: with the focus still in the tree the reader's next
            # `j` would type-search the outline instead of scrolling the chapter.
            self.view.setFocus()

    def _toggle_sidebar(self):
        """Reveal the outline, put the keyboard in it, or hide it.

        `t` used to flip visibility and leave the focus in the view, so the tree was
        mouse-only. Now a visible-but-unfocused outline is re-entered rather than
        hidden, and Escape (see `eventFilter`) is the way out.
        """
        if not self.dock.isVisible():
            self.dock.show()
            self._reload_outline()
            self._focus_outline()
        elif not self.outline.hasFocus():
            self._focus_outline()
        else:
            self.dock.hide()
            self.view.setFocus()

    def _focus_outline(self):
        """Put the keyboard in the outline, on the entry for the page being read.

        Revealing the dock and leaving the focus in the view made the outline
        mouse-only: arrow keys went to the page and `itemActivated` was unreachable.
        """
        self._select_outline_page(self.view.current_page())
        self.outline.setFocus()

    def _select_outline_page(self, page):
        """Select the last entry whose page is at or before `page`, like a bookmark list."""
        best = None
        for item in self._outline_flat:
            target = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if target is None:
                continue
            if int(target) <= page:
                best = item
            else:
                break
        if best is not None:
            self.outline.setCurrentItem(best)
            self.outline.scrollToItem(best)

    def eventFilter(self, obj, event):
        """Keys typed while the outline has focus belong to the document.

        Escape leaves the outline; without it the keyboard has no way back. Everything
        printable goes back to the view as well, because a reader who opened the sidebar
        and then pressed `f` (or `T`, or `:`) had every one of those keys eaten by the
        tree's own type-search — which looks exactly like a broken keybinding.
        """
        if obj is self.outline and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.dock.hide()
                self.view.setFocus()
                return True
            text = event.text()
            if (text and text.isprintable() and len(text) == 1
                    and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                  | Qt.KeyboardModifier.AltModifier
                                                  | Qt.KeyboardModifier.MetaModifier))):
                self.view.setFocus()
                self.view.keyPressEvent(event)
                return True
        return super().eventFilter(obj, event)

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
