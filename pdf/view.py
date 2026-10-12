"""The Qt render surface: a QGraphicsView that draws pages with QtPdf (PDFium).

This is the module that owns the *engine*. It implements the view protocol
(docs/architecture.md §4) so the pure command layer can drive it. All of the
interesting interaction logic lives in the pure modules; this file is the glue and
is therefore mutation-`exempt` — it is covered by the offscreen integration/e2e
suites instead (a byte of this file is exercised by loading and driving the app).
"""

from __future__ import annotations

import os
import subprocess

from PyQt6.QtCore import Qt, QSize, QRectF, QPointF, QTimer, QModelIndex, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QGraphicsRectItem, QGraphicsSimpleTextItem, QApplication)
from PyQt6.QtPdf import (QPdfDocument, QPdfSearchModel, QPdfLinkModel,
                         QPdfBookmarkModel, QPdfPageNavigator)

from . import nav, keymap, hints as hints_mod


_CTRL_TOKENS = {
    Qt.Key.Key_D: "<C-d>", Qt.Key.Key_U: "<C-u>", Qt.Key.Key_F: "<C-f>",
    Qt.Key.Key_B: "<C-b>", Qt.Key.Key_O: "<C-o>", Qt.Key.Key_I: "<C-i>",
    Qt.Key.Key_Q: "<C-q>",
}
_PLAIN_TOKENS = {
    Qt.Key.Key_Escape: "<Esc>", Qt.Key.Key_Return: "<CR>", Qt.Key.Key_Enter: "<CR>",
    Qt.Key.Key_Backspace: "<BS>", Qt.Key.Key_Space: "<Space>", Qt.Key.Key_Tab: "<Tab>",
}


def key_token(event) -> str | None:
    """Map a QKeyEvent to a keymap token, or None when it carries no key."""
    key = event.key()
    ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
    if ctrl:
        return _CTRL_TOKENS.get(key)
    if key in _PLAIN_TOKENS:
        return _PLAIN_TOKENS[key]
    text = event.text()
    if text and text.isprintable():
        return text
    return None


class PdfView(QGraphicsView):
    """A continuous, keyboard-driven PDF view over a QPdfDocument."""

    messageRaised = pyqtSignal(str, str)
    modeChanged = pyqtSignal(str)
    pageChanged = pyqtSignal(int, int)      # index, count
    zoomChanged = pyqtSignal(int)
    rotationChanged = pyqtSignal(int)
    pathChanged = pyqtSignal(str)
    outlineChanged = pyqtSignal()
    promptRequested = pyqtSignal(str)
    sidebarToggled = pyqtSignal()

    def __init__(self, parent=None, palette: dict | None = None):
        super().__init__(parent)
        self.km = keymap.default_keymap()
        self.palette_dict = palette or {}
        self._buffer: tuple[str, ...] = ()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._flush_keys)

        self.doc = QPdfDocument(self)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.doc)
        self.link_model = QPdfLinkModel(self)
        self.link_model.setDocument(self.doc)
        self.bookmarks = QPdfBookmarkModel(self)
        self.bookmarks.setDocument(self.doc)
        self.navigator = QPdfPageNavigator(self)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pages: dict[int, QGraphicsPixmapItem] = {}
        self._positions: dict[int, QRectF] = {}
        self._overlay: list = []
        self._hint_labels: list[str] = []
        self._hint_targets: list = []
        self._hint_typed = ""
        self._outline_indexes: list = []
        self._page = 0
        self._zoom = 100
        self._rotation = 0
        self._mode = "normal"
        self._query = ""
        self._search_index = -1
        self._search_pending = False
        self._marks: dict[str, int] = {}
        self._path = ""

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.search_model.countChanged.connect(self._on_search_count)
        self._apply_palette()

    # ── engine ────────────────────────────────────────────────────────────
    def load(self, path, password=None):
        resolved = os.path.expanduser(path)
        if password:
            self.doc.setPassword(password)
        error = self.doc.load(resolved)
        if error != QPdfDocument.Error.None_:
            self.messageRaised.emit(f"cannot open {path}: {error}", "error")
            return
        self._path = resolved
        self._page = 0
        self._rotation = 0
        self._query = ""
        self.search_model.setSearchString("")
        self._rebuild_layout()
        self.navigator.jump(self._page, QPointF(), 1.0)
        self.pathChanged.emit(resolved)
        self.outlineChanged.emit()
        self._emit_page()
        self.messageRaised.emit(f"{os.path.basename(resolved)}: {self.page_count()} pages", "info")

    def page_count(self):
        return self.doc.pageCount()

    def current_page(self):
        return self._page

    def page_label(self, index):
        return self.doc.pageLabel(index)

    def path(self):
        return self._path

    def get_text(self, index):
        return self.doc.getAllText(index).text()

    # ── layout / rendering ────────────────────────────────────────────────
    def _scale(self):
        return self._zoom / 100.0

    def _dims(self, index):
        size = self.doc.pagePointSize(index)
        w, h = float(size.width()), float(size.height())
        if self._rotation % 180:
            w, h = h, w
        return w * self._scale(), h * self._scale()

    def _rebuild_layout(self):
        for item in self._pages.values():
            self._scene.removeItem(item)
        self._pages.clear()
        self._positions = {}
        gap = 12.0
        y = 0.0
        width = 1.0
        for i in range(self.page_count()):
            w, h = self._dims(i)
            self._positions[i] = QRectF(0.0, y, w, h)
            width = max(width, w)
            y += h + gap
        self._scene.setSceneRect(QRectF(0, 0, width, y))
        self._render_visible()

    def _render_visible(self):
        if not self.page_count():
            return
        viewport = self.mapToScene(self.viewport().rect()).boundingRect()
        for index, rect in self._positions.items():
            if not rect.intersects(viewport):
                continue
            if index in self._pages:
                continue
            qimage = self.doc.render(index, QSize(max(1, int(rect.width())),
                                                  max(1, int(rect.height()))))
            if qimage.isNull():
                continue
            item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
            item.setPos(rect.topLeft())
            if self._rotation:
                item.setTransformOriginPoint(rect.width() / 2, rect.height() / 2)
                item.setRotation(self._rotation)
            self._scene.addItem(item)
            self._pages[index] = item

    def _on_scroll(self, _value):
        self._render_visible()
        self._update_current_page()

    def _update_current_page(self):
        center = self.mapToScene(self.viewport().rect().center()).y()
        best, best_dist = self._page, None
        for index, rect in self._positions.items():
            dist = abs(rect.center().y() - center)
            if best_dist is None or dist < best_dist:
                best, best_dist = index, dist
        if best != self._page:
            self._page = best
            self._emit_page()

    def _emit_page(self):
        self.pageChanged.emit(self._page, self.page_count())

    def _center_on(self, index):
        rect = self._positions.get(index)
        if rect is not None:
            self.centerOn(rect.center())
        self._render_visible()

    # ── navigation ────────────────────────────────────────────────────────
    def goto_page(self, index):
        index = nav.clamp_page(index, self.page_count())
        self._page = index
        self._center_on(index)
        self._emit_page()

    def goto_label(self, label):
        for i in range(self.page_count()):
            if self.doc.pageLabel(i) == label:
                self.goto_page(i)
                return
        self.messageRaised.emit(f"no page labelled {label!r}", "error")

    def goto_scroll(self, where):
        rect = self._positions.get(self._page)
        if rect is None:
            return
        frac = {"top": 0.0, "middle": 0.5, "bottom": 1.0}.get(where, 0.0)
        self.centerOn(rect.center().x(), rect.top() + frac * rect.height())
        self._render_visible()

    def scroll(self, dy, dx=0):
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
        if dx:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
        self._render_visible()

    def scroll_pages(self, dy):
        self.scroll(dy * (self.viewport().height() // 2))

    def history_back(self):
        self.navigator.back()
        self._page = int(self.navigator.currentPage())
        self._center_on(self._page)
        self._emit_page()

    def history_forward(self):
        self.navigator.forward()
        self._page = int(self.navigator.currentPage())
        self._center_on(self._page)
        self._emit_page()

    # ── zoom / rotate ─────────────────────────────────────────────────────
    def zoom_percent(self):
        return self._zoom

    def zoom(self, delta_pct=None, set_pct=None, mode=None):
        if set_pct is not None:
            self._zoom = nav.clamp_zoom(set_pct)
        elif mode is not None:
            size = self.doc.pagePointSize(self._page)
            pw, ph = float(size.width()), float(size.height())
            if self._rotation % 180:
                pw, ph = ph, pw
            scale = nav.fit_scale(pw, ph, self.viewport().width(),
                                  self.viewport().height(), mode, margin=16)
            self._zoom = nav.clamp_zoom(int(scale * 100))
        elif delta_pct is not None:
            self._zoom = 100 if delta_pct == 0 else nav.zoom_percent(self._zoom, delta_pct)
        self._rebuild_layout()
        self._center_on(self._page)
        self.zoomChanged.emit(self._zoom)

    def rotation(self):
        return self._rotation

    def rotate(self, delta):
        self._rotation = nav.rotate(self._rotation, delta)
        self._rebuild_layout()
        self._center_on(self._page)
        self.rotationChanged.emit(self._rotation)

    # ── search ────────────────────────────────────────────────────────────
    def search(self, text):
        self._query = text
        self._search_index = -1
        self._search_pending = True
        self.search_model.setSearchString(text)
        # the search runs on a worker; results may already be ready (repeat search)
        if self.search_model.count() > 0:
            self._search_pending = False
            self._goto_hit(1)

    def _on_search_count(self):
        """QtPdf searches asynchronously — navigate once the first result lands."""
        if self._search_pending and self.search_model.count() > 0:
            self._search_pending = False
            self._goto_hit(1)

    def _goto_hit(self, direction):
        total = self.search_model.count()
        if total == 0:
            self.messageRaised.emit(f"no matches for {self._query!r}", "error")
            return
        if self._search_index < 0:
            index = 0 if direction >= 0 else total - 1
        else:
            index = (self._search_index + direction) % total
        self._search_index = index
        link = self.search_model.resultAtIndex(index)
        self.goto_page(int(link.page()))
        self._draw_search_highlight(link)
        self.messageRaised.emit(f"match {index + 1}/{total}", "info")

    def search_next(self):
        self._goto_hit(1)

    def search_prev(self):
        self._goto_hit(-1)

    def search_query(self):
        return self._query

    def clear_search(self):
        self._query = ""
        self.search_model.setSearchString("")
        self._search_index = -1
        self._clear_overlay()
        self._clear_hints()

    def _draw_search_highlight(self, link):
        self._clear_overlay()
        rect = self._positions.get(self._page)
        if rect is None:
            return
        color = QColor(self.palette_dict.get("yellow", "#f9e2af"))
        for hit in link.rectangles():
            box = QRectF(hit).translated(rect.topLeft())
            item = QGraphicsRectItem(box)
            item.setPen(QPen(color, 1))
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
            self._scene.addItem(item)
            self._overlay.append(item)
        self._render_visible()

    # ── hints ─────────────────────────────────────────────────────────────
    def open_hints(self, kind="follow"):
        self._clear_hints()
        if not self.page_count():
            return
        self.link_model.setPage(self._page)
        rect = self._positions.get(self._page)
        if rect is None:
            return
        count = self.link_model.rowCount(QModelIndex())
        targets = []
        for r in range(count):
            index = self.link_model.index(r, 0)
            link = self.link_model.data(index, QPdfLinkModel.Role.Link.value)
            area = self.link_model.data(index, QPdfLinkModel.Role.Rectangle.value)
            if link is None or area is None:
                continue
            targets.append((link, area))
        self._hint_targets = targets
        self._hint_labels = hints_mod.generate_labels(len(targets))
        self._hint_typed = ""
        color = QColor(self.palette_dict.get("accent", "#89b4fa"))
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        for label, (_link, area) in zip(self._hint_labels, targets):
            item = QGraphicsSimpleTextItem(label)
            item.setBrush(QBrush(color))
            item.setFont(font)
            box = QRectF(area).translated(rect.topLeft())
            item.setPos(box.center())
            self._scene.addItem(item)
            self._overlay.append(item)
        self.set_mode("hint")
        self.messageRaised.emit(f"{len(targets)} hints", "info")

    def hint_key(self, key):
        """Handle a character while in hint mode; returns True if consumed."""
        if self._mode != "hint":
            return False
        if key == "<BS>":
            self._hint_typed = self._hint_typed[:-1]
        else:
            self._hint_typed += key
        matches = hints_mod.matching(self._hint_labels, self._hint_typed)
        if len(matches) == 1:
            self.activate_hint(self._hint_labels[matches[0]])
            return True
        if not matches:
            self.messageRaised.emit("no such hint", "error")
            self._clear_hints()
            self.set_mode("normal")
        return True

    def hint_backspace(self):
        self._hint_typed = self._hint_typed[:-1]

    def activate_hint(self, label):
        index = hints_mod.unique_match(self._hint_labels, label)
        if index < 0:
            self.messageRaised.emit("not a hint", "error")
            return
        link, _area = self._hint_targets[index]
        self._clear_hints()
        self.set_mode("normal")
        url = link.url()
        if url.isValid() and url.toString():
            self.open_url(url.toString())
            return
        page = int(link.page())
        if page >= 0:
            self.goto_page(page)

    def _clear_hints(self):
        self._hint_labels = []
        self._hint_targets = []
        self._hint_typed = ""
        if self._mode == "hint":
            self._clear_overlay()

    def _clear_overlay(self):
        for item in self._overlay:
            self._scene.removeItem(item)
        self._overlay = []

    # ── yank / outline / marks ────────────────────────────────────────────
    def yank_selection(self):
        self.yank_page()

    def yank_page(self):
        text = self.get_text(self._page)
        QApplication.clipboard().setText(text)
        self.messageRaised.emit(f"yanked page {self._page + 1} ({len(text)} chars)", "info")

    def outline(self):
        self._outline_indexes = []
        out = []

        def walk(parent, level):
            for row in range(self.bookmarks.rowCount(parent)):
                index = self.bookmarks.index(row, 0, parent)
                title = self.bookmarks.data(index, QPdfBookmarkModel.Role.Title.value)
                page = self.bookmarks.data(index, QPdfBookmarkModel.Role.Page.value)
                self._outline_indexes.append(index)
                out.append((len(out), str(title or ""),
                            int(page) if page is not None else -1, level))
                walk(index, level + 1)

        walk(QModelIndex(), 0)
        return out

    def outline_goto(self, row):
        if not self._outline_indexes:
            self.outline()
        if not 0 <= row < len(self._outline_indexes):
            self.messageRaised.emit("no such outline entry", "error")
            return
        index = self._outline_indexes[row]
        page = self.bookmarks.data(index, QPdfBookmarkModel.Role.Page.value)
        if page is None:
            self.messageRaised.emit("bookmark has no destination", "error")
            return
        self.goto_page(int(page))

    def toggle_sidebar(self):
        self.sidebarToggled.emit()

    def mark_set(self, char):
        self._marks[char] = self._page
        self.messageRaised.emit(f"mark {char} set on page {self._page + 1}", "info")

    def mark_jump(self, char):
        if char in self._marks:
            self.goto_page(self._marks[char])
        else:
            self.messageRaised.emit(f"no mark {char}", "error")

    # ── modes / prompts / messages ────────────────────────────────────────
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        self._mode = mode
        self.modeChanged.emit(mode)

    def start_prompt(self, kind):
        self.promptRequested.emit(kind)

    def prompt_action(self, action):
        pass

    def message(self, text, level="info"):
        self.messageRaised.emit(text, level)

    def open_url(self, url):
        opener = os.environ.get("OMARCHY_PDF_OPENER", "qutebrowser")
        try:
            subprocess.Popen([opener, "--target", "window", url])
        except OSError:
            subprocess.Popen(["xdg-open", url])
        self.messageRaised.emit(f"opened {url}", "info")

    # ── document operations ───────────────────────────────────────────────
    def _emit_doc(self, builder, args):
        text = builder(self.path(), *args) if args else builder(self.path())
        self.messageRaised.emit(text, "info")

    def op_info(self, *args):
        from . import docops
        self._emit_doc(docops.info_text, args)

    def op_save_as(self, *args):
        from . import docops
        self._emit_doc(docops.copy, args)

    def op_print(self, *args):
        from . import docops
        self._emit_doc(docops.print_document, args)

    def op_attachments(self, *args):
        from . import docops
        self._emit_doc(docops.attachments, args)

    def op_layers(self, *args):
        from . import docops
        self._emit_doc(docops.layers, args)

    def op_forms(self, *args):
        from . import writeops
        self._emit_doc(writeops.forms, args)

    def op_annotate(self, *args):
        from . import writeops
        self._emit_doc(writeops.annotate, args)

    def op_sign(self, *args):
        from . import writeops
        self._emit_doc(writeops.sign, args)

    def op_redact(self, *args):
        from . import writeops
        self._emit_doc(writeops.redact, args)

    def op_ocr(self, *args):
        from . import writeops
        self._emit_doc(writeops.ocr, args)

    # ── keyboard ──────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        token = key_token(event)
        if token is None:
            super().keyPressEvent(event)
            return
        if self._mode == "hint" and self.hint_key(token):
            event.accept()
            return
        resolution = self.km.feed(self._mode, token, self._buffer)
        self._buffer = resolution.buffer
        if resolution.state == keymap.PENDING:
            self._timer.start()
            event.accept()
            return
        self._timer.stop()
        command = resolution.command if resolution.state == keymap.FIRED else None
        self._buffer = ()
        if command is not None:
            self.run_command(command)
        event.accept()

    def _flush_keys(self):
        resolution = self.km.flush(self._mode, self._buffer)
        self._buffer = ()
        if resolution.state == keymap.FIRED and resolution.command is not None:
            self.run_command(resolution.command)

    def run_command(self, line):
        from . import commands
        try:
            commands.dispatch(self, line)
        except commands.CommandError as exc:
            self.messageRaised.emit(str(exc), "error")

    def send_keys(self, text: str):
        """Drive the keymap from a string of tokens (used by the CLI and tests)."""
        for token in keymap.parse_sequence(text):
            if self._mode == "hint" and self.hint_key(token):
                continue
            resolution = self.km.feed(self._mode, token, self._buffer)
            self._buffer = resolution.buffer
            if resolution.state != keymap.PENDING:
                self._buffer = ()
                if resolution.state == keymap.FIRED and resolution.command is not None:
                    self.run_command(resolution.command)

    # ── appearance ────────────────────────────────────────────────────────
    def _apply_palette(self):
        bg = self.palette_dict.get("bg_darker", self.palette_dict.get("bg", "#101019"))
        self._scene.setBackgroundBrush(QBrush(QColor(bg)))

    def apply_palette(self, palette: dict):
        self.palette_dict = palette
        self._apply_palette()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_visible()
