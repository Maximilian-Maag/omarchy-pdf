"""The command layer: a registry, a parser, dispatch, and completion.

Pure Python, no Qt. Commands operate on a *view* object that satisfies the protocol
documented in docs/architecture.md §4. Keeping the layer Qt-free is what lets the
whole vim workflow be tested head-less against a fake view — and why the keymap and
command layer can be mutation targets with a high kill rate.

Every command name is a single hyphenated token, so a binding value is exactly a
command line as if typed after ':' (``"gg": "first"``). A test asserts every default
binding resolves to a real command, so a dead binding cannot ship.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import nav


class CommandError(Exception):
    """Raised for an unknown command or bad arguments — surfaced to the user."""


@dataclass(frozen=True)
class Command:
    name: str
    handler: Callable[[object, tuple[str, ...]], None]
    help: str = ""
    aliases: tuple[str, ...] = ()
    rest: bool = False          # take the whole remainder as a single argument
    minimum: int = 0            # minimum positional args (handlers enforce arity)


# ── helpers used by handlers ─────────────────────────────────────────────

def _require(args: tuple[str, ...], count: int, usage: str) -> None:
    if len(args) != count:
        raise CommandError(f"usage: {usage}")


def _int(text: str, what: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise CommandError(f"{what} must be a number: {text!r}") from None


# ── handlers ─────────────────────────────────────────────────────────────
# every handler is (view, args) -> None and only touches the view protocol.

def _scroll(dy: int, dx: int = 0):
    def handler(view, args):
        _require(args, 0, "scroll")
        view.scroll(dy, dx)
    return handler


def _scroll_pages(dy: int):
    def handler(view, args):
        _require(args, 0, "half-page")
        view.scroll_pages(dy)
    return handler


def _page_step(delta: int):
    def handler(view, args):
        _require(args, 0, "page-step")
        view.goto_page(nav.clamp_page(view.current_page() + delta, view.page_count()))
    return handler


def _goto_edge(where: str):
    def handler(view, args):
        _require(args, 0, "goto-edge")
        if where == "first":
            view.goto_page(nav.first_page(view.page_count()))
        elif where == "last":
            view.goto_page(nav.last_page(view.page_count()))
        else:
            view.goto_scroll(where)
    return handler


def h_goto(view, args):
    """goto <page|label> — 1-based page number or a document page label."""
    _require(args, 1, "goto <page|label>")
    target = args[0]
    if target.lstrip("+-").isdigit():
        view.goto_page(nav.clamp_page(int(target) - 1, view.page_count()))
    else:
        view.goto_label(target)


def _zoom_steps(delta: int):
    def handler(view, args):
        _require(args, 0, "zoom")
        view.zoom(delta_pct=delta)
    return handler


def h_zoom_set(view, args):
    """zoom <percent> — set the zoom level explicitly."""
    _require(args, 1, "zoom <percent>")
    view.zoom(set_pct=nav.clamp_zoom(_int(args[0], "zoom")))


def _zoom_fit(mode: str):
    def handler(view, args):
        _require(args, 0, "zoom-fit")
        view.zoom(mode=mode)
    return handler


def _rotate(delta: int):
    def handler(view, args):
        _require(args, 0, "rotate")
        view.rotate(delta)
    return handler


def h_search(view, args):
    """search <text> — run a full-document search."""
    _require(args, 1, "search <text>")
    view.search(args[0])


def h_search_prompt(view, args):
    _require(args, 0, "search-prompt")
    view.start_prompt("search")


def h_search_prev_prompt(view, args):
    _require(args, 0, "search-prev-prompt")
    view.start_prompt("search-prev")


def _search_step(action: str):
    def handler(view, args):
        _require(args, 0, "search-step")
        getattr(view, f"search_{action}")()
    return handler


def _hint(kind: str):
    def handler(view, args):
        _require(args, 0, "hint")
        view.open_hints(kind)
    return handler


def h_hint_activate(view, args):
    """hint <label> — activate a hint directly (as if its label were typed)."""
    _require(args, 1, "hint-activate <label>")
    view.activate_hint(args[0])


def h_hint_backspace(view, args):
    _require(args, 0, "hint-backspace")
    view.hint_backspace()


def _history(action: str):
    def handler(view, args):
        _require(args, 0, "history")
        getattr(view, f"history_{action}")()
    return handler


def h_open(view, args):
    """open <path> — load a document."""
    _require(args, 1, "open <path>")
    view.load(args[0])


def h_open_prompt(view, args):
    _require(args, 0, "open-prompt")
    view.start_prompt("open")


def h_web_search_prompt(view, args):
    _require(args, 0, "web-search-prompt")
    view.start_prompt("web-search")


def h_outline_toggle(view, args):
    _require(args, 0, "sidebar-toggle")
    view.toggle_sidebar()


def h_outline_goto(view, args):
    """outline-goto <index> — jump to outline entry `index`."""
    _require(args, 1, "outline-goto <index>")
    view.outline_goto(_int(args[0], "outline index"))


def h_yank_selection(view, args):
    _require(args, 0, "yank-selection")
    view.yank_selection()


def h_yank_page(view, args):
    _require(args, 0, "yank-page")
    view.yank_page()


def h_visual(view, args):
    _require(args, 0, "visual")
    view.set_mode("visual")


def h_mark_set(view, args):
    _require(args, 0, "mark")
    view.start_prompt("mark")


def h_mark_jump(view, args):
    _require(args, 0, "mark-jump")
    view.start_prompt("mark-jump")


def h_mark_store(view, args):
    """mark-set <char> — remember the current page under a mark."""
    _require(args, 1, "mark-set <char>")
    view.mark_set(args[0])


def h_mark_go(view, args):
    """mark-go <char> — jump to a stored mark."""
    _require(args, 1, "mark-go <char>")
    view.mark_jump(args[0])


def _doc_op(name: str):
    def handler(view, args):
        getattr(view, f"op_{name}")(*args)
    return handler


def h_command_prompt(view, args):
    _require(args, 0, "command-prompt")
    view.start_prompt("command")


def _prompt_action(action: str):
    def handler(view, args):
        _require(args, 0, f"prompt-{action}")
        view.prompt_action(action)
    return handler


def h_quit(view, args):
    _require(args, 0, "quit")
    view.quit()


def h_clear(view, args):
    _require(args, 0, "search-clear")
    view.clear_search()


def h_help(view, args):
    _require(args, 0, "help")
    view.message("j/k scroll  gg/G top/end  /search  f hint  :command  q quit")


def _mode_command(mode: str):
    def handler(view, args):
        _require(args, 0, "set-mode")
        view.set_mode(mode)
    return handler


# ── the registry ─────────────────────────────────────────────────────────

_COMMANDS: list[Command] = [
    # motion
    Command("scroll-down", _scroll(60), "scroll down a line"),
    Command("scroll-up", _scroll(-60), "scroll up a line"),
    Command("scroll-left", _scroll(0, -60), "scroll left"),
    Command("scroll-right", _scroll(0, 60), "scroll right"),
    Command("half-down", _scroll_pages(1), "half a page down"),
    Command("half-up", _scroll_pages(-1), "half a page up"),
    Command("page-next", _page_step(1), "next page"),
    Command("page-prev", _page_step(-1), "previous page"),
    Command("first", _goto_edge("first"), "first page"),
    Command("last", _goto_edge("last"), "last page"),
    Command("top", _goto_edge("top"), "top of the page"),
    Command("middle", _goto_edge("middle"), "middle of the page"),
    Command("bottom", _goto_edge("bottom"), "bottom of the page"),
    Command("goto", h_goto, "goto <page|label>", minimum=1),
    # zoom
    Command("zoom-in", _zoom_steps(1), "zoom in"),
    Command("zoom-out", _zoom_steps(-1), "zoom out"),
    Command("zoom-reset", _zoom_steps(0), "reset zoom"),
    Command("zoom-set", h_zoom_set, "zoom <percent>", minimum=1),
    Command("zoom-fit-width", _zoom_fit("width"), "fit width"),
    Command("zoom-fit-page", _zoom_fit("page"), "fit page"),
    # rotate
    Command("rotate-cw", _rotate(90), "rotate clockwise"),
    Command("rotate-ccw", _rotate(-90), "rotate counter-clockwise"),
    # search
    Command("search", h_search, "search <text>", rest=True, minimum=1),
    Command("search-prompt", h_search_prompt, "prompt for a search string"),
    Command("search-prev-prompt", h_search_prev_prompt, "prompt for a backward search"),
    Command("search-next", _search_step("next"), "next search hit"),
    Command("search-prev", _search_step("prev"), "previous search hit"),
    Command("search-clear", h_clear, "clear the search highlight", aliases=("clear",)),
    # hints
    Command("hint-follow", _hint("follow"), "follow a link (hint mode)"),
    Command("hint-open", _hint("open"), "open a link in the browser"),
    Command("hint-activate", h_hint_activate, "hint-activate <label>", minimum=1),
    Command("hint-clear", _mode_command("normal"), "leave hint mode"),
    Command("hint-backspace", h_hint_backspace, "delete a hint character"),
    # history
    Command("history-back", _history("back"), "history back"),
    Command("history-forward", _history("forward"), "history forward"),
    # open / outline
    Command("open", h_open, "open <path>", minimum=1),
    Command("open-prompt", h_open_prompt, "prompt for a file to open"),
    Command("web-search-prompt", h_web_search_prompt, "prompt for a web search"),
    Command("sidebar-toggle", h_outline_toggle, "toggle the outline sidebar"),
    Command("outline-goto", h_outline_goto, "outline-goto <index>", minimum=1),
    # yank / modes
    Command("yank-selection", h_yank_selection, "yank the selection"),
    Command("yank-page", h_yank_page, "yank the page text"),
    Command("visual", h_visual, "enter visual mode"),
    Command("mark", h_mark_set, "set a mark"),
    Command("mark-jump", h_mark_jump, "jump to a mark"),
    Command("mark-set", h_mark_store, "mark-set <char>", minimum=1),
    Command("mark-go", h_mark_go, "mark-go <char>", minimum=1),
    # document operations (read side)
    Command("info", _doc_op("info"), "document info"),
    Command("save-as", _doc_op("save_as"), "save a copy"),
    Command("print", _doc_op("print"), "print the document"),
    Command("attachments", _doc_op("attachments"), "list embedded files"),
    Command("layers", _doc_op("layers"), "list optional-content layers"),
    # write-side operations
    Command("forms", _doc_op("forms"), "fill AcroForm fields"),
    Command("annotate", _doc_op("annotate"), "add an annotation"),
    Command("sign", _doc_op("sign"), "sign / verify (QES)"),
    Command("redact", _doc_op("redact"), "redact a region"),
    Command("ocr", _doc_op("ocr"), "OCR the document"),
    # chrome
    Command("command-prompt", h_command_prompt, "open the command line"),
    Command("prompt-cancel", _prompt_action("cancel"), "cancel the prompt"),
    Command("prompt-accept", _prompt_action("accept"), "accept the prompt"),
    Command("prompt-complete", _prompt_action("complete"), "complete the current word"),
    Command("quit", h_quit, "close the viewer", aliases=("q",)),
    Command("help", h_help, "show a short help"),
]

_BY_NAME: dict[str, Command] = {}


def _register(command: Command) -> None:
    _BY_NAME[command.name] = command
    for alias in command.aliases:
        _BY_NAME[alias] = command


for _c in _COMMANDS:
    _register(_c)


def registry() -> dict[str, Command]:
    """The name -> Command table (includes aliases)."""
    return dict(_BY_NAME)


def lookup(name: str) -> Command | None:
    return _BY_NAME.get(name)


def parse(line: str) -> tuple[str, str]:
    """Split a command line into (name, remainder). Blank input yields ("", "")."""
    stripped = line.strip()
    if not stripped:
        return "", ""
    name, _, rest = stripped.partition(" ")
    return name, rest


def dispatch(view, line: str) -> Command | None:
    """Run `line` against `view`. Raises :class:`CommandError` on bad input."""
    name, rest = parse(line)
    if not name:
        return None
    command = _BY_NAME.get(name)
    if command is None:
        raise CommandError(f"not a command: {name}")
    if command.rest:
        if not rest.strip(" "):
            raise CommandError(f"usage: {command.help or command.name}")
        args: tuple[str, ...] = (rest,)
    else:
        args = tuple(rest.split()) if rest else ()
    if len(args) < command.minimum:
        raise CommandError(f"usage: {command.help or command.name}")
    command.handler(view, args)
    return command


def complete(prefix: str) -> list[str]:
    """Command names beginning with `prefix`, sorted."""
    return sorted(name for name in _BY_NAME if name.startswith(prefix))


def command_names() -> list[str]:
    return sorted(_BY_NAME)
