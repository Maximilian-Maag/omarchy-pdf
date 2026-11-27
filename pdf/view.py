"""The Qt render surface: a QGraphicsView that draws pages with QtPdf (PDFium).

This is the module that owns the *engine*. It implements the view protocol
(docs/architecture.md §4) so the pure command layer can drive it. All of the
interesting interaction logic lives in the pure modules; this file is the glue and
is therefore mutation-`exempt` — it is covered by the offscreen integration/e2e
suites instead (a byte of this file is exercised by loading and driving the app).
"""

from __future__ import annotations

import math
import os
import subprocess

from PyQt6.QtCore import Qt, QSize, QRectF, QPointF, QTimer, QModelIndex, pyqtSignal
from PyQt6.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont, QPolygonF)
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QGraphicsRectItem, QGraphicsSimpleTextItem, QApplication)
from PyQt6.QtPdf import (QPdfDocument, QPdfSearchModel, QPdfLinkModel,
                         QPdfBookmarkModel, QPdfPageNavigator)

from . import nav, keymap, hints as hints_mod, night as night_mod


_CTRL_TOKENS = {
    Qt.Key.Key_D: "<C-d>", Qt.Key.Key_U: "<C-u>", Qt.Key.Key_F: "<C-f>",
    Qt.Key.Key_B: "<C-b>", Qt.Key.Key_O: "<C-o>", Qt.Key.Key_I: "<C-i>",
    Qt.Key.Key_Q: "<C-q>", Qt.Key.Key_N: "<C-n>",
}
_PLAIN_TOKENS = {
    Qt.Key.Key_Escape: "<Esc>", Qt.Key.Key_Return: "<CR>", Qt.Key.Key_Enter: "<CR>",
    Qt.Key.Key_Backspace: "<BS>", Qt.Key.Key_Space: "<Space>", Qt.Key.Key_Tab: "<Tab>",
}

# Overlay chrome (hint plates, search highlights) is added to the same scene as the page
# pixmaps, which sit at z 0. Without a z of its own an overlay is painted UNDER every
# page inserted after it — a zoom or rotate removes and re-adds the pages, so a hint set
# opened before it stayed "live" but invisible.
OVERLAY_Z = 1.0
# QGraphicsItem data key naming what an overlay item is ("hint-label", "hint-plate",
# "search-hit"): tests and any future chrome can tell them apart without importing a
# concrete Qt class.
OVERLAY_KIND = 0


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
    nightChanged = pyqtSignal(str)
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
        # Links are activated by a plain click, which means the view has to see the
        # hover too — otherwise the pointer never changes over a link and a reader with
        # no pointer feedback has no way to tell a link from body text.
        self.setMouseTracking(True)

        self._pages: dict[int, QGraphicsPixmapItem] = {}
        self._positions: dict[int, QRectF] = {}
        self._overlay: list = []
        self._hint_labels: list[str] = []
        self._hint_targets: list = []
        self._hint_kind = "follow"
        self._hint_typed = ""
        self._legend = None
        self._outline_indexes: list = []
        self._page = 0
        self._zoom = 100
        self._rotation = 0
        self._night = "off"
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
            item = QGraphicsPixmapItem(self._page_pixmap(qimage))
            item.setPos(rect.topLeft())
            if self._rotation:
                item.setTransformOriginPoint(rect.width() / 2, rect.height() / 2)
                item.setRotation(self._rotation)
            self._scene.addItem(item)
            self._pages[index] = item

    def _page_pixmap(self, image):
        """Composite a QtPdf page render onto opaque paper, then apply the night effect.

        QtPdf (PDFium) returns a page with a TRANSPARENT background: a PDF usually does
        not paint the white sheet, it only draws content over it. Shown as-is, that
        transparent area reveals the scene background, which is the dark theme colour -
        so a page of black text ends up black-on-black and is unreadable. Fill the sheet
        first, the way every other PDF viewer does. The colour is the palette's `paper`
        (white unless a theme overrides it).

        The night effect runs last, on the composited sheet: inverting the raw PDFium
        image would leave the paper transparent and the text floating on the theme
        background, which is exactly the unreadable case above. The grey -> colour table
        comes from :mod:`pdf.night`, so the arithmetic is unit-tested away from Qt.
        """
        paper = QImage(image.size(), QImage.Format.Format_RGB32)
        paper.fill(QColor(self.palette_dict.get("paper", "#ffffff")))
        painter = QPainter(paper)
        painter.drawImage(0, 0, image)
        painter.end()
        table = night_mod.luminance_map(self._night, self.palette_dict.get("fg", "#ffd700"))
        if table is not None:
            paper = self._apply_luminance_table(paper, table)
        return QPixmap.fromImage(paper)

    @staticmethod
    def _apply_luminance_table(image, table):
        """Map every pixel of `image` through a 256-entry grey -> colour table.

        `Format_Grayscale8` pixels *are* their grey value, so converting that format to
        `Indexed8` keeps the value as the palette index and swapping the palette applies
        the table — one lookup per pixel inside Qt rather than a Python loop over a
        million of them, which would stall the view on every page render.
        """
        grey = image.convertToFormat(QImage.Format.Format_Grayscale8)
        indexed = grey.convertToFormat(QImage.Format.Format_Indexed8)
        indexed.setColorTable([QColor(r, g, b).rgb() for (r, g, b) in table])
        return indexed.convertToFormat(QImage.Format.Format_RGB32)

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

    def _center_on(self, index, point=None):
        """Show `index`, with `point` (PDF points, origin top-left) near the top.

        Centring the page is only right when there is no destination point: a page
        taller than the window then shows its middle, and a heading 50 points below
        the page top ends up *above* the visible area — which is what made a bookmark
        jump look like "it went to the page but not to the mark".
        """
        rect = self._positions.get(index)
        if rect is not None:
            target = self._point_scene(index, point) if point is not None else None
            if target is not None:
                margin = min(60.0, self.viewport().height() * 0.12)
                self.centerOn(target.x(),
                              target.y() + self.viewport().height() / 2.0 - margin)
            else:
                self.centerOn(rect.center())
        self._render_visible()

    # ── navigation ────────────────────────────────────────────────────────
    def goto_page(self, index, point=None):
        """Go to `index`; with `point`, land on that spot (PDF points, top-left origin)."""
        index = nav.clamp_page(index, self.page_count())
        self._page = index
        self._center_on(index, point)
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

    # ── night / page colour ───────────────────────────────────────────────
    def night_effect(self):
        return self._night

    def set_night(self, effect, announce=True):
        """Switch the page colour effect and re-render what is on screen.

        Re-rendering has to happen here rather than at the next scroll: the whole point
        is that the reader presses the key and the page in front of them changes. Dropping
        the cached pixmaps keeps the scroll position, because the layout is untouched.
        """
        wanted = night_mod.normalize(effect, default=self._night)
        if wanted == self._night:
            return
        self._night = wanted
        for item in self._pages.values():
            self._scene.removeItem(item)
        self._pages.clear()
        self._render_visible()
        self.nightChanged.emit(self._night)
        if announce:
            self.messageRaised.emit(f"page colour: {self._night}", "info")

    def toggle_night(self):
        self.set_night(night_mod.cycle(self._night))

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
            item.setZValue(OVERLAY_Z)
            item.setData(OVERLAY_KIND, "search-hit")
            self._scene.addItem(item)
            self._overlay.append(item)
        self._render_visible()

    # ── links ─────────────────────────────────────────────────────────────
    def _point_scale(self, index):
        """Scene units per PDF point on a page: the zoom, and nothing else.

        QtPdf reports link rectangles in points whatever the view does, so every use of
        one has to scale it — that is the whole bug class fixed here (`open_hints` used
        to translate the raw points by the page origin, which is only correct at 100 %).
        On a rotated page the visible width belongs to the page's *height*, because the
        layout swaps the dimensions for 90°/270°.
        """
        rect = self._positions.get(index)
        size = self.doc.pagePointSize(index)
        if rect is None:
            return 1.0
        span = float(size.height()) if self._rotation % 180 else float(size.width())
        return rect.width() / span if span else 1.0

    def _rotate_point(self, point, centre):
        """Rotate a scene point about `centre` by the view rotation."""
        angle = math.radians(self._rotation)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        dx, dy = point.x() - centre.x(), point.y() - centre.y()
        return QPointF(centre.x() + dx * cos_a - dy * sin_a,
                       centre.y() + dx * sin_a + dy * cos_a)

    def _rotate_box(self, box, centre):
        """Rotate a scene rectangle about `centre` by the view rotation, as a bounding box."""
        corners = [self._rotate_point(point, centre) for point in
                   (box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft())]
        return QPolygonF(corners).boundingRect()

    def _point_scene(self, index, point):
        """Map a destination point (PDF points, origin top-left) onto the scene.

        Same two corrections as :meth:`_link_scene_rect` — the point scale, and the
        rotation about the page centre — because a destination is only a degenerate
        rectangle. Without them a bookmark lands correctly at 100 % / 0° and drifts
        off the mark everywhere else.
        """
        rect = self._positions.get(index)
        if rect is None or point is None:
            return None
        if not (math.isfinite(point.x()) and math.isfinite(point.y())):
            return None
        scale = self._point_scale(index)
        size = self.doc.pagePointSize(index)
        left = rect.center().x() - float(size.width()) * scale / 2.0
        top = rect.center().y() - float(size.height()) * scale / 2.0
        scene = QPointF(left + float(point.x()) * scale, top + float(point.y()) * scale)
        if not self._rotation % 360:
            return scene
        return self._rotate_point(scene, rect.center())

    def _link_scene_rect(self, index, area):
        """Map a link area (PDF points, origin top-left) onto the scene."""
        rect = self._positions.get(index)
        if rect is None:
            return None
        scale = self._point_scale(index)
        size = self.doc.pagePointSize(index)
        # Build the box on an unrotated page centred on the laid-out rectangle: at 90°/
        # 270° the layout's dimensions are the swapped ones, so the page's own centre is
        # the only origin both orientations agree on.
        left = rect.center().x() - float(size.width()) * scale / 2.0
        top = rect.center().y() - float(size.height()) * scale / 2.0
        box = QRectF(left + area.x() * scale, top + area.y() * scale,
                     area.width() * scale, area.height() * scale)
        if not self._rotation % 360:
            return box
        return self._rotate_box(box, rect.center())

    @staticmethod
    def _link_url(link):
        """The link's external URL, or "" when it is an internal destination."""
        url = link.url()
        return url.toString() if url.isValid() and url.toString() else ""

    def _link_entries(self, index, kind="follow"):
        """(link, scene rect) for the links on a page, in the order QtPdf lists them.

        `kind` is `follow` for `f` (every link: internal jumps and external URIs) and
        `open` for `F`, which means "hand it to the browser" and therefore has nothing
        to offer on an internal destination.
        """
        self.link_model.setPage(index)
        entries = []
        for row in range(self.link_model.rowCount(QModelIndex())):
            model_index = self.link_model.index(row, 0)
            link = self.link_model.data(model_index, QPdfLinkModel.Role.Link.value)
            area = self.link_model.data(model_index, QPdfLinkModel.Role.Rectangle.value)
            if link is None or area is None:
                continue
            if kind == "open" and not self._link_url(link):
                continue
            box = self._link_scene_rect(index, area)
            if box is None:
                continue
            entries.append((link, box))
        return entries

    def _activate_link(self, link, kind="follow"):
        """Activate a link the way the reader asked for: browser, else jump."""
        url = self._link_url(link)
        if url:
            self.open_url(url)
            return
        page = int(link.page())
        if page >= 0:
            self.goto_page(page, link.location())

    def _link_at(self, pos):
        """The link annotation under a scene point, or None."""
        for index, rect in self._positions.items():
            if not rect.contains(pos):
                continue
            for link, box in self._link_entries(index):
                if box.contains(pos):
                    return link
            return None
        return None

    # ── hints ─────────────────────────────────────────────────────────────
    def _viewport_rect(self):
        """The visible part of the scene, or None before the widget has a layout.

        A view that has been resized but never shown still reports a degenerate
        viewport; treating that as "nothing is visible" would hide every hint.
        """
        rect = self.viewport().rect()
        if rect.width() < 1 or rect.height() < 1:
            return None
        return self.mapToScene(rect).boundingRect()

    def _visible_pages(self, viewport):
        """Pages intersecting the viewport, the current sheet first.

        Hints used to be collected from `self._page` alone, so on a fit-page spread (or
        a document whose links sit on the neighbouring sheet) `f` reported nothing while
        the links were plainly on screen. `_update_current_page` picks the page nearest
        the viewport centre, which is not the same as "what is visible".
        """
        area = viewport if viewport is not None else self._scene.sceneRect()
        pages = [i for i, rect in self._positions.items()
                 if rect is not None and rect.intersects(area)]
        pages.sort(key=lambda i: (i != self._page, i))
        return pages

    def _hint_scale(self):
        """Scene units per PDF point — the hint chrome has to follow the zoom.

        A fixed 11 pt label is a few pixels next to page text at 300 %, which is the
        zoom a magnified reading session uses; that read as "the hints never appear".
        """
        return max(self._scale(), 1.0)

    def _hint_font(self):
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(12, int(round(11 * self._hint_scale()))))
        return font

    def _outline_targets(self):
        """(row, title, destination page) for every outline entry, in document order.

        These are the fallback for `f` on a page with no link annotations: the entries a
        reader actually wants to reach — a chapter, the bibliography — are in the outline,
        not painted on the sheet in front of them. Without this, `f` on a prose page said
        "no links in view" and hint mode was dead exactly where the reader stood.
        """
        targets = []
        for row, title, page, _level in self.outline():
            if page is not None and page >= 0:
                targets.append((row, str(title or ""), int(page)))
        return targets

    def _link_destination(self, link):
        """A short, speakable destination for a hint: a URL or "S. <page>"."""
        url = self._link_url(link)
        if url:
            text = url.replace("https://", "").replace("http://", "").rstrip("/")
            return text if len(text) <= 32 else text[:31] + "\u2026"
        page = int(link.page())
        return f"S.{page + 1}" if page >= 0 else "?"

    def open_hints(self, kind="follow"):
        self._clear_hints()
        if not self.page_count():
            self.messageRaised.emit("no document loaded", "error")
            return
        self._hint_kind = kind
        viewport = self._viewport_rect()
        targets = []
        for index in self._visible_pages(viewport):
            for link, box in self._link_entries(index, kind):
                # A label has to land where the reader can see it: a page can be taller
                # than the window, and hinting a box below the fold puts the label off
                # screen while inflating the "N hints" count.
                if box is None or (viewport is not None and not box.intersects(viewport)):
                    continue
                targets.append(("link", link, box, self._link_destination(link)))
        if not targets and kind == "follow":
            # No annotations on screen: offer the document's own structure. These have no
            # box to paint a label on, so the status line carries the whole set — which is
            # also what a magnified reader can actually read.
            for row, title, page in self._outline_targets():
                targets.append(("outline", row, None, f"S.{page + 1} {title}"[:28]))
        if not targets:
            # Entering hint mode with nothing to point at leaves a mode that eats the
            # next keystroke ("no such hint") and shows an empty page: say why instead.
            self.messageRaised.emit(
                "no external links in view" if kind == "open"
                else "no links or outline in this document", "error")
            return
        self._hint_targets = targets
        self._hint_labels = hints_mod.generate_labels(len(targets))
        self._hint_typed = ""
        accent = QColor(self.palette_dict.get("accent", "#89b4fa"))
        ink = QColor(self.palette_dict.get("bg_darker", "#101019"))
        font = self._hint_font()
        margin = max(2.0, font.pixelSize() * 0.25)
        for label, (_kind, _payload, box, _dest) in zip(self._hint_labels, targets):
            if box is None:
                continue
            text = QGraphicsSimpleTextItem(label)
            text.setBrush(QBrush(ink))
            text.setFont(font)
            pad = text.boundingRect()
            # Centre the label on the link and back it with an accent plate: a bare
            # letter in the theme colour disappears over a coloured page area.
            plate = QGraphicsRectItem(QRectF(0, 0, pad.width() + 2 * margin,
                                            pad.height() + 2 * margin))
            plate.setPen(QPen(accent, 0))
            plate.setBrush(QBrush(accent))
            plate_w, plate_h = pad.width() + 2 * margin, pad.height() + 2 * margin
            origin = QPointF(box.center().x() - plate_w / 2,
                             box.center().y() - plate_h / 2)
            # A link on the edge of the viewport would put half its plate outside it.
            if viewport is not None and plate_w <= viewport.width() and plate_h <= viewport.height():
                origin = QPointF(
                    min(max(origin.x(), viewport.left()), viewport.right() - plate_w),
                    min(max(origin.y(), viewport.top()), viewport.bottom() - plate_h))
            plate.setPos(origin)
            text.setPos(origin + QPointF(margin - pad.x(), margin - pad.y()))
            plate.setData(OVERLAY_KIND, "hint-plate")
            text.setData(OVERLAY_KIND, "hint-label")
            for item in (plate, text):
                item.setZValue(OVERLAY_Z)
                self._scene.addItem(item)
                self._overlay.append(item)
        self.set_mode("hint")
        # Labels painted on the page are useless on their own: a hint may have no box at
        # all (outline entries), the boxes can sit outside the visible part of a big page,
        # and a magnified reader cannot survey a whole sheet. The panel names every hint,
        # in window coordinates, so it is readable whatever the zoom and wherever the page
        # has scrolled to.
        self._show_legend([f"{label}  {target[3]}"
                           for label, target in zip(self._hint_labels, targets)][:14],
                          self.font().pixelSize())
        self.messageRaised.emit(
            hints_mod.describe(self._hint_labels, [t[3] for t in targets]), "info")

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
        kind, payload, _box, _dest = self._hint_targets[index]
        self._clear_hints()
        self.set_mode("normal")
        if kind == "outline":
            self.outline_goto(int(payload))
        else:
            self._activate_link(payload, self._hint_kind)

    def _clear_hints(self):
        self._hint_labels = []
        self._hint_targets = []
        self._hint_typed = ""
        self._hide_legend()
        if self._mode == "hint":
            self._clear_overlay()

    # ── hint legend ───────────────────────────────────────────────────────
    def _legend_label(self):
        """The legend is a child widget, i.e. it lives in window coordinates.

        A hint that has no box on the page — an outline entry, which is every hint on a
        prose page — has nowhere in the scene to put its label, and a scene item would
        also scroll away under the reader. As a viewport child it stays where it was
        put, keeps its own readable type size whatever the page zoom, and is text, which
        is the only form this reader can survey.
        """
        if self._legend is None:
            from PyQt6.QtWidgets import QLabel
            self._legend = QLabel(self.viewport())
            self._legend.setWordWrap(False)
            self._legend.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            # Hint mode is driven from the keyboard; the pointer must keep reaching the
            # page (and the link under it) through the panel.
            self._legend.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._legend.setStyleSheet(
                "QLabel { background:%s; color:%s; border:1px solid %s; padding:4px 8px; }"
                % (self.palette_dict.get("bg_dark", "#161622"),
                   self.palette_dict.get("fg", "#ffd700"),
                   self.palette_dict.get("accent", "#89b4fa")))
        return self._legend

    def _show_legend(self, lines, font_px):
        label = self._legend_label()
        label.setFont(self._legend_font(font_px))
        label.setText("\n".join(lines))
        label.adjustSize()
        label.move(8, 8)
        label.show()
        label.raise_()

    def _legend_font(self, pixel_size):
        font = QFont()
        font.setBold(False)
        size = int(pixel_size)
        if size <= 0:
            # QFont.pixelSize() is -1 when the widget font is defined in points, which
            # is the normal case on a desktop with a scaled font: measure it instead of
            # falling back to a 12 px panel this reader could not read.
            size = max(12, int(self.fontMetrics().height() * 1.1))
        font.setPixelSize(max(12, size))
        return font

    def _hide_legend(self):
        if self._legend is not None:
            self._legend.hide()

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

    def outline_destination(self, row):
        """(page, location) for outline entry `row`; location is None when unset.

        QtPdf pages and locations are both 0-based / top-left, so a caller can hand
        them straight to :meth:`goto_page` — jumping to the page alone loses the
        heading when the page is taller than the window.
        """
        if not self._outline_indexes:
            self.outline()
        if not 0 <= row < len(self._outline_indexes):
            return (-1, None)
        index = self._outline_indexes[row]
        page = self.bookmarks.data(index, QPdfBookmarkModel.Role.Page.value)
        location = self.bookmarks.data(index, QPdfBookmarkModel.Role.Location.value)
        return (int(page) if page is not None else -1, location)

    def outline_goto(self, row):
        if not self._outline_indexes:
            self.outline()
        if not 0 <= row < len(self._outline_indexes):
            self.messageRaised.emit("no such outline entry", "error")
            return
        page, location = self.outline_destination(row)
        if page < 0:
            self.messageRaised.emit("bookmark has no destination", "error")
            return
        self.goto_page(page, location)

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

    def quit(self):
        """Close the window this view is shown in.

        `quit` is a command-layer verb (`q`, `:quit`), not a QWidget one, so the view has
        to provide it: without it commands.h_quit raised AttributeError from inside
        keyPressEvent, which PyQt6 escalates to qFatal() — pressing q aborted the process
        instead of closing it.
        """
        self.window().close()

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

    # ── mouse ─────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        """A plain left click on a link annotation activates it.

        Every other PDF reader does this, and the viewer's keyboard hints are no
        replacement for it: a click that does nothing reads as a broken link. Hint mode
        keeps the click for itself so a label can still be typed.
        """
        if event.button() == Qt.MouseButton.LeftButton and self._mode == "normal":
            link = self._link_at(self.mapToScene(event.position().toPoint()))
            if link is not None:
                self._activate_link(link)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        over_link = self._link_at(self.mapToScene(event.position().toPoint())) is not None
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over_link
                                  else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

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
