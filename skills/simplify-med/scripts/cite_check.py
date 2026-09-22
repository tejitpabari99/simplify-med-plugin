#!/usr/bin/env python3
"""Citation guard for the assemble path.

Default mode validates the assemble agent's raw output
(``03_plan.raw.json``) against ``care_plan_agent.schema.json``, then applies
a set of deterministic guards -- ported from simplify-med's
``_verify_assembly`` (``backend/care_plan/pipeline.py``) -- that drop or
repair anything the agent asserted without a fact behind it, and writes
``03_plan.draft.json``.

``--additions`` mode does the analogous job for the assemble-missing agent's
output (``05_additions.raw.json``): every addition must cite only facts
listed as missing in ``04_coverage.json``, or it is dropped.

Stdlib only. Runnable as ``python3 cite_check.py --run-dir D [--additions]``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402
import runlog  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


# Sections that are flat top-level arrays of items on the care plan (agent)
# schema, each item carrying its own `source_fact_ids`.
ITEM_LIST_FIELDS = (
    "reason_for_visit", "medications", "tests", "procedures",
    "other", "follow_up", "warning_signs",
)
# The NOT STATED rule (assemble.md) applies `why` only to these four.
WHY_FIELDS = ("medications", "tests", "procedures", "other")
# STATUS is required (never null) on these five.
STATUS_REQUIRED_FIELDS = ("medications", "tests", "procedures", "other", "follow_up")
SEVERITY_ENUM = {"high", "medium", "low"}
URGENCY_ENUM = {"emergency", "call_doctor", "monitor", "normal_side_effect"}

# additions_raw.schema.json / additions.schema.json use the same item shapes
# as the care plan, but `diagnosis` is flattened to a top-level
# `diagnosis_details` array (no `changed_since_last_visit`).
ADDITIONS_ITEM_FIELDS = (
    "reason_for_visit", "diagnosis_details", "medications", "tests",
    "procedures", "other", "follow_up", "warning_signs",
)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


def _run_id(run_dir: str) -> str:
    return os.path.basename(os.path.normpath(run_dir))


def _load_valid_fact_ids(run_dir: str) -> set[int]:
    facts_path = os.path.join(run_dir, "02_facts.json")
    data = _read_json(facts_path)
    return {fact["id"] for fact in data.get("facts", [])}


def _filter_source_fact_ids(item: dict, valid_ids: set[int]) -> tuple[dict, bool]:
    """Drop any `source_fact_ids` entry not in `valid_ids`. Returns the
    (possibly copied) item and whether every id was dropped (nothing
    survives to back this item's claim)."""
    original = item.get("source_fact_ids", [])
    cited = [i for i in original if i in valid_ids]
    if cited != original:
        item = dict(item)
        item["source_fact_ids"] = cited
    return item, (len(cited) == 0)


def _null_empty_why(item: dict) -> dict:
    if item.get("why", None) == "":
        item = dict(item)
        item["why"] = None
    return item


def _fix_enum(item: dict, key: str, enum: set[str]) -> dict:
    value = item.get(key)
    if value is not None and value not in enum:
        item = dict(item)
        item[key] = None
    return item


def _default_status(item: dict) -> tuple[dict, bool]:
    if item.get("status") is None:
        item = dict(item)
        item["status"] = "to_do"
        return item, True
    return item, False


def _fatal(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _apply_guards(raw: dict, valid_ids: set[int]) -> tuple[dict, dict]:
    """The deterministic guards from ``_verify_assembly``, as a pure
    function: `raw` in, `(guarded_plan, checks)` out. No file I/O, no schema
    validation -- kept separate from `_run_assemble` so it can be unit
    tested directly against inputs the care_plan_agent schema's own
    structural constraints (`questions` maxItems 3, required `status`,
    restricted `severity`/`urgency` enums) would otherwise reject before a
    guard ever ran on them in the full CLI flow."""
    plan = dict(raw)

    items_in = 0
    items_kept = 0
    dropped_uncited_by_section: dict[str, int] = {}
    why_nulled = 0
    status_defaulted = 0

    # (1) questions truncated to 3
    questions = plan.get("questions", [])
    questions_truncated = len(questions) > 3
    plan["questions"] = questions[:3]

    # (2) summary_fact_ids filtered; summary text kept even if uncited
    summary = plan.get("summary", "")
    summary_fact_ids = plan.get("summary_fact_ids", [])
    cited_summary_ids = [i for i in summary_fact_ids if i in valid_ids]
    summary_uncited = bool(summary) and bool(summary_fact_ids) and not cited_summary_ids
    plan["summary_fact_ids"] = cited_summary_ids

    # (3) + (5) + (6) + (7) over the flat item-list sections
    for field in ITEM_LIST_FIELDS:
        items = plan.get(field, [])
        items_in += len(items)
        kept = []
        for item in items:
            item, all_dropped = _filter_source_fact_ids(item, valid_ids)
            if all_dropped:
                dropped_uncited_by_section[field] = dropped_uncited_by_section.get(field, 0) + 1
                continue
            if field in WHY_FIELDS:
                before = item.get("why", None)
                item = _null_empty_why(item)
                if before == "" and item.get("why") is None:
                    why_nulled += 1
            if field == "warning_signs":
                item = _fix_enum(item, "urgency", URGENCY_ENUM)
            if field in STATUS_REQUIRED_FIELDS:
                item, defaulted = _default_status(item)
                if defaulted:
                    status_defaulted += 1
            kept.append(item)
        plan[field] = kept
        items_kept += len(kept)

    # diagnosis.details is the one nested item container
    diagnosis = dict(plan.get("diagnosis", {}))
    details = diagnosis.get("details", [])
    items_in += len(details)
    kept_details = []
    for detail in details:
        detail, all_dropped = _filter_source_fact_ids(detail, valid_ids)
        if all_dropped:
            dropped_uncited_by_section["diagnosis"] = dropped_uncited_by_section.get("diagnosis", 0) + 1
            continue
        detail = _fix_enum(detail, "severity", SEVERITY_ENUM)
        kept_details.append(detail)
    diagnosis["details"] = kept_details
    items_kept += len(kept_details)

    # (4) changed_since_last_visit_fact_ids filtered
    changed = diagnosis.get("changed_since_last_visit", "")
    changed_ids = diagnosis.get("changed_since_last_visit_fact_ids", [])
    cited_changed_ids = [i for i in changed_ids if i in valid_ids]
    if changed and changed_ids and not cited_changed_ids:
        diagnosis["changed_since_last_visit"] = ""
        diagnosis["changed_since_last_visit_fact_ids"] = []
    else:
        diagnosis["changed_since_last_visit_fact_ids"] = cited_changed_ids
    plan["diagnosis"] = diagnosis

    checks = {
        "items_in": items_in,
        "items_kept": items_kept,
        "dropped_uncited_by_section": dropped_uncited_by_section,
        "questions_truncated": questions_truncated,
        "summary_uncited": summary_uncited,
        "why_nulled": why_nulled,
        "status_defaulted": status_defaulted,
    }
    return plan, checks


# --- assemble mode -----------------------------------------------------

def _run_assemble(run_dir: str) -> int:
    raw_path = os.path.join(run_dir, "03_plan.raw.json")
    if not os.path.isfile(raw_path):
        return _fatal(
            "cite_check: could not find 03_plan.raw.json in the run directory. "
            "The assemble agent must write this file before cite_check can run."
        )
    try:
        raw = _read_json(raw_path)
    except json.JSONDecodeError as exc:
        return _fatal(f"cite_check: 03_plan.raw.json is not valid JSON ({exc}).")

    agent_schema = validate.load_schema("care_plan_agent")
    schema_errors = validate.validate(raw, agent_schema)
    if schema_errors:
        print(
            "cite_check: 03_plan.raw.json does not match care_plan_agent.schema.json. "
            "The assemble agent should be retried with these errors:",
            file=sys.stderr,
        )
        for error in schema_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    valid_ids = _load_valid_fact_ids(run_dir)
    plan, guard_checks = _apply_guards(raw, valid_ids)
    items_kept = guard_checks["items_kept"]
    dropped_uncited_by_section = guard_checks["dropped_uncited_by_section"]

    run_id = _run_id(run_dir)
    plugin_version = runlog.plugin_version()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    plan["schema_version"] = SCHEMA_VERSION
    plan["plugin_version"] = plugin_version
    plan["meta"] = {
        "run_id": run_id,
        "plugin_version": plugin_version,
        "schema_version": SCHEMA_VERSION,
        "level": "standard",
        "created_at": created_at,
    }
    plan["notices"] = []
    plan["terms"] = {}

    care_plan_schema = validate.load_schema("care_plan")
    plan_errors = validate.validate(plan, care_plan_schema)
    if plan_errors:
        print(
            "cite_check: internal bug -- the guarded plan does not match "
            "care_plan.schema.json (this is a bug in cite_check.py, not in "
            "the assemble agent's output):",
            file=sys.stderr,
        )
        for error in plan_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    _write_json(draft_path, plan)

    status = "degraded" if dropped_uncited_by_section else "ok"
    runlog.record(run_dir, "assemble", status, checks=guard_checks)

    print(f"OK wrote {draft_path} ({items_kept}/{guard_checks['items_in']} items kept)")
    return 0


# --- additions mode ------------------------------------------------------

def _empty_additions(run_dir: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "run_id": _run_id(run_dir),
        "reason_for_visit": [],
        "diagnosis_details": [],
        "medications": [],
        "tests": [],
        "procedures": [],
        "other": [],
        "follow_up": [],
        "warning_signs": [],
        "low_priority": [],
        "dropped": [],
    }


def _run_additions(run_dir: str) -> int:
    raw_path = os.path.join(run_dir, "05_additions.raw.json")
    out_path = os.path.join(run_dir, "05_additions.json")

    if not os.path.isfile(raw_path):
        _write_json(out_path, _empty_additions(run_dir))
        runlog.record(
            run_dir, "assemble_missing", "skipped",
            checks={"items_in": 0, "items_kept": 0, "dropped_not_missing": 0, "dropped_uncited": 0},
        )
        print(f"OK skipped (no 05_additions.raw.json found); wrote empty {out_path}")
        return 0

    try:
        raw = _read_json(raw_path)
    except json.JSONDecodeError as exc:
        return _fatal(f"cite_check --additions: 05_additions.raw.json is not valid JSON ({exc}).")

    raw_schema = validate.load_schema("additions_raw")
    schema_errors = validate.validate(raw, raw_schema)
    if schema_errors:
        print(
            "cite_check --additions: 05_additions.raw.json does not match "
            "additions_raw.schema.json. The assemble-missing agent should be "
            "retried with these errors:",
            file=sys.stderr,
        )
        for error in schema_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    valid_ids = _load_valid_fact_ids(run_dir)
    coverage_path = os.path.join(run_dir, "04_coverage.json")
    if not os.path.isfile(coverage_path):
        return _fatal(
            "cite_check --additions: could not find 04_coverage.json in the "
            "run directory. review-coverage and sanitize_review must run before "
            "cite_check --additions."
        )
    coverage = _read_json(coverage_path)
    missing = set(coverage.get("missing", []))

    result = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "run_id": _run_id(run_dir),
    }

    items_in = 0
    items_kept = 0
    dropped_not_missing = 0
    dropped_uncited = 0
    dropped_log: list[dict] = []

    for field in ADDITIONS_ITEM_FIELDS:
        items = raw.get(field, [])
        items_in += len(items)
        kept = []
        for item in items:
            item, all_dropped = _filter_source_fact_ids(item, valid_ids)
            cited = set(item.get("source_fact_ids", []))
            if all_dropped or not cited:
                dropped_uncited += 1
                dropped_log.append({"item": item, "reason": "uncited"})
                continue
            if not cited.issubset(missing):
                dropped_not_missing += 1
                dropped_log.append({"item": item, "reason": "not_missing"})
                continue
            if field in WHY_FIELDS:
                item = _null_empty_why(item)
            if field == "diagnosis_details":
                item = _fix_enum(item, "severity", SEVERITY_ENUM)
            if field == "warning_signs":
                item = _fix_enum(item, "urgency", URGENCY_ENUM)
            if field in STATUS_REQUIRED_FIELDS:
                item, _defaulted = _default_status(item)
            kept.append(item)
        result[field] = kept
        items_kept += len(kept)

    result["low_priority"] = raw.get("low_priority", [])
    result["dropped"] = dropped_log

    additions_schema = validate.load_schema("additions")
    result_errors = validate.validate(result, additions_schema)
    if result_errors:
        print(
            "cite_check --additions: internal bug -- the guarded additions do "
            "not match additions.schema.json (this is a bug in cite_check.py, "
            "not in the assemble-missing agent's output):",
            file=sys.stderr,
        )
        for error in result_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    _write_json(out_path, result)

    checks = {
        "items_in": items_in,
        "items_kept": items_kept,
        "dropped_not_missing": dropped_not_missing,
        "dropped_uncited": dropped_uncited,
    }
    status = "ok" if (dropped_not_missing == 0 and dropped_uncited == 0) else "degraded"
    runlog.record(run_dir, "assemble_missing", status, checks=checks)

    print(f"OK wrote {out_path} ({items_kept}/{items_in} items kept)")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Citation guard for assembled care-plan items (or their additions)."
    )
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument(
        "--additions", action="store_true",
        help="Guard 05_additions.raw.json against 04_coverage.json's missing list, "
             "instead of guarding 03_plan.raw.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.additions:
        return _run_additions(args.run_dir)
    return _run_assemble(args.run_dir)


if __name__ == "__main__":
    sys.exit(main())
