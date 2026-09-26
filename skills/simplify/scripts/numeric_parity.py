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
import hashlib
import json
import os
import re
import sys
from collections import Counter

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


def _extract_number_tokens(text: str) -> Counter[tuple[str, str]]:
    """Tokenize numbers with multiplicity while excluding dates and times."""
    excluded = _excluded_spans(text)
    tokens: Counter[tuple[str, str]] = Counter()
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
        tokens[(num_norm, unit)] += 1
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


def _backing_tokens(fact_ids, facts_by_id: dict) -> Counter[tuple[str, str]]:
    tokens: Counter[tuple[str, str]] = Counter()
    for fid in dict.fromkeys(fact_ids):
        fact = facts_by_id.get(fid)
        if fact is None:
            continue
        text_tokens = _extract_number_tokens(fact.get("text", ""))
        quote_tokens = _extract_number_tokens(fact.get("quote", ""))
        tokens.update(text_tokens | quote_tokens)
    return tokens


def _expanded_token_strings(tokens: Counter[tuple[str, str]]) -> list[str]:
    return sorted(
        _token_str(number, unit)
        for (number, unit), count in tokens.items()
        for _occurrence in range(count)
    )


def _check_field(path: str, value: str, backing: Counter[tuple[str, str]]) -> dict | None:
    if not value:
        return None
    field_tokens = _extract_number_tokens(value)
    if not field_tokens:
        return None
    if all(count <= backing[token] for token, count in field_tokens.items()):
        return None
    return {
        "path": path,
        "tokens_in_field": _expanded_token_strings(field_tokens),
        "tokens_in_facts": _expanded_token_strings(backing),
    }


def _check_richness(path: str, value, thin_fields: list[dict]) -> None:
    if isinstance(value, str) and value and not _is_informative(value):
        thin_fields.append({"path": path, "value": value})


class NumericParityError(ValueError):
    """Raised when numeric review or settled content is not exact."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _fact_list(facts: dict | list[dict]) -> list[dict]:
    value = facts.get("facts", []) if isinstance(facts, dict) else facts
    return value if isinstance(value, list) else []


def _numeric_fields(plan: dict):
    for section, field_names in _NUMERIC_PARITY_FIELDS.items():
        for index, item in enumerate(plan.get(section, [])):
            fact_ids = item.get("source_fact_ids", [])
            for field in field_names:
                value = item.get(field)
                if isinstance(value, str):
                    yield f"{section}[{index}].{field}", value, fact_ids
            if section == "other":
                for step_index, step in enumerate(item.get("steps", [])):
                    if isinstance(step, str):
                        yield f"other[{index}].steps[{step_index}]", step, fact_ids

    diagnosis = plan.get("diagnosis", {}) or {}
    for index, detail in enumerate(diagnosis.get("details", [])):
        fact_ids = detail.get("source_fact_ids", [])
        for field in _DIAGNOSIS_DETAIL_FIELDS:
            value = detail.get(field)
            if isinstance(value, str):
                yield f"diagnosis.details[{index}].{field}", value, fact_ids

    summary = plan.get("summary")
    if isinstance(summary, str):
        yield "summary", summary, plan.get("summary_fact_ids", [])
    changed = diagnosis.get("changed_since_last_visit")
    if isinstance(changed, str):
        yield (
            "diagnosis.changed_since_last_visit", changed,
            diagnosis.get("changed_since_last_visit_fact_ids", []),
        )
    for index, question in enumerate(plan.get("questions", [])):
        if not isinstance(question, dict):
            continue
        value = question.get("question")
        if isinstance(value, str):
            yield f"questions[{index}].question", value, question.get("source_fact_ids", [])


def build_numeric_flags(
    plan: dict,
    facts: dict | list[dict],
    *,
    run_id: str,
    plugin_version: str,
) -> dict:
    """Build deterministic numeric flags in memory without writing artifacts."""
    facts_by_id = {fact["id"]: fact for fact in _fact_list(facts) if isinstance(fact.get("id"), int)}
    mismatches: list[dict] = []
    for path, value, fact_ids in _numeric_fields(plan):
        mismatch = _check_field(path, value, _backing_tokens(fact_ids, facts_by_id))
        if mismatch:
            mismatches.append(mismatch)
    for mismatch in mismatches:
        identity = json.dumps(mismatch, sort_keys=True, separators=(",", ":")).encode("utf-8")
        mismatch["flag_id"] = (
            int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") & ((1 << 53) - 1)
        ) or 1

    thin_fields: list[dict] = []
    for section, field in _RICHNESS_CHECKS:
        for index, item in enumerate(plan.get(section, [])):
            _check_richness(f"{section}[{index}].{field}", item.get(field), thin_fields)
    diagnosis = plan.get("diagnosis", {}) or {}
    for index, detail in enumerate(diagnosis.get("details", [])):
        _check_richness(f"diagnosis.details[{index}].description", detail.get("description"), thin_fields)

    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "run_id": run_id,
        "numeric_parity": mismatches,
        "thin_fields": thin_fields,
    }


_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_MISSING = object()


def _get_path(document: dict, path: str):
    value = document
    for name, index in _PATH_TOKEN_RE.findall(path):
        try:
            value = value[int(index)] if index else value[name]
        except (KeyError, IndexError, TypeError, ValueError):
            return _MISSING
    return value


def _numeric_tokens_by_path(plan: dict) -> dict[str, Counter[tuple[str, str]]]:
    return {path: _extract_number_tokens(value) for path, value, _fact_ids in _numeric_fields(plan)}


def _numeric_sources_by_path(plan: dict) -> dict[str, list[int]]:
    return {path: fact_ids for path, _value, fact_ids in _numeric_fields(plan)}


def assert_post_settlement_numeric(
    draft_plan: dict,
    settled_plan: dict,
    facts: dict | list[dict],
    flags: dict,
    review: dict,
) -> dict:
    """Require exact review resolution and strict settled numeric parity."""
    errors: list[str] = []
    expected = build_numeric_flags(
        draft_plan, facts,
        run_id=flags.get("run_id", "assertion"),
        plugin_version=flags.get("plugin_version", "assertion"),
    )["numeric_parity"]
    supplied = flags.get("numeric_parity", [])
    if supplied != expected:
        errors.append("numeric flags do not match the draft plan")
    flags_by_id = {flag.get("flag_id"): flag for flag in supplied if isinstance(flag, dict)}

    resolutions = review.get("numeric_resolutions", [])
    resolution_counts: dict[int, int] = {}
    resolutions_by_id: dict[int, dict] = {}
    for resolution in resolutions:
        flag_id = resolution.get("flag_id") if isinstance(resolution, dict) else None
        if flag_id not in flags_by_id:
            errors.append(f"review resolves unknown numeric flag {flag_id}")
            continue
        resolution_counts[flag_id] = resolution_counts.get(flag_id, 0) + 1
        resolutions_by_id[flag_id] = resolution
    for flag_id in sorted(flags_by_id):
        count = resolution_counts.get(flag_id, 0)
        if count == 0:
            errors.append(f"unresolved numeric flag {flag_id}")
        elif count > 1:
            errors.append(f"numeric flag {flag_id} is resolved more than once")

    corrections = review.get("corrections", [])
    operations_by_path: dict[str, list[dict]] = {}
    for operation in corrections:
        if isinstance(operation, dict) and isinstance(operation.get("path"), str):
            operations_by_path.setdefault(operation["path"], []).append(operation)

    corrected_paths: set[str] = set()
    removed_paths: set[str] = set()
    equivalent_paths: set[str] = set()
    settled_mismatches = build_numeric_flags(
        settled_plan, facts, run_id="assertion", plugin_version="assertion",
    )["numeric_parity"]
    settled_mismatches_by_path = {flag["path"]: flag for flag in settled_mismatches}
    path_sources = _numeric_sources_by_path(draft_plan)
    facts_by_id = {
        fact["id"]: fact for fact in _fact_list(facts)
        if isinstance(fact, dict) and isinstance(fact.get("id"), int)
    }

    for flag_id, resolution in resolutions_by_id.items():
        flag = flags_by_id[flag_id]
        path = flag["path"]
        kind = resolution.get("resolution")
        operations = operations_by_path.get(path, [])
        if kind == "equivalent":
            equivalent_paths.add(path)
            if _get_path(draft_plan, path) != _get_path(settled_plan, path):
                errors.append(f"equivalent flag {flag_id} changed during settlement")
            if operations:
                errors.append(f"equivalent flag {flag_id} has a contradictory correction operation")
        elif kind == "corrected":
            corrected_paths.add(path)
            if resolution.get("correction_path") != path:
                errors.append(f"corrected flag {flag_id} must link its exact flag path")
            matching = [operation for operation in operations if operation.get("op") == "replace"]
            if len(matching) != 1 or len(operations) != 1:
                errors.append(f"corrected flag {flag_id} requires one exact replace operation")
            else:
                operation = matching[0]
                if _get_path(settled_plan, path) != operation.get("value"):
                    errors.append(f"corrected flag {flag_id} did not apply the exact replacement value")
                operation_sources = operation.get("source_fact_ids", [])
                cited_sources = set(path_sources.get(path, []))
                if not operation_sources or not set(operation_sources).issubset(cited_sources):
                    errors.append(f"corrected flag {flag_id} cites facts outside the path citations")
                if len(operation_sources) != len(set(operation_sources)):
                    errors.append(f"corrected flag {flag_id} repeats correction provenance")
                replacement = operation.get("value")
                replacement_tokens = (
                    _extract_number_tokens(replacement) if isinstance(replacement, str) else Counter()
                )
                source_tokens = _backing_tokens(operation_sources, facts_by_id)
                if not replacement_tokens or any(
                    count > source_tokens[token] for token, count in replacement_tokens.items()
                ):
                    errors.append(
                        f"corrected flag {flag_id} lacks source-supported numeric content"
                    )
            if path in settled_mismatches_by_path:
                errors.append(f"corrected flag {flag_id} remains contradictory after settlement")
        elif kind == "removed":
            removed_paths.add(path)
            if resolution.get("correction_path") != path:
                errors.append(f"removed flag {flag_id} must link its exact flag path")
            matching = [operation for operation in operations if operation.get("op") in {"clear", "remove"}]
            if len(matching) != 1 or len(operations) != 1:
                errors.append(f"removed flag {flag_id} requires one exact clear or remove operation")
            if _get_path(settled_plan, path) not in {_MISSING, None, ""}:
                errors.append(f"removed flag {flag_id} still has numeric content")
            if path in settled_mismatches_by_path:
                errors.append(f"removed flag {flag_id} remains contradictory after settlement")
        else:
            errors.append(f"numeric flag {flag_id} has invalid resolution {kind!r}")

    draft_tokens = _numeric_tokens_by_path(draft_plan)
    settled_tokens = _numeric_tokens_by_path(settled_plan)
    allowed_changed_paths = corrected_paths | removed_paths
    for path in sorted(set(draft_tokens) | set(settled_tokens)):
        if draft_tokens.get(path, Counter()) != settled_tokens.get(path, Counter()) and path not in allowed_changed_paths:
            errors.append(f"new numeric content or unnamed numeric change at {path}")

    original_by_path = {flag["path"]: flag for flag in supplied}
    for path, mismatch in settled_mismatches_by_path.items():
        if path not in equivalent_paths:
            errors.append(f"newly introduced numeric mismatch at {path}")
        else:
            original = original_by_path[path]
            if (mismatch["tokens_in_field"], mismatch["tokens_in_facts"]) != (
                original["tokens_in_field"], original["tokens_in_facts"],
            ):
                errors.append(f"equivalent flag at {path} became contradictory")

    if errors:
        raise NumericParityError(errors)
    return {
        "numeric_flags": len(flags_by_id),
        "numeric_resolutions": len(resolutions_by_id),
        "settled_mismatches": len(settled_mismatches),
    }


def _failed(run_dir: str, message: str, errors: list[str] | None = None) -> int:
    runlog.record(
        run_dir, "numeric_parity", "failed",
        checks={"validation_errors": errors or [message]},
    )
    print(message, file=sys.stderr)
    for error in errors or []:
        print(f"  {error}", file=sys.stderr)
    return 1


def _run(run_dir: str) -> int:
    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    facts_path = os.path.join(run_dir, "02_facts.json")
    out_path = os.path.join(run_dir, "03_flags.json")
    if os.path.exists(out_path):
        os.remove(out_path)

    if not os.path.isfile(draft_path):
        return _failed(
            run_dir,
            "numeric_parity: could not find 03_plan.draft.json in the run "
            "directory. cite_check must run before numeric_parity."
        )
    if not os.path.isfile(facts_path):
        return _failed(
            run_dir, "numeric_parity: could not find 02_facts.json in the run directory."
        )

    try:
        with open(draft_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except json.JSONDecodeError as exc:
        return _failed(
            run_dir, f"numeric_parity: 03_plan.draft.json is not valid JSON ({exc})."
        )
    try:
        with open(facts_path, "r", encoding="utf-8") as f:
            facts_data = json.load(f)
    except json.JSONDecodeError as exc:
        return _failed(run_dir, f"numeric_parity: 02_facts.json is not valid JSON ({exc}).")

    flags = build_numeric_flags(
        plan, facts_data, run_id=os.path.basename(os.path.normpath(run_dir)),
        plugin_version=runlog.plugin_version(),
    )
    fields_checked = sum(1 for _field in _numeric_fields(plan))
    mismatches = flags["numeric_parity"]
    thin_fields = flags["thin_fields"]

    flags_schema = validate.load_schema("flags")
    flags_errors = validate.validate(flags, flags_schema)
    if flags_errors:
        return _failed(
            run_dir,
            "numeric_parity: internal bug -- flags do not match flags.schema.json:",
            flags_errors,
        )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(flags, f, indent=2, sort_keys=False)
        f.write("\n")

    checks = {
        "fields_checked": fields_checked,
        "numeric_mismatches": len(mismatches),
        "thin_fields": len(thin_fields),
    }
    runlog.record(
        run_dir,
        "numeric_parity",
        "ok",
        checks=checks,
        artifacts=["03_flags.json"],
        run_id=os.path.basename(os.path.normpath(run_dir)),
    )

    print(f"OK wrote {out_path} ({len(mismatches)} numeric mismatch(es), {len(thin_fields)} thin field(s))")
    print(
        f"numeric_parity: ok | fields_checked={fields_checked} "
        f"numeric_mismatches={len(mismatches)} thin_fields={len(thin_fields)}"
    )
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
