#!/usr/bin/env python3
"""Deterministic post-validation of the two review agents' raw output.

CLI: python3 sanitize_review.py --run-dir D [--only review|coverage]

Two independent jobs, each tolerant of the other's raw file being absent:

- review: validates 04_review.raw.json against review_raw.schema.json,
  drops corrections that are unresolvable / out of scope / malformed (ported
  from simplify-med's pipeline._sanitize_review_result), dedupes identical
  corrections, and lets a "remove" win over a "correct"/"not_stated" on the
  same array item. Writes 04_review.json (review.schema.json). Records the
  "review_fidelity" stage.
- coverage: validates 04_coverage.raw.json against coverage_raw.schema.json,
  drops entries citing an unknown fact id, backfills every fact id the
  agent's coverage walk omitted as present=false, and writes 04_coverage.json
  (coverage.schema.json) with a `missing` list. Records the "review_coverage"
  stage.

Exit codes: 1 only when a raw file that IS present fails its own schema
(the orchestrator's retry signal for that stage); 0 otherwise, including
when a raw file is simply absent (that side is recorded "skipped").

Stdlib only. Importable as `sanitize_review`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


# Path addressing shared with diff_guard.py -- dotted keys, "[N]" indices.
_PATH_SEGMENT_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)(\[(\d+)\])?")

_WHY_PATH_RE = re.compile(r"^(medications|tests|procedures|other)\[\d+\]\.why$")


def resolve_path(root: dict, path: str):
    """Walk `path` into `root`. Returns (found, value); found=False for an
    out-of-range index, an unknown field name, or a malformed segment."""
    node = root
    for segment in path.split("."):
        m = _PATH_SEGMENT_RE.fullmatch(segment)
        if not m:
            return False, None
        name, _, idx = m.groups()
        if not isinstance(node, dict) or name not in node:
            return False, None
        node = node[name]
        if idx is not None:
            i = int(idx)
            if not isinstance(node, list) or i >= len(node):
                return False, None
            node = node[i]
    return True, node


def _targets_removed_item(path: str, removed_items: set) -> bool:
    """True if `path` names one of `removed_items` itself, or a field
    nested under one -- a boundary match on "." or "[", not a plain
    prefix match (so "diagnosis.details[1]" never matches a removed
    "diagnosis.details[10]")."""
    return any(
        path == removed or path.startswith(removed + ".") or path.startswith(removed + "[")
        for removed in removed_items
    )


def _correction_key(c: dict):
    return (c.get("op"), c.get("path"), c.get("value"))


def sanitize_corrections(corrections: list, plan_dict: dict):
    """Returns (kept, dropped) where dropped is a list of
    {"correction": c, "reason": str}."""
    kept: list = []
    dropped: list = []

    seen_keys = set()
    for c in corrections:
        op = c.get("op")
        path = c.get("path")
        value = c.get("value")

        found, _ = resolve_path(plan_dict, path) if isinstance(path, str) else (False, None)
        if not found:
            dropped.append({"correction": c, "reason": "unresolvable_path"})
            continue

        if op == "not_stated" and not _WHY_PATH_RE.match(path):
            dropped.append({"correction": c, "reason": "not_stated_outside_why"})
            continue

        if op == "correct" and not value:
            dropped.append({"correction": c, "reason": "correct_without_value"})
            continue

        if path == "summary" and op in ("correct", "not_stated"):
            dropped.append({"correction": c, "reason": "summary_only_remove"})
            continue

        key = _correction_key(c)
        if key in seen_keys:
            dropped.append({"correction": c, "reason": "duplicate"})
            continue
        seen_keys.add(key)

        kept.append(c)

    # "remove" wins over a "correct"/"not_stated" targeting the same item.
    removed_items = {c["path"] for c in kept if c.get("op") == "remove"}
    final_kept = []
    for c in kept:
        if c.get("op") != "remove" and _targets_removed_item(c.get("path"), removed_items):
            dropped.append({"correction": c, "reason": "removed_item"})
            continue
        final_kept.append(c)

    return final_kept, dropped


def process_review(run_dir: str, run_id: str) -> bool:
    """Returns True unless a present raw file failed its own schema."""
    raw_path = os.path.join(run_dir, "04_review.raw.json")
    out_path = os.path.join(run_dir, "04_review.json")

    if not os.path.isfile(raw_path):
        doc = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "run_id": run_id,
            "verdict": "pass",
            "corrections": [],
            "dropped": [],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        runlog.record(run_dir, "review_fidelity", "skipped", checks={
            "verdict": "pass", "corrections_in": 0, "corrections_kept": 0, "dropped_by_reason": {},
        })
        return True

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_doc = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"04_review.raw.json is not valid JSON: {exc}")
        runlog.record(run_dir, "review_fidelity", "failed", checks={"schema_errors": [str(exc)]})
        return False

    schema_errors = validate.validate(raw_doc, validate.load_schema("review_raw"))
    if schema_errors:
        for error in schema_errors:
            print(error)
        runlog.record(run_dir, "review_fidelity", "failed", checks={"schema_errors": schema_errors})
        return False

    plan_path = os.path.join(run_dir, "03_plan.draft.json")
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_dict = json.load(f)

    corrections_in = raw_doc.get("corrections", [])
    kept, dropped = sanitize_corrections(corrections_in, plan_dict)

    dropped_by_reason: dict = {}
    for d in dropped:
        dropped_by_reason[d["reason"]] = dropped_by_reason.get(d["reason"], 0) + 1

    doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "verdict": raw_doc.get("verdict", "pass"),
        "corrections": kept,
        "dropped": dropped,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")

    runlog.record(run_dir, "review_fidelity", "ok", checks={
        "verdict": doc["verdict"],
        "corrections_in": len(corrections_in),
        "corrections_kept": len(kept),
        "dropped_by_reason": dropped_by_reason,
    })
    return True


def process_coverage(run_dir: str, run_id: str) -> bool:
    """Returns True unless a present raw file failed its own schema."""
    raw_path = os.path.join(run_dir, "04_coverage.raw.json")
    out_path = os.path.join(run_dir, "04_coverage.json")

    if not os.path.isfile(raw_path):
        doc = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "run_id": run_id,
            "coverage": [],
            "missing": [],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        runlog.record(run_dir, "review_coverage", "skipped", checks={
            "facts": 0, "present": 0, "missing": 0, "backfilled": 0, "unknown_dropped": 0,
        })
        return True

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_doc = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"04_coverage.raw.json is not valid JSON: {exc}")
        runlog.record(run_dir, "review_coverage", "failed", checks={"schema_errors": [str(exc)]})
        return False

    schema_errors = validate.validate(raw_doc, validate.load_schema("coverage_raw"))
    if schema_errors:
        for error in schema_errors:
            print(error)
        runlog.record(run_dir, "review_coverage", "failed", checks={"schema_errors": schema_errors})
        return False

    facts_path = os.path.join(run_dir, "02_facts.json")
    with open(facts_path, "r", encoding="utf-8") as f:
        facts_doc = json.load(f)
    fact_ids = sorted({f["id"] for f in facts_doc.get("facts", [])})
    fact_id_set = set(fact_ids)

    present_by_id: dict = {}
    unknown_dropped = 0
    for entry in raw_doc.get("coverage", []):
        fact_id = entry.get("fact_id")
        if fact_id not in fact_id_set:
            unknown_dropped += 1
            continue
        present_by_id[fact_id] = bool(entry.get("present"))

    backfilled = 0
    for fact_id in fact_ids:
        if fact_id not in present_by_id:
            present_by_id[fact_id] = False
            backfilled += 1

    coverage = [{"fact_id": fid, "present": present_by_id[fid]} for fid in fact_ids]
    missing = [fid for fid in fact_ids if not present_by_id[fid]]
    present_count = len(fact_ids) - len(missing)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "coverage": coverage,
        "missing": missing,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")

    runlog.record(run_dir, "review_coverage", "ok", checks={
        "facts": len(fact_ids),
        "present": present_count,
        "missing": len(missing),
        "backfilled": backfilled,
        "unknown_dropped": unknown_dropped,
    })
    return True


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sanitize the review-fidelity and review-coverage agents' raw output")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--only", choices=["review", "coverage"], default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir
    run_id = os.path.basename(os.path.normpath(run_dir))

    ok = True
    if args.only in (None, "review"):
        ok = process_review(run_dir, run_id) and ok
    if args.only in (None, "coverage"):
        ok = process_coverage(run_dir, run_id) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
