#!/usr/bin/env python3
"""Protected-content candidate scan over numbered source units.

`scan(units)` runs cheap, case-insensitive regexes over every non-skipped
unit and returns, per protected category, the sorted unique ids of units
that *might* carry that kind of content (medication changes, follow-up,
return precautions, diagnoses, disposition, abnormal or pending results).
The scan is tuned for high recall: false positives are expected and are
dismissed by the verifier; a missed candidate is the costly error. The
result is written by unitize.py as `01_protected.json` (schema
`protected`).

Category notes:

- `medication_changes` includes explicit "no new medications prescribed"
  statements (they match `prescri`), so a none-statement is a candidate the
  writer must show or the verifier must dismiss.
- A dose alone (for example a contrast volume) is not a candidate; the dose
  pattern needs a number with a unit *and* a frequency or oral-route word in
  the same unit.

Stdlib only. Importable as `protected`.
"""

from __future__ import annotations

import re

# Same order as schema/protected.schema.json `categories.required`.
CATEGORIES = (
    "medication_changes",
    "follow_up",
    "return_precautions",
    "diagnoses",
    "disposition",
    "abnormal_or_pending_results",
)


def _compile(*patterns: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    "medication_changes": _compile(
        r"prescri",
        r"\b(start|started|starting|stop|stopped|stopping|discontinue|discontinued|"
        r"increase|decrease|resume|resumed|hold|held|switch(ed)? to|change(d)? to)\b",
        r"\bnew (medication|medicine|prescription|drug)s?\b",
        r"\b(refill|taper)",
    ),
    "follow_up": _compile(
        r"\bfollow[- ]?up\b",
        r"\bschedul",
        r"\bappointment",
        r"\brefer(ral|red|ring)?\b",
        r"\bsee (your|a|an|the) (primary|pcp|doctor|physician|provider|specialist|cardiolog|neurolog)",
        r"\bf/u\b",
        r"\breturn to (the )?(clinic|office)\b",
        r"\b(within|in) (\d+(\s*(-|to)\s*\d+)?|one|two|three|four|five|six|a few|several) ?"
        r"(day|week|month)s?\b",
        r"\b(recheck|re-check)\b",
    ),
    "return_precautions": _compile(
        r"\breturn to (the )?(er|ed|emergency)",
        r"\bcome back\b",
        r"\bseek (immediate|emergency|urgent|medical|prompt)",
        r"\b(call|dial) 911\b",
        r"\bgo to (the )?(nearest )?(emergency|er\b|ed\b)",
        r"\breturn (precautions|if|for)\b",
        r"\bif\b.*\b(worsen|worsens|worsening|worse)\b",
        r"\bwarning signs\b",
        r"\b(call|contact)\b.*\b(if|right away|immediately|same day)\b",
    ),
    "diagnoses": _compile(
        r"diagnos",
        r"\bimpression",
        r"\bassessment",
        r"\bfinal dx\b",
        r"\bdx\b",
    ),
    "disposition": _compile(
        r"discharg",
        r"\badmit",
        r"\bdisposition",
        r"\btransfer",
        r"\b(stable|good|fair|serious|critical|satisfactory|improved) condition\b",
        r"\bagainst medical advice\b",
    ),
    "abnormal_or_pending_results": _compile(
        r"\bpending\b",
        r"\bawaiting\b",
        r"\babnormal",
        r"\belevated\b",
        r"\bcritical\b",
        r"\bpositive\b",
        r"\((h|l|hh|ll|a)\)",
        r"\bflagged\b",
        r"\bnot (yet )?resulted\b",
        r"\bresults? (to follow|will be)\b",
    ),
}

# Dose + frequency/oral route in the same unit (e.g. "ibuprofen 400 mg by mouth
# every 6 hours"); a bare volume such as "80 mL IV" contrast is not a candidate.
_DOSE = re.compile(r"\b\d+(\.\d+)? ?(mg|mcg|g|ml|units?)\b", re.IGNORECASE)
_FREQUENCY_OR_ROUTE = re.compile(
    r"\b(daily|bid|tid|qid|qhs|prn|by mouth|po|orally|every|twice|times|nightly|"
    r"as needed|once a day)\b",
    re.IGNORECASE,
)


def _matches(category: str, text: str) -> bool:
    if any(pattern.search(text) for pattern in _PATTERNS[category]):
        return True
    if category == "medication_changes":
        return bool(_DOSE.search(text) and _FREQUENCY_OR_ROUTE.search(text))
    return False


def categories_for(text: str) -> list[str]:
    """Return the protected categories whose patterns match `text`, in CATEGORIES order."""
    return [category for category in CATEGORIES if _matches(category, text)]


def scan(units: list[dict]) -> dict[str, list[int]]:
    """Return {category: sorted unique unit ids} over units without a `skip` key.

    Every category in CATEGORIES is present, possibly with an empty list.
    """
    found: dict[str, set[int]] = {category: set() for category in CATEGORIES}
    for unit in units:
        if unit.get("skip"):
            continue
        for category in categories_for(unit.get("text", "")):
            found[category].add(unit["id"])
    return {category: sorted(found[category]) for category in CATEGORIES}


def candidate_ids(categories: dict[str, list[int]]) -> set[int]:
    """Every unit id that is a candidate in at least one category."""
    return {uid for ids in categories.values() for uid in ids}
