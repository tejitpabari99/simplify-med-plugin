#!/usr/bin/env python3
"""Numeric-parity and thin-field hints for the assembled care plan.

Ports simplify-med's ``_extract_number_tokens`` / ``_check_numeric_parity``
and ``_RICHNESS_CHECKS`` / ``_is_informative_quote``
(``backend/care_plan/pipeline.py``) faithfully: same tokenizer regexes, same
date/time-of-day exclusions, same known-unit-word vocabulary, same 15-char
unit-word bound, same informativeness floor. Unlike simplify-med (which only
logs), this script writes its findings to ``03_flags.json`` so a downstream
reviewer agent can read them as hints.

This check never drops or mutates the plan -- it only produces hints, so it
always records "ok" (never "degraded").

Stdlib only. Runnable as ``python3 numeric_parity.py --run-dir D``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402
import runlog  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


# --- numeric tokenizer, ported verbatim from simplify-med's pipeline.py ---

_UNIT_WORD_MAX_LENGTH = 15  # reasoned, not calibrated (PRD 10 S4.2): long
# enough for the longest realistic compound lab unit (mmol/L, mIU/mL), short
# enough that it can't silently swallow the start of the next clinical word
# if a unit is missing.

_UNIT_WORD_RE = rf"%|[A-Za-z][A-Za-z%/]{{0,{_UNIT_WORD_MAX_LENGTH - 1}}}"

# A closed vocabulary of clinical units/counts, used only to decide whether a
# slash pair ("4/12") is a bare date or a unit-bearing ratio, and to keep an
# arbitrary following word (a drug or person name) out of the numeric-parity
# log.
_KNOWN_UNIT_WORDS: frozenset[str] = frozenset({
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


def _normalize_number(raw: str) -> str:
    """Canonicalize one bare number's own digits -- leading zeros, thousands
    separators, and a trailing decimal zero are formatting, not value."""
    raw = raw.replace(",", "")
    if "." in raw:
        integer_part, _, frac_part = raw.partition(".")
        frac_part = frac_part.rstrip("0")
        integer_part = integer_part.lstrip("0") or "0"
        return f"{integer_part}.{frac_part}" if frac_part else integer_part
    return raw.lstrip("0") or "0"


_TIME_OF_DAY_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

# A slash pair is a unit-bearing ratio, not a bare date, only when followed
# by a *known* unit word -- not just any word.
_bare_date_alpha_units = sorted((w for w in _KNOWN_UNIT_WORDS if w != "%"), key=len, reverse=True)
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


def _excluded_spans(text: str) -> list[tuple[int, int]]:
    """Date/time-shaped spans, dropped from BOTH sides of every numeric-
    parity comparison. Any number token merely overlapping one of these
    spans is dropped, not just one fully contained in it."""
    spans = [m.span() for m in _TIME_OF_DAY_RE.finditer(text)]
    spans += [m.span() for m in _BARE_DATE_RE.finditer(text)]
    spans += [m.span() for m in _WRITTEN_DATE_RE.finditer(text)]
    return spans


def _extract_number_tokens(text: str) -> set[tuple[str, str]]:
    """Tokenize every number-with-optional-unit out of `text` into a set of
    (normalized_number, normalized_unit) pairs; unit is "" when none is
    attached. Excludes date/time-shaped spans entirely."""
    excluded = _excluded_spans(text)
    tokens: set[tuple[str, str]] = set()
    for m in _NUMBER_TOKEN_RE.finditer(text):
        if any(m.start() < e and m.end() > s for s, e in excluded):
            continue
        num, unit = m.group("num"), (m.group("unit") or "").lower()
        if "/" in num:
            num_norm = "/".join(_normalize_number(p) for p in num.split("/"))
        elif "-" in num:
            num_norm = "-".join(_normalize_number(p.strip()) for p in num.split("-"))
        else:
            num_norm = _normalize_number(num)
        tokens.add((num_norm, unit))
    return tokens


# --- content-richness floor, ported from _is_informative_quote ---

_QUOTE_MIN_LENGTH = 12
_QUOTE_LONG_WORD_MIN_LENGTH = 7


def _is_informative(value: str) -> bool:
    if any(ch.isdigit() for ch in value):
        return True
    if any(len(word) >= _QUOTE_LONG_WORD_MIN_LENGTH for word in value.split()):
        return True
    return len(value) >= _QUOTE_MIN_LENGTH


# Ported from _RICHNESS_CHECKS (pipeline.py). diagnosis.details.description
# is handled in a dedicated loop below, mirroring the source's own layout.
_RICHNESS_CHECKS: tuple[tuple[str, str], ...] = (
    ("reason_for_visit", "description"),
    ("medications", "why"),
    ("tests", "why"),
    ("tests", "description"),
    ("procedures", "why"),
    ("other", "why"),
    ("other", "description"),
)

# Ported from _NUMERIC_PARITY_FIELDS (pipeline.py), extended to also cover
# reason_for_visit and diagnosis.details -- every item in the care plan
# carries source_fact_ids and is eligible for the same check (brief S3.3).
_NUMERIC_PARITY_FIELDS: dict[str, tuple[str, ...]] = {
    "reason_for_visit": ("reason", "description"),
    "medications": ("title", "plain_name", "why", "dosage", "frequency",
                     "timing", "duration", "instructions",
                     "side_effects_to_watch", "change"),
    "tests": ("title", "plain_name", "why", "description", "preparation"),
    "procedures": ("title", "plain_name", "why", "what_to_expect", "timeframe"),
    "other": ("title", "why", "description", "frequency", "duration"),  # steps[] handled separately
    "follow_up": ("time_frame", "description"),
    "warning_signs": ("symptom", "what_it_might_mean", "what_to_do", "related_to"),
}
_DIAGNOSIS_DETAIL_FIELDS = ("title", "plain_name", "description", "what_it_means_for_you")


def _token_str(num: str, unit: str) -> str:
    return f"{num} {unit}" if unit else num


def _backing_tokens(fact_ids, facts_by_id: dict) -> set[tuple[str, str]]:
    tokens: set[tuple[str, str]] = set()
    for fid in fact_ids:
        fact = facts_by_id.get(fid)
        if fact is None:
            continue
        combined = f"{fact.get('text', '')} {fact.get('quote', '')}"
        tokens |= _extract_number_tokens(combined)
    return tokens


def _check_field(path: str, value: str, backing: set[tuple[str, str]]) -> dict | None:
    if not value:
        return None
    field_tokens = _extract_number_tokens(value)
    if not field_tokens:
        return None
    if all(token in backing for token in field_tokens):
        return None
    return {
        "path": path,
        "tokens_in_field": sorted(_token_str(num, unit) for num, unit in field_tokens),
        "tokens_in_facts": sorted(_token_str(num, unit) for num, unit in backing),
    }


def _check_richness(path: str, value, thin_fields: list[dict]) -> None:
    if isinstance(value, str) and value and not _is_informative(value):
        thin_fields.append({"path": path, "value": value})


def _run(run_dir: str) -> int:
    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    facts_path = os.path.join(run_dir, "02_facts.json")

    if not os.path.isfile(draft_path):
        print(
            "numeric_parity: could not find 03_plan.draft.json in the run "
            "directory. cite_check must run before numeric_parity.",
            file=sys.stderr,
        )
        return 1
    if not os.path.isfile(facts_path):
        print(
            "numeric_parity: could not find 02_facts.json in the run "
            "directory.",
            file=sys.stderr,
        )
        return 1

    try:
        with open(draft_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"numeric_parity: 03_plan.draft.json is not valid JSON ({exc}).", file=sys.stderr)
        return 1
    try:
        with open(facts_path, "r", encoding="utf-8") as f:
            facts_data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"numeric_parity: 02_facts.json is not valid JSON ({exc}).", file=sys.stderr)
        return 1

    facts_by_id = {fact["id"]: fact for fact in facts_data.get("facts", [])}

    mismatches: list[dict] = []
    thin_fields: list[dict] = []
    fields_checked = 0

    for section, field_names in _NUMERIC_PARITY_FIELDS.items():
        items = plan.get(section, [])
        for idx, item in enumerate(items):
            backing = _backing_tokens(item.get("source_fact_ids", []), facts_by_id)
            for field in field_names:
                value = item.get(field)
                if not isinstance(value, str):
                    continue
                fields_checked += 1
                result = _check_field(f"{section}[{idx}].{field}", value, backing)
                if result:
                    mismatches.append(result)
            if section == "other":
                for step_idx, step in enumerate(item.get("steps", [])):
                    if not isinstance(step, str):
                        continue
                    fields_checked += 1
                    result = _check_field(f"other[{idx}].steps[{step_idx}]", step, backing)
                    if result:
                        mismatches.append(result)

    diagnosis = plan.get("diagnosis", {}) or {}
    details = diagnosis.get("details", [])
    for idx, detail in enumerate(details):
        backing = _backing_tokens(detail.get("source_fact_ids", []), facts_by_id)
        for field in _DIAGNOSIS_DETAIL_FIELDS:
            value = detail.get(field)
            if not isinstance(value, str):
                continue
            fields_checked += 1
            result = _check_field(f"diagnosis.details[{idx}].{field}", value, backing)
            if result:
                mismatches.append(result)

    summary = plan.get("summary")
    if isinstance(summary, str) and summary:
        fields_checked += 1
        backing = _backing_tokens(plan.get("summary_fact_ids", []), facts_by_id)
        result = _check_field("summary", summary, backing)
        if result:
            mismatches.append(result)

    changed = diagnosis.get("changed_since_last_visit")
    if isinstance(changed, str) and changed:
        fields_checked += 1
        backing = _backing_tokens(diagnosis.get("changed_since_last_visit_fact_ids", []), facts_by_id)
        result = _check_field("diagnosis.changed_since_last_visit", changed, backing)
        if result:
            mismatches.append(result)

    for section, field in _RICHNESS_CHECKS:
        items = plan.get(section, [])
        for idx, item in enumerate(items):
            _check_richness(f"{section}[{idx}].{field}", item.get(field), thin_fields)
    for idx, detail in enumerate(details):
        _check_richness(f"diagnosis.details[{idx}].description", detail.get("description"), thin_fields)

    flags = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "run_id": os.path.basename(os.path.normpath(run_dir)),
        "numeric_parity": mismatches,
        "thin_fields": thin_fields,
    }

    flags_schema = validate.load_schema("flags")
    flags_errors = validate.validate(flags, flags_schema)
    if flags_errors:
        print(
            "numeric_parity: internal bug -- flags do not match "
            "flags.schema.json:",
            file=sys.stderr,
        )
        for error in flags_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    out_path = os.path.join(run_dir, "03_flags.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(flags, f, indent=2, sort_keys=False)
        f.write("\n")

    checks = {
        "fields_checked": fields_checked,
        "numeric_mismatches": len(mismatches),
        "thin_fields": len(thin_fields),
    }
    runlog.record(run_dir, "numeric_parity", "ok", checks=checks)

    print(f"OK wrote {out_path} ({len(mismatches)} numeric mismatch(es), {len(thin_fields)} thin field(s))")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Numeric-parity and thin-field hints for the assembled care plan."
    )
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return _run(args.run_dir)


if __name__ == "__main__":
    sys.exit(main())
