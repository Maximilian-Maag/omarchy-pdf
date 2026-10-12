"""The ':' / '/' command line with tab-completion — qutebrowser's status prompt."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit

from . import commands


class CommandBar(QLineEdit):
    """A hidden single-line input shown for command, search and open prompts.

    `accept` is emitted with (kind, text) when the user presses Return, `cancel`
    when they press Escape.
    """

    accept = pyqtSignal(str, str)
    cancel = pyqtSignal()

    PREFIX = {"command": ":", "search": "/", "search-prev": "?", "open": ":open ",
              "web-search": ":web-search-prompt ", "mark": ":", "mark-jump": ":"}

    def __init__(self, parent=None, palette: dict | None = None):
        super().__init__(parent)
        self.palette_dict = palette or {}
        self.kind = "command"
        self._history: list[str] = []
        self._history_pos = 0
        self.hide()
        self._style()

    def _style(self):
        bg = self.palette_dict.get("bg_dark", "#161622")
        fg = self.palette_dict.get("fg", "#cdd6f4")
        accent = self.palette_dict.get("accent", "#89b4fa")
        self.setStyleSheet(
            f"QLineEdit {{ background:{bg}; color:{fg}; border:1px solid {accent};"
            f" padding:2px 6px; font-family:monospace; }}")

    def start(self, kind: str, prefill: str = ""):
        self.kind = kind
        prefix = self.PREFIX.get(kind, ":")
        self.setText(prefill or prefix)
        self.setCursorPosition(len(self.text()))
        self.show()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

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
            self.hide()
            self.cancel.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self._payload()
            self._history.append(text)
            self._history_pos = len(self._history)
            self.hide()
            self.accept.emit(self.kind, text)
            return
        if event.key() == Qt.Key.Key_Tab:
            payload = self._payload()
            if self.kind in ("command", "open", "web-search", "mark", "mark-jump"):
                matches = commands.complete(payload)
                if matches:
                    filled = matches[0]
                    self.setText(":" + filled)
            return
        if event.key() == Qt.Key.Key_Up and self._history:
            self._history_pos = max(0, self._history_pos - 1)
            self.setText(":" + self._history[self._history_pos])
            return
        if event.key() == Qt.Key.Key_Down and self._history:
            self._history_pos = min(len(self._history), self._history_pos + 1)
            text = self._history[self._history_pos] if self._history_pos < len(self._history) else ""
            self.setText(":" + text if text else ":")
            return
        super().keyPressEvent(event)
