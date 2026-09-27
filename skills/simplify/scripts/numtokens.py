#!/usr/bin/env python3
"""Numeric tokenizer shared by check_draft, settle, and finalize.

Moved unchanged in behavior from the retired ``numeric_parity.py`` (a
faithful port of simplify-med's ``_extract_number_tokens``): same tokenizer
regexes, same date/time-of-day exclusions, same known-unit-word vocabulary,
same 15-char unit-word bound.

A visible string's number tokens must appear in the text of the source units
that string's item cites; ``unbacked_tokens`` names the ones that do not.

Stdlib only. Importable as `numtokens`.
"""

from __future__ import annotations

import re
from collections import Counter

_UNIT_WORD_MAX_LENGTH = 15  # reasoned, not calibrated: long enough for the
# longest realistic compound lab unit (mmol/L, mIU/mL), short enough that it
# can't silently swallow the start of the next clinical word if a unit is
# missing.

_UNIT_WORD_RE = rf"%|[A-Za-z][A-Za-z%/]{{0,{_UNIT_WORD_MAX_LENGTH - 1}}}"

# A closed vocabulary of clinical units/counts, used only to decide whether a
# slash pair ("4/12") is a bare date or a unit-bearing ratio.
KNOWN_UNIT_WORDS: frozenset[str] = frozenset({
    "%", "mg", "mcg", "µg", "ug", "g", "gm", "kg", "lb", "lbs", "oz",
    "ml", "l", "dl", "cc", "unit", "units", "iu", "meq", "mmol", "mmhg",
    "bpm", "mg/dl", "mmol/l", "g/dl", "mg/kg", "mcg/kg", "miu/ml", "u/l",
    "tablet", "tablets", "tab", "tabs", "pill", "pills", "capsule",
    "capsules", "cap", "caps", "puff", "puffs", "drop", "drops", "spray",
    "sprays", "patch", "patches", "cup", "cups", "tsp", "tbsp",
    "teaspoon", "teaspoons", "tablespoon", "tablespoons", "dose", "doses",
    "inch", "inches", "cm", "mm", "hour", "hours", "hr", "hrs", "minute",
    "minutes", "min", "day", "days", "week", "weeks", "month", "months",
    "year", "years",
})

_NUMBER_TOKEN_RE = re.compile(
    r"""
    (?P<num>
        \d{1,3}(?:,\d{3})+(?:\.\d+)?        # 1,000 or 1,000.5
      | \d+/\d+                             # fraction OR ratio/date shape: 1/2, 158/96, 4/12
      | \d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?   # range: 5-10, 5.5-10.2
      | \d+(?:\.\d+)?                       # plain integer or decimal
    )
    [ ]?
    (?P<unit>""" + _UNIT_WORD_RE + r""")?
    """,
    re.VERBOSE,
)

_TIME_OF_DAY_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

# A slash pair is a unit-bearing ratio, not a bare date, only when followed
# by a *known* unit word -- not just any word.
_bare_date_alpha_units = sorted((w for w in KNOWN_UNIT_WORDS if w != "%"), key=len, reverse=True)
_BARE_DATE_UNIT_LOOKAHEAD = (
    r"(?:%|(?:" + "|".join(re.escape(w) for w in _bare_date_alpha_units) + r")\b)"
)
_BARE_DATE_RE = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b(?![ \t]*" + _BARE_DATE_UNIT_LOOKAHEAD + r")",
    re.IGNORECASE,
)
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
)
_WRITTEN_DATE_RE = re.compile(
    r"\b(?:" + "|".join(_MONTH_NAMES) + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)


def normalize_number(raw: str) -> str:
    """Canonicalize one bare number's own digits -- leading zeros, thousands
    separators, and a trailing decimal zero are formatting, not value."""
    raw = raw.replace(",", "")
    if "." in raw:
        integer_part, _, frac_part = raw.partition(".")
        frac_part = frac_part.rstrip("0")
        integer_part = integer_part.lstrip("0") or "0"
        return f"{integer_part}.{frac_part}" if frac_part else integer_part
    return raw.lstrip("0") or "0"


def excluded_spans(text: str) -> list[tuple[int, int]]:
    """Date/time-shaped spans, dropped from BOTH sides of every numeric
    comparison. Any number token merely overlapping one of these spans is
    dropped, not just one fully contained in it."""
    spans = [m.span() for m in _TIME_OF_DAY_RE.finditer(text)]
    spans += [m.span() for m in _BARE_DATE_RE.finditer(text)]
    spans += [m.span() for m in _WRITTEN_DATE_RE.finditer(text)]
    return spans


def extract_number_tokens(text: str) -> Counter[tuple[str, str]]:
    """Tokenize numbers as (normalized number, lowercased unit word) with
    multiplicity, excluding dates and times of day."""
    excluded = excluded_spans(text)
    tokens: Counter[tuple[str, str]] = Counter()
    for m in _NUMBER_TOKEN_RE.finditer(text):
        if any(m.start() < e and m.end() > s for s, e in excluded):
            continue
        num, unit = m.group("num"), (m.group("unit") or "").lower()
        if "/" in num:
            num_norm = "/".join(normalize_number(p) for p in num.split("/"))
        elif "-" in num:
            num_norm = "-".join(normalize_number(p.strip()) for p in num.split("-"))
        else:
            num_norm = normalize_number(num)
        tokens[(num_norm, unit)] += 1
    return tokens


def token_str(num: str, unit: str) -> str:
    """Render one token as "25 mg" (or "25" when it has no unit word)."""
    return f"{num} {unit}" if unit else num


def backing_tokens(texts) -> Counter[tuple[str, str]]:
    """All number tokens in an iterable of source texts (e.g. cited units)."""
    tokens: Counter[tuple[str, str]] = Counter()
    for text in texts:
        tokens.update(extract_number_tokens(text or ""))
    return tokens


def unbacked_tokens(text: str, backing: Counter[tuple[str, str]]) -> list[str]:
    """Distinct token strings in `text` that never appear in `backing`, in
    first-appearance order."""
    out: list[str] = []
    for token in extract_number_tokens(text):
        if backing[token] == 0:
            rendered = token_str(*token)
            if rendered not in out:
                out.append(rendered)
    return out
