#!/usr/bin/env python3
"""Validate an optional post-finalization glossary against visible report text."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plan_view  # noqa: E402
import runlog  # noqa: E402
import textnorm  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402

_CAP = 5


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an optional glossary after finalization")
    parser.add_argument("--run-dir", required=True)
    return parser


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"{os.path.basename(path)} must contain a JSON object")
    return document


def _write_glossary(run_dir: str, run_id: str, terms: list) -> None:
    document = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "terms": terms,
    }
    descriptor, temporary_path = tempfile.mkstemp(prefix=".glossary.", suffix=".tmp", dir=run_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, os.path.join(run_dir, "07_glossary.json"))
    except BaseException:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def _load_finalized_plan(run_dir: str) -> tuple[dict, str]:
    plan_path = os.path.join(run_dir, "06_plan.final.json")
    plan = _read_json(plan_path)
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("optional glossary generation requires a completed schema-v2 final report")
    run_id = (plan.get("meta") or {}).get("run_id")
    if not run_id:
        raise ValueError("06_plan.final.json is missing its run identity")
    run_log = _read_json(os.path.join(run_dir, "run.json"))
    if run_log.get("run_id") != run_id:
        raise ValueError("run.json does not belong to 06_plan.final.json")
    if ((run_log.get("stages") or {}).get("finalize") or {}).get("status") != "ok":
        raise ValueError("optional glossary generation requires successful finalization")
    return plan, run_id


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    run_dir = args.run_dir
    try:
        plan, run_id = _load_finalized_plan(run_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"glossary_check: {error}", file=sys.stderr)
        return 1

    raw_path = os.path.join(run_dir, "07_glossary.raw.json")
    if not os.path.isfile(raw_path):
        _write_glossary(run_dir, run_id, [])
        runlog.record(
            run_dir,
            "glossary",
            "skipped",
            checks={
                "terms_in": 0,
                "terms_kept": 0,
                "dropped_not_visible": 0,
                "dropped_duplicate": 0,
                "dropped_cap": 0,
                "dropped_empty_definition": 0,
            },
            artifacts=["07_glossary.json"],
            skip_reason="no glossary proposals were requested",
            run_id=run_id,
        )
        print("glossary: skipped | terms_in=0 terms_kept=0")
        return 0

    try:
        raw_document = _read_json(raw_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"glossary_check: {error}", file=sys.stderr)
        return 1

    errors = validate.validate(raw_document, validate.load_schema("glossary_raw"))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    visible_text = textnorm.normalize_text(plan_view.visible_text(plan))
    raw_terms = raw_document.get("terms", [])
    dropped_not_visible = 0
    dropped_duplicate = 0
    dropped_empty_definition = 0
    seen_matched = set()
    survivors = []

    for term in raw_terms:
        definition = (term.get("definition") or "").strip()
        if not definition:
            dropped_empty_definition += 1
            continue
        matched_term = term.get("matched_term", "")
        normalized_matched = textnorm.normalize_text(matched_term)
        if not normalized_matched or normalized_matched not in visible_text:
            dropped_not_visible += 1
            continue
        if normalized_matched in seen_matched:
            dropped_duplicate += 1
            continue
        seen_matched.add(normalized_matched)
        survivors.append({
            "term": term.get("term", matched_term),
            "matched_term": matched_term,
            "definition": definition,
            "source": "llm_proposed",
        })

    dropped_cap = max(0, len(survivors) - _CAP)
    kept_terms = survivors[:_CAP]
    _write_glossary(run_dir, run_id, kept_terms)

    checks = {
        "terms_in": len(raw_terms),
        "terms_kept": len(kept_terms),
        "dropped_not_visible": dropped_not_visible,
        "dropped_duplicate": dropped_duplicate,
        "dropped_cap": dropped_cap,
        "dropped_empty_definition": dropped_empty_definition,
    }
    status = "ok" if all(value == 0 for key, value in checks.items() if key.startswith("dropped_")) else "degraded"
    runlog.record(
        run_dir,
        "glossary",
        status,
        checks=checks,
        artifacts=["07_glossary.raw.json", "07_glossary.json"],
        run_id=run_id,
    )
    print(f"glossary: {status} | terms_in={len(raw_terms)} terms_kept={len(kept_terms)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
