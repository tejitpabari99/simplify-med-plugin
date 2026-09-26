#!/usr/bin/env python3
"""Text normalization helpers shared by the grounding path.

Ported from simplify-med's ``backend/utils/text_normalization.py``
(``normalize_text`` / ``normalize_with_offsets``), plus two helpers new to
this plugin: ``is_informative`` (the quote informativeness floor) and
``find_normalized`` (locate a normalized needle's raw offsets in a raw
haystack).

Stdlib only. Importable as ``textnorm``.
"""

from __future__ import annotations

import unicodedata


def normalize_with_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Normalize `text` (NFKD-decompose, ASCII-encode with errors="ignore",
    lowercase, collapse/strip whitespace) and return the normalized string
    together with, for each normalized character, the (start, end) span
    (Python slice semantics) of raw `text` indices it was derived from.
    ``len(spans) == len(normalized)`` always.

    Two passes:

    1. Per-character transliteration: each raw character is individually
       NFKD-decomposed, ASCII-encoded (errors="ignore"), lowercased. This
       yields zero or more output characters per raw character, each
       tagged with the raw (i, i+1) span of the single input character
       that produced it.
    2. Whitespace collapse, mirroring ``" ".join(text.split())``: a
       maximal interior run of whitespace-classified characters becomes a
       single " " tagged with the run's own (start, end); leading/trailing
       runs are dropped entirely.
    """
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    for i, raw_char in enumerate(text):
        nfkd = unicodedata.normalize("NFKD", raw_char)
        ascii_char = nfkd.encode("ascii", "ignore").decode("ascii").lower()
        for out_char in ascii_char:
            chars.append(out_char)
            spans.append((i, i + 1))

    normalized_chars: list[str] = []
    normalized_spans: list[tuple[int, int]] = []
    total = len(chars)
    i = 0
    while i < total:
        if chars[i].isspace():
            run_start = spans[i][0]
            run_end = spans[i][1]
            j = i
            while j < total and chars[j].isspace():
                run_end = spans[j][1]
                j += 1
            if normalized_chars and j < total:
                # Interior run: neither leading (something already emitted)
                # nor trailing (more non-whitespace content follows).
                normalized_chars.append(" ")
                normalized_spans.append((run_start, run_end))
            i = j
        else:
            normalized_chars.append(chars[i])
            normalized_spans.append(spans[i])
            i += 1

    return "".join(normalized_chars), normalized_spans


def normalize_text(text: str) -> str:
    """Lowercase, strip accents, and collapse whitespace."""
    return normalize_with_offsets(text)[0]


# Quote informativeness floor, ported from simplify-med's
# backend/care_plan/pipeline.py (_QUOTE_MIN_LENGTH, _QUOTE_LONG_WORD_MIN_LENGTH).
_MIN_LENGTH = 12
_LONG_WORD_MIN_LENGTH = 7


def is_informative(text: str) -> bool:
    """True if `text` carries enough content to be worth citing: it
    contains a digit, or any word of `_LONG_WORD_MIN_LENGTH`-plus
    characters, or its stripped length is `_MIN_LENGTH`-plus characters."""
    if any(ch.isdigit() for ch in text):
        return True
    if any(len(word) >= _LONG_WORD_MIN_LENGTH for word in text.split()):
        return True
    return len(text.strip()) >= _MIN_LENGTH


def find_normalized(needle: str, haystack: str) -> tuple[int, int] | None:
    """Find the first occurrence of `needle`, compared in normalized form,
    inside raw `haystack`, and return its raw (start, end) span (Python
    slice semantics). Returns None if `needle` normalizes to the empty
    string or is not found."""
    normalized_needle = normalize_text(needle)
    if not normalized_needle:
        return None
    normalized_haystack, spans = normalize_with_offsets(haystack)
    idx = normalized_haystack.find(normalized_needle)
    if idx == -1:
        return None
    start = spans[idx][0]
    end = spans[idx + len(normalized_needle) - 1][1]
    return start, end
