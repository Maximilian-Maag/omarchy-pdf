"""The ':' / '/' command line with tab-completion — qutebrowser's status prompt."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem

from . import commands


class CommandBar(QLineEdit):
    """A hidden single-line input shown for command, search and open prompts.

    `accept` is emitted with (kind, text) when the user presses Return, `cancel`
    when they press Escape.

    Typing offers suggestions underneath, the way qutebrowser's prompt does: a reader who
    does not remember whether the command is `places` or `outline` reads the list instead
    of guessing and being told "unknown command".
    """

    accept = pyqtSignal(str, str)
    cancel = pyqtSignal()

    PREFIX = {"command": ":", "search": "/", "search-prev": "?", "open": ":open ",
              "web-search": ":web-search-prompt ", "mark": ":", "mark-jump": ":"}
    COMPLETABLE = ("command", "open", "web-search", "mark", "mark-jump")

    def __init__(self, parent=None, palette: dict | None = None):
        super().__init__(parent)
        self.palette_dict = palette or {}
        self.kind = "command"
        self._history: list[str] = []
        self._history_pos = 0
        self._popup: QListWidget | None = None
        self.hide()
        self._style()
        self.textChanged.connect(self._refresh_popup)

    def _style(self):
        bg = self.palette_dict.get("bg_dark", "#161622")
        fg = self.palette_dict.get("fg", "#cdd6f4")
        accent = self.palette_dict.get("accent", "#89b4fa")
        self.setStyleSheet(
            f"QLineEdit {{ background:{bg}; color:{fg}; border:1px solid {accent};"
            f" padding:2px 6px; font-family:monospace; }}")

    # ── suggestions ───────────────────────────────────────────────────────
    def _popup_widget(self) -> QListWidget:
        if self._popup is None:
            popup = QListWidget(self.parent())
            popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            popup.setUniformItemSizes(True)
            popup.setStyleSheet(
                "QListWidget { background:%s; color:%s; border:1px solid %s; }"
                "QListWidget::item:selected { background:%s; color:%s; }"
                % (self.palette_dict.get("bg_dark", "#161622"),
                   self.palette_dict.get("fg", "#ffd700"),
                   self.palette_dict.get("accent", "#89b4fa"),
                   self.palette_dict.get("selection", "#45475a"),
                   self.palette_dict.get("fg_light", "#bac2de")))
            self._popup = popup
        return self._popup

    def _refresh_popup(self):
        if not self.isVisible() or self.kind not in self.COMPLETABLE:
            self._hide_popup()
            return
        matches = commands.suggest(self._payload())
        if not matches:
            self._hide_popup()
            return
        popup = self._popup_widget()
        popup.clear()
        for name, help_text in matches:
            item = QListWidgetItem(f"{name}   {help_text}".rstrip())
            item.setData(Qt.ItemDataRole.UserRole, name)
            popup.addItem(item)
        popup.setCurrentRow(0)
        row_height = max(18, self.fontMetrics().height() + 6)
        popup.setGeometry(self._popup_rect(len(matches), row_height))
        popup.show()
        popup.raise_()

    def _popup_rect(self, rows: int, row_height: int):
        from PyQt6.QtCore import QRect
        host = self.parentWidget()
        area = host.rect() if host is not None else self.rect()
        origin = self.mapTo(host, QPoint(0, self.height())) if host is not None else QPoint(0, 0)
        width = max(self.width(), 420)
        width = min(width, max(200, area.width() - origin.x() - 8))
        height = min(rows * row_height + 4, 260)
        return QRect(origin.x(), origin.y(), width, height)

    def _hide_popup(self):
        if self._popup is not None:
            self._popup.hide()

    def _selected_name(self) -> str | None:
        if self._popup is None or not self._popup.isVisible():
            return None
        item = self._popup.currentItem()
        if item is None:
            return None
        name = item.data(Qt.ItemDataRole.UserRole)
        return str(name) if name else None

    def _move_selection(self, step: int):
        """Move the highlight, leave the text alone.

        Rewriting the line as the highlight moves would re-filter the list under the
        reader's fingers, so one Down press would collapse twelve suggestions to one.
        """
        popup = self._popup
        if popup is None or not popup.isVisible() or popup.count() == 0:
            return False
        row = (popup.currentRow() + step) % popup.count()
        popup.setCurrentRow(row)
        return True

    def _prefix_for_kind(self) -> str:
        return self.PREFIX.get(self.kind, ":")

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self, kind: str, prefill: str = ""):
        self.kind = kind
        prefix = self.PREFIX.get(kind, ":")
        self.setText(prefill or prefix)
        self.setCursorPosition(len(self.text()))
        self.show()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._refresh_popup()

    def _finish(self):
        self._hide_popup()
        self.hide()

    def _payload(self) -> str:
        text = self.text()
        for prefix in (":open ", ":web-search-prompt "):
            if text.startswith(prefix):
                return text[len(prefix):]
        if text[:1] in (":", "/", "?"):
            return text[1:]
        return text

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish()
            self.cancel.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            name = self._selected_name()
            payload = name if name is not None and " " not in self._payload() else self._payload()
            self._history.append(payload)
            self._history_pos = len(self._history)
            self._finish()
            self.accept.emit(self.kind, payload)
            return
        if event.key() == Qt.Key.Key_Tab:
            name = self._selected_name()
            if name is not None:
                self.setText(self._prefix_for_kind() + name)
                self.setCursorPosition(len(self.text()))
                return
            payload = self._payload()
            if self.kind in self.COMPLETABLE:
                matches = commands.complete(payload)
                if matches:
                    self.setText(self._prefix_for_kind() + matches[0])
            return
        if event.key() == Qt.Key.Key_Up:
            if self._move_selection(-1):
                return
            if self._history:
                self._history_pos = max(0, self._history_pos - 1)
                self.setText(":" + self._history[self._history_pos])
            return
        if event.key() == Qt.Key.Key_Down:
            if self._move_selection(1):
                return
            if self._history:
                self._history_pos = min(len(self._history), self._history_pos + 1)
                text = (self._history[self._history_pos]
                        if self._history_pos < len(self._history) else "")
                self.setText(":" + text if text else ":")
            return
        super().keyPressEvent(event)
