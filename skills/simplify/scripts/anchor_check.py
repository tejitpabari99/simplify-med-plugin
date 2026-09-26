#!/usr/bin/env python3
"""Anchor check: verify a raw fact's citation against its unit's text.

Module + CLI. `check_fact(raw_fact, units_by_id)` is the deterministic
check merge_facts.py runs on every fact a ground agent proposed. The CLI
is what the orchestrator uses, after a ground agent writes
`02_facts.<k>.raw.json`, to decide whether to retry that agent (schema
errors) before merge_facts ever runs.

Stdlib only. Runnable as `python3 anchor_check.py --run-dir D --chunk K`
and importable as `anchor_check`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import textnorm  # noqa: E402
import validate  # noqa: E402

_CATEGORIES = frozenset({
    "reason_for_visit",
    "diagnosis",
    "medications",
    "tests",
    "procedures",
    "other",
    "follow_up",
    "warning_signs",
})
_CLAUSE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_LEADING_MARKER = re.compile(r"^(?:[-*•>]+|\d+[.)])\s+")


def _clause_key(text: str) -> str:
    stripped = _LEADING_MARKER.sub("", text.strip())
    return textnorm.normalize_text(stripped.rstrip(".!?;"))


def _containing_clause(unit_text: str, start: int, end: int) -> str:
    offset = 0
    for clause in _CLAUSE_BOUNDARY.split(unit_text):
        clause_start = unit_text.find(clause, offset)
        clause_end = clause_start + len(clause)
        if start >= clause_start and end <= clause_end:
            return clause
        offset = clause_end
    return unit_text


def check_fact(raw_fact: dict, units_by_id: dict) -> tuple:
    """Validate one raw fact against the units it cites.

    Returns (ok, reason, char_start, char_end). `reason` is None when
    ok is True. When ok is False, char_start/char_end are None.
    Reasons, checked in order: "unknown_unit", "empty_quote",
    "quote_not_in_unit", "uninformative_quote", "incomplete_clause",
    "bad_category".
    """
    unit_id = raw_fact.get("unit_id")
    unit = units_by_id.get(unit_id)
    if unit is None:
        return False, "unknown_unit", None, None

    quote = raw_fact.get("quote") or ""
    if not quote:
        return False, "empty_quote", None, None

    unit_text = unit.get("text", "")
    located = textnorm.find_normalized(quote, unit_text)
    if located is None:
        return False, "quote_not_in_unit", None, None

    if not textnorm.is_informative(quote):
        return False, "uninformative_quote", None, None

    char_start, char_end = located
    clause = _containing_clause(unit_text, char_start, char_end)
    if _clause_key(quote) != _clause_key(clause):
        return False, "incomplete_clause", None, None

    category = raw_fact.get("category")
    if category not in _CATEGORIES:
        return False, "bad_category", None, None

    return True, None, char_start, char_end


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and anchor-check one chunk's raw facts")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--chunk", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    raw_path = os.path.join(args.run_dir, f"02_facts.{args.chunk}.raw.json")
    if not os.path.isfile(raw_path):
        print(f"{raw_path} does not exist", file=sys.stderr)
        return 1

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_doc = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {raw_path!r}: {exc}")
        return 1

    schema = validate.load_schema("facts_raw")
    errors = validate.validate(raw_doc, schema)
    if errors:
        for error in errors:
            print(error)
        return 1

    units_path = os.path.join(args.run_dir, "01_units.json")
    with open(units_path, "r", encoding="utf-8") as f:
        units_doc = json.load(f)
    chunk_meta = next((chunk for chunk in units_doc.get("chunks", []) if chunk.get("k") == args.chunk), None)
    if chunk_meta is None:
        print(f"chunk {args.chunk} is not declared by 01_units.json", file=sys.stderr)
        return 1
    units_by_id = {
        unit["id"]: unit
        for unit in units_doc.get("units", [])
        if chunk_meta["first_id"] <= unit["id"] <= chunk_meta["last_id"]
    }

    facts = raw_doc.get("facts", [])
    ok_count = 0
    for i, raw_fact in enumerate(facts):
        ok, reason, char_start, char_end = check_fact(raw_fact, units_by_id)
        status = "ok" if ok else f"drop ({reason})"
        if ok:
            ok_count += 1
        text = raw_fact.get("text", "")
        print(f"[{i}] {status}: {text!r}")

    dropped = len(facts) - ok_count
    overall = "ok" if dropped == 0 else "failed"
    print(
        f"anchor_check: {overall} | chunk={args.chunk} facts={len(facts)} "
        f"ok={ok_count} dropped={dropped}"
    )

    return 0 if dropped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
