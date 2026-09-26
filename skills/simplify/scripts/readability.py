#!/usr/bin/env python3
"""Flesch-Kincaid grade level, a rough reading-level estimate.

This is a reading-level estimate only, not a measure of quality, clarity,
or medical accuracy. It counts words, sentences, and syllables and applies
a fixed formula; it says nothing about whether the text is correct or
well organized.

Stdlib only. Importable as `readability` (`fk_grade(text) -> float | None`)
and runnable as `python3 readability.py <file>`.
"""

from __future__ import annotations

import re
import sys

_WORD_RE = re.compile(r"\S+")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")
_NON_ALPHA_RE = re.compile(r"[^a-z]")

_MIN_WORDS = 30


def _syllables_in_word(word: str) -> int:
    w = _NON_ALPHA_RE.sub("", word.lower())
    if not w:
        return 1
    groups = _VOWEL_GROUP_RE.findall(w)
    count = len(groups)
    if w.endswith("e"):
        ends_le = w.endswith("le") and len(w) > 2 and w[-3] not in "aeiouy"
        if not ends_le:
            count -= 1
    return max(count, 1)


def fk_grade(text: str) -> float | None:
    """Flesch-Kincaid grade level for `text`, rounded to 1 decimal.

    Returns None when `text` has fewer than 30 words -- too little text
    for the estimate to mean anything.
    """
    if not text:
        return None

    words = [w for w in _WORD_RE.findall(text) if _HAS_LETTER_RE.search(w)]
    if len(words) < _MIN_WORDS:
        return None

    n_words = len(words)
    n_sentences = max(len(_SENTENCE_END_RE.findall(text)), 1)
    n_syllables = sum(_syllables_in_word(w) for w in words)

    grade = 0.39 * (n_words / n_sentences) + 11.8 * (n_syllables / n_words) - 15.59
    return round(grade, 1)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 readability.py <file>", file=sys.stderr)
        return 2
    with open(argv[0], "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    grade = fk_grade(text)
    print(grade if grade is not None else "None")
    return 0


if __name__ == "__main__":
    sys.exit(main())
