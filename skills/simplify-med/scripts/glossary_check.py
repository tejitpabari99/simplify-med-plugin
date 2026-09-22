#!/usr/bin/env python3
"""Filter a glossary agent's raw term proposals down to a clean glossary.

CLI: python3 glossary_check.py --run-dir D

Validates 02_glossary.raw.json against glossary_raw.schema.json first
(schema errors -> print and exit 1, the orchestrator's retry signal).
Then drops terms whose matched_term cannot be found (normalized
substring) in any unit's text, terms with an empty definition, and exact
duplicates (by normalized matched_term); caps the survivors at 25 in file
order; forces `source: "llm_proposed"`; writes 02_glossary.json.

Never fatal: a missing raw file yields an empty glossary, status
"skipped", exit 0. Stdlib only. Importable as `glossary_check`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runlog  # noqa: E402
import textnorm  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402

_CAP = 25


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Filter and cap a glossary agent's raw proposals")
    parser.add_argument("--run-dir", required=True)
    return parser


def _write_glossary(run_dir: str, run_id: str, terms: list) -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "terms": terms,
    }
    path = os.path.join(run_dir, "02_glossary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir
    run_id = os.path.basename(os.path.normpath(run_dir))

    raw_path = os.path.join(run_dir, "02_glossary.raw.json")
    if not os.path.isfile(raw_path):
        _write_glossary(run_dir, run_id, [])
        runlog.record(run_dir, "glossary", "skipped", checks={
            "terms_in": 0, "terms_kept": 0,
            "dropped_not_in_source": 0, "dropped_duplicate": 0, "dropped_cap": 0,
        })
        return 0

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_doc = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {raw_path!r}: {exc}")
        return 1

    schema = validate.load_schema("glossary_raw")
    errors = validate.validate(raw_doc, schema)
    if errors:
        for error in errors:
            print(error)
        return 1

    units_path = os.path.join(run_dir, "01_units.json")
    try:
        with open(units_path, "r", encoding="utf-8") as f:
            units_doc = json.load(f)
    except OSError as exc:
        print(
            f"glossary_check could not read {units_path!r}: {exc}. "
            "The glossary cannot be checked against the source document without it.",
            file=sys.stderr,
        )
        return 1

    unit_texts = [u.get("text", "") for u in units_doc.get("units", [])]
    normalized_unit_texts = [textnorm.normalize_text(t) for t in unit_texts]

    raw_terms = raw_doc.get("terms", [])
    terms_in = len(raw_terms)

    dropped_not_in_source = 0
    dropped_duplicate = 0
    dropped_empty_definition = 0
    seen_matched: set = set()
    survivors: list[dict] = []

    for term in raw_terms:
        definition = (term.get("definition") or "").strip()
        if not definition:
            dropped_empty_definition += 1
            continue

        matched_term = term.get("matched_term", "")
        normalized_matched = textnorm.normalize_text(matched_term)
        if not normalized_matched or not any(
            normalized_matched in unit_text for unit_text in normalized_unit_texts
        ):
            dropped_not_in_source += 1
            continue

        if normalized_matched in seen_matched:
            dropped_duplicate += 1
            continue
        seen_matched.add(normalized_matched)

        survivors.append({
            "term": term.get("term", matched_term),
            "matched_term": matched_term,
            "definition": term.get("definition", ""),
            "source": "llm_proposed",
        })

    dropped_cap = max(0, len(survivors) - _CAP)
    kept_terms = survivors[:_CAP]

    _write_glossary(run_dir, run_id, kept_terms)

    checks = {
        "terms_in": terms_in,
        "terms_kept": len(kept_terms),
        "dropped_not_in_source": dropped_not_in_source,
        "dropped_duplicate": dropped_duplicate,
        "dropped_cap": dropped_cap,
        "dropped_empty_definition": dropped_empty_definition,
    }
    status = "ok" if (dropped_not_in_source == 0 and dropped_duplicate == 0
                       and dropped_cap == 0 and dropped_empty_definition == 0) else "degraded"
    runlog.record(run_dir, "glossary", status, checks=checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
