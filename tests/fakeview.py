"""A recording stand-in for the view protocol (docs/architecture.md §4).

The command layer is pure, so tests drive it against this object instead of a real
window. Every method records its arguments in ``calls`` (a list of tuples), which
makes both the *effect* and the *absence* of an effect observable.
"""
from __future__ import annotations


class FakeView:
    def __init__(self, pages: int = 10, page: int = 0):
        self.pages = pages
        self.page = page
        self.calls: list[tuple] = []
        self.messages: list[tuple[str, str]] = []
        self.opened: list[str] = []
        self.urls: list[str] = []
        self.mode = "normal"
        self.query = ""

    # -- recording helper --
    def _rec(self, name, *args):
        self.calls.append((name, *args))

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    # -- protocol --
    def page_count(self):
        return self.pages

    def current_page(self):
        return self.page

    def goto_page(self, index):
        self._rec("goto_page", index)

    def goto_label(self, label):
        self._rec("goto_label", label)

    def goto_scroll(self, where):
        self._rec("goto_scroll", where)

    def page_label(self, index):
        return str(index + 1)

    def scroll(self, dy, dx=0):
        self._rec("scroll", dy, dx)

    def scroll_pages(self, dy):
        self._rec("scroll_pages", dy)

    def zoom(self, delta_pct=None, set_pct=None, mode=None):
        self._rec("zoom", delta_pct, set_pct, mode)

    def rotate(self, delta):
        self._rec("rotate", delta)

    def search(self, text):
        self._rec("search", text)
        self.query = text

    def search_next(self):
        self._rec("search_next")

    def search_prev(self):
        self._rec("search_prev")

    def clear_search(self):
        self._rec("clear_search")

    def start_prompt(self, kind):
        self._rec("start_prompt", kind)

    def prompt_action(self, action):
        self._rec("prompt_action", action)

    def open_hints(self, kind):
        self._rec("open_hints", kind)

    def activate_hint(self, label):
        self._rec("activate_hint", label)

    def hint_backspace(self):
        self._rec("hint_backspace")

    def history_back(self):
        self._rec("history_back")

    def history_forward(self):
        self._rec("history_forward")

    def load(self, path, password=None):
        self._rec("load", path)
        self.opened.append(path)

    def toggle_sidebar(self):
        self._rec("toggle_sidebar")

    def outline_goto(self, index):
        self._rec("outline_goto", index)

    def mark_set(self, char):
        self._rec("mark_set", char)

    def mark_jump(self, char):
        self._rec("mark_jump", char)

    def yank_selection(self):
        self._rec("yank_selection")

    def yank_page(self):
        self._rec("yank_page")

    def set_mode(self, mode):
        self._rec("set_mode", mode)
        self.mode = mode

    def message(self, text, level="info"):
        self.messages.append((text, level))

    def open_url(self, url):
        self._rec("open_url", url)
        self.urls.append(url)

    def quit(self):
        self._rec("quit")

    # -- document operations --
    def op_info(self, *args):
        self._rec("op_info", *args)

    def op_save_as(self, *args):
        self._rec("op_save_as", *args)

    def op_print(self, *args):
        self._rec("op_print", *args)

    def op_attachments(self, *args):
        self._rec("op_attachments", *args)

    def op_layers(self, *args):
        self._rec("op_layers", *args)

    def op_forms(self, *args):
        self._rec("op_forms", *args)

    def op_annotate(self, *args):
        self._rec("op_annotate", *args)

    def op_sign(self, *args):
        self._rec("op_sign", *args)

    def op_redact(self, *args):
        self._rec("op_redact", *args)

    def op_ocr(self, *args):
        self._rec("op_ocr", *args)
