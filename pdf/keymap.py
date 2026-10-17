"""Vim-style keymap: modes, key sequences, the bind table, and the resolver.

Pure Python — no Qt. This is where the qutebrowser-shaped interaction lives:
bindings are plain strings (`"gg": "goto first"`), a key sequence is parsed into
tokens, and a prefix-aware resolver turns a stream of keypresses into commands.

Resolution rules (deliberately vim-compatible):

  * a buffer that is a complete binding and is NOT a prefix of a longer binding
    fires immediately;
  * a buffer that is a complete binding AND a prefix of a longer binding stays
    PENDING, so the caller can wait (and later `flush()` it);
  * a buffer that is a proper prefix of some binding stays PENDING;
  * anything else is UNMATCHED and the buffer resets.

That is what lets an unbound ``g`` sit in front of bound ``gg``/``gu``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── results of feeding a key ─────────────────────────────────────────────
PENDING = "pending"
FIRED = "fired"
UNMATCHED = "unmatched"

MODES = ("normal", "command", "search", "hint", "visual")


# ── key-sequence parsing ─────────────────────────────────────────────────

def parse_sequence(seq: str) -> tuple[str, ...]:
    """Split a key sequence into tokens.

    ``"<C-d>"`` -> ``("<C-d>",)``; ``"gg"`` -> ``("g", "g")``; ``"<Esc>j"`` ->
    ``("<Esc>", "j")``. An unterminated ``"<"`` is taken as a literal ``"<"``.
    """
    tokens: list[str] = []
    i = 0
    while i < len(seq):
        char = seq[i]
        if char == "<":
            close = seq.find(">", i)
            if close == -1:
                tokens.append(char)
                i += 1
            else:
                tokens.append(seq[i:close + 1])
                # max() keeps the index strictly increasing, so even a mutated
                # branch condition can never turn this into an infinite loop.
                i = max(close + 1, i + 1)
        else:
            tokens.append(char)
            i += 1
    return tuple(tokens)


def format_sequence(tokens: tuple[str, ...]) -> str:
    """Inverse of :func:`parse_sequence` — join tokens back into one string."""
    return "".join(tokens)


# ── the default bind table ───────────────────────────────────────────────

# normal-mode bindings. Keys are sequences; values are command lines, exactly as
# if typed after ':' (arguments included), so a binding and a command are one concept.
DEFAULT_BINDS: dict[str, dict[str, str]] = {
    "normal": {
        # motion — vim hjkl + half/full page
        "j": "scroll-down",
        "k": "scroll-up",
        "h": "scroll-left",
        "l": "scroll-right",
        "<C-d>": "half-down",
        "<C-u>": "half-up",
        "<C-f>": "page-next",
        "<C-b>": "page-prev",
        "J": "page-next",
        "K": "page-prev",
        "<Space>": "page-next",
        "gg": "first",
        "G": "last",
        "H": "top",
        "M": "middle",
        "L": "bottom",
        "gt": "page-next",
        "gT": "page-prev",
        # zoom
        "+": "zoom-in",
        "-": "zoom-out",
        "=": "zoom-reset",
        "zi": "zoom-in",
        "zo": "zoom-out",
        "zw": "zoom-fit-width",
        "zp": "zoom-fit-page",
        # rotate
        "r": "rotate-cw",
        "R": "rotate-ccw",
        # search
        "/": "search-prompt",
        "?": "search-prev-prompt",
        "n": "search-next",
        "N": "search-prev",
        # hints (follow links / annotations)
        "f": "hint-follow",
        "F": "hint-open",
        # navigation history
        "<C-o>": "history-back",
        "<C-i>": "history-forward",
        # open
        "o": "open-prompt",
        "O": "open-prompt",
        "t": "sidebar-toggle",
        "w": "web-search-prompt",
        # yank / select
        "y": "yank-selection",
        "Y": "yank-page",
        "v": "visual",
        # marks
        "m": "mark",
        "'": "mark-jump",
        # document operations
        "i": "info",
        "s": "save-as",
        "p": "print",
        "a": "attachments",
        # NOT "l": vim's `l` is scroll-right, and it was already bound above — a second
        # "l" in this same dict silently WON (later key), so the vim motion was dead and
        # the doc-op was the only thing `l` did. Layers moved to <C-l> instead.
        "<C-l>": "layers",
        # write-side operations
        "e": "forms",
        "A": "annotate",
        "S": "sign",
        "x": "redact",
        "C": "ocr",
        # chrome
        ":": "command-prompt",
        "q": "quit",
        "<C-q>": "quit",
        "b": "sidebar-toggle",
        "<Esc>": "search-clear",
    },
    # the ':' line and '/' line consume text; only a few control keys are bound
    "command": {"<Esc>": "prompt-cancel", "<CR>": "prompt-accept", "<Tab>": "prompt-complete"},
    "search": {"<Esc>": "prompt-cancel", "<CR>": "prompt-accept", "<Tab>": "prompt-complete"},
    # hint mode: typing label characters narrows; <Esc> leaves
    "hint": {"<Esc>": "hint-clear", "<BS>": "hint-backspace"},
    # visual mode: motions extend the selection, y yanks, <Esc> leaves
    "visual": {
        "j": "scroll-down", "k": "scroll-up",
        "h": "scroll-left", "l": "scroll-right",
        "y": "yank-selection", "<Esc>": "search-clear",
    },
}


# ── the resolver ─────────────────────────────────────────────────────────

@dataclass
class Resolution:
    """The outcome of feeding one key into the resolver."""
    state: str
    command: str | None = None
    buffer: tuple[str, ...] = ()


class KeyMap:
    """A prefix-aware key resolver over a mode -> {sequence: command} table."""

    def __init__(self, binds: dict[str, dict[str, str]] | None = None):
        table = binds if binds is not None else DEFAULT_BINDS
        self.binds: dict[str, dict[tuple[str, ...], str]] = {
            mode: {parse_sequence(seq): cmd for seq, cmd in mapping.items()}
            for mode, mapping in table.items()
        }

    # -- introspection ----------------------------------------------------
    def modes(self) -> list[str]:
        return sorted(self.binds)

    def bindings(self, mode: str) -> dict[str, str]:
        """Return the human-readable bindings for a mode."""
        return {
            format_sequence(seq): cmd
            for seq, cmd in self.binds.get(mode, {}).items()
        }

    def command_for(self, mode: str, sequence: str) -> str | None:
        return self.binds.get(mode, {}).get(parse_sequence(sequence))

    # -- binding ----------------------------------------------------------
    def bind(self, mode: str, sequence: str, command: str) -> None:
        self.binds.setdefault(mode, {})[parse_sequence(sequence)] = command

    def unbind(self, mode: str, sequence: str) -> None:
        self.binds.get(mode, {}).pop(parse_sequence(sequence), None)

    # -- resolution -------------------------------------------------------
    @staticmethod
    def _is_prefix(mapping: dict[tuple[str, ...], str], buffer: tuple[str, ...]) -> bool:
        """True when some binding is *longer* than `buffer` and starts with it."""
        n = len(buffer)
        return any(len(seq) > n and seq[:n] == buffer for seq in mapping)

    def feed(self, mode: str, key: str, buffer: tuple[str, ...] = ()) -> Resolution:
        """Feed one key. Returns a :class:`Resolution`; caller keeps the buffer."""
        mapping = self.binds.get(mode, {})
        buf = buffer + (key,)
        if buf in mapping:
            if self._is_prefix(mapping, buf):
                return Resolution(PENDING, None, buf)
            return Resolution(FIRED, mapping[buf], ())
        if self._is_prefix(mapping, buf):
            return Resolution(PENDING, None, buf)
        return Resolution(UNMATCHED, None, ())

    def flush(self, mode: str, buffer: tuple[str, ...]) -> Resolution:
        """Timeout flush: fire a buffer that is already a complete binding."""
        if buffer and buffer in self.binds.get(mode, {}):
            return Resolution(FIRED, self.binds[mode][buffer], ())
        return Resolution(UNMATCHED, None, ())


def default_keymap() -> KeyMap:
    return KeyMap()
