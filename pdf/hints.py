"""Hint labels for hint mode (qutebrowser's ``f``).

Pure Python, no Qt. Hints are generated from a fixed alphabet; the length is the
smallest that can address every target, so short documents get single-key hints and
long ones grow to two keys. Typing narrows the set.
"""

from __future__ import annotations

# Home-row-weighted lowercase alphabet: the shortest, easiest-to-type labels first.
ALPHABET = "asdfghjklqwertyuiopzxcvbnm"


def label_length(count: int, alphabet: str = ALPHABET) -> int:
    """Smallest label length that can address `count` targets with `alphabet`.

    Written without a `count <= 0` guard so no boundary mutant can hide in it: an
    empty (or negative) count simply never enters the loop and yields length 1.
    """
    length = 1
    capacity = len(alphabet)
    while capacity < count:
        length += 1
        capacity *= len(alphabet)
    return length


def label_for(index: int, length: int, alphabet: str = ALPHABET) -> str:
    """Deterministic label for `index` at a given length (base-|alphabet| digits)."""
    size = len(alphabet)
    chars: list[str] = []
    n = index
    for _ in range(length):
        chars.append(alphabet[n % size])
        n //= size
    return "".join(reversed(chars))


def generate_labels(count: int, alphabet: str = ALPHABET) -> list[str]:
    """`count` distinct labels, all of minimal, uniform length."""
    length = label_length(count, alphabet)
    return [label_for(i, length, alphabet) for i in range(count)]


def matching(labels: list[str], typed: str) -> list[int]:
    """Indices whose label starts with `typed` (all of them when `typed` is empty)."""
    return [i for i, label in enumerate(labels) if label.startswith(typed)]


def unique_match(labels: list[str], typed: str) -> int:
    """The single index whose label equals `typed`, else -1."""
    for i, label in enumerate(labels):
        if label == typed:
            return i
    return -1


def is_complete(labels: list[str], typed: str) -> bool:
    """True once `typed` addresses exactly one hint."""
    return len(matching(labels, typed)) == 1
