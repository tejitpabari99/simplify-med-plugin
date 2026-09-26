#!/usr/bin/env python3
"""Merge every chunk's raw facts into one verified, renumbered ledger.

CLI: python3 merge_facts.py --run-dir D

Reads 01_units.json and every 02_facts.<k>.raw.json (ascending k, starting
at 1) it finds contiguously from chunk 1 up to the highest chunk number
referenced in 01_units.json's `chunks`. Runs anchor_check.check_fact on
every fact, keeps survivors, drops the rest (recorded), deduplicates exact
repeats, and writes 02_facts.json.

Stdlib only. Importable as `merge_facts`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anchor_check  # noqa: E402
import runlog  # noqa: E402
import textnorm  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge chunked raw facts into one verified ledger")
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir

    for stale_name in ("02_facts.json", "02_facts.txt"):
        stale_path = os.path.join(run_dir, stale_name)
        if os.path.exists(stale_path):
            os.remove(stale_path)

    units_path = os.path.join(run_dir, "01_units.json")
    with open(units_path, "r", encoding="utf-8") as f:
        units_doc = json.load(f)
    units_by_id = {u["id"]: u for u in units_doc.get("units", [])}
    chunks_meta = units_doc.get("chunks", [])
    chunks_expected = len(chunks_meta)

    run_id = units_doc.get("run_id")
    current_run = runlog.read(run_dir)
    if current_run and current_run.get("run_id") != run_id:
        print("01_units.json does not belong to the current run", file=sys.stderr)
        return 1

    facts_raw_schema = validate.load_schema("facts_raw")

    kept: list[dict] = []
    dropped: list[dict] = []
    dropped_by_reason: dict = {}
    missing_chunks: list[int] = []
    invalid_chunks: dict[int, list[str]] = {}
    facts_in = 0
    chunks_found = 0
    seen_dupe_keys: set = set()
    duplicates_removed = 0

    for chunk_meta in chunks_meta:
        k = chunk_meta["k"]
        raw_path = os.path.join(run_dir, f"02_facts.{k}.raw.json")
        if not os.path.isfile(raw_path):
            missing_chunks.append(k)
            continue
        chunks_found += 1

        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                raw_doc = json.load(f)
        except json.JSONDecodeError as exc:
            invalid_chunks[k] = [str(exc)]
            continue

        schema_errors = validate.validate(raw_doc, facts_raw_schema)
        if schema_errors:
            invalid_chunks[k] = schema_errors
            continue

        raw_facts = raw_doc.get("facts", [])
        chunk_units = {
            unit_id: unit
            for unit_id, unit in units_by_id.items()
            if chunk_meta["first_id"] <= unit_id <= chunk_meta["last_id"]
        }
        for raw_fact in raw_facts:
            facts_in += 1
            ok, reason, char_start, char_end = anchor_check.check_fact(raw_fact, chunk_units)
            if not ok:
                dropped.append({"chunk": k, "reason": reason, "fact": raw_fact})
                dropped_by_reason[reason] = dropped_by_reason.get(reason, 0) + 1
                continue

            dupe_key = (
                raw_fact["unit_id"],
                textnorm.normalize_text(raw_fact["quote"]),
                raw_fact["category"],
            )
            if dupe_key in seen_dupe_keys:
                duplicates_removed += 1
                continue
            seen_dupe_keys.add(dupe_key)

            kept.append({
                "chunk": k,
                "category": raw_fact["category"],
                "unit_id": raw_fact["unit_id"],
                "quote": raw_fact["quote"],
                "char_start": char_start,
                "char_end": char_end,
                "text": raw_fact["text"],
            })

    raw_artifacts = [f"02_facts.{chunk['k']}.raw.json" for chunk in chunks_meta if os.path.isfile(os.path.join(run_dir, f"02_facts.{chunk['k']}.raw.json"))]
    checks = {
        "chunks_expected": chunks_expected,
        "chunks_found": chunks_found,
        "facts_in": facts_in,
        "facts_kept": len(kept),
        "dropped_by_reason": dropped_by_reason,
        "duplicates_removed": duplicates_removed,
        "missing_chunks": missing_chunks,
        "invalid_chunks": invalid_chunks,
    }

    if missing_chunks or invalid_chunks or dropped:
        runlog.record(run_dir, "ground", "failed", checks=checks, artifacts=raw_artifacts, run_id=run_id)
        print(
            "grounding failed: every declared chunk and proposed fact must pass schema and complete-clause anchoring",
            file=sys.stderr,
        )
        return 1

    facts = []
    for i, fact in enumerate(kept, start=1):
        facts.append({
            "id": i,
            "category": fact["category"],
            "unit_id": fact["unit_id"],
            "quote": fact["quote"],
            "char_start": fact["char_start"],
            "char_end": fact["char_end"],
            "text": fact["text"],
        })

    facts_doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "facts": facts,
        "dropped": dropped,
    }

    facts_errors = validate.validate(facts_doc, validate.load_schema("facts"))
    if facts_errors:
        runlog.record(run_dir, "ground", "failed", checks={"schema_errors": facts_errors}, artifacts=raw_artifacts, run_id=run_id)
        print(
            "merge_facts produced a facts document that failed its own schema; this is a bug in merge_facts.py.",
            file=sys.stderr,
        )
        return 1

    facts_path = os.path.join(run_dir, "02_facts.json")
    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts_doc, f, indent=2)
        f.write("\n")

    if len(facts) == 0:
        runlog.record(run_dir, "ground", "failed", checks=checks, artifacts=raw_artifacts, run_id=run_id)
        os.remove(facts_path)
        print(
            "The clinical document could not be read into any verified facts. "
            "Every proposed fact either cited a line that does not exist, quoted "
            "text that could not be found verbatim, or was too short to be useful. "
            "The document may be empty, malformed, or entirely unlike a clinical note.",
            file=sys.stderr,
        )
        return 1

    checks["facts_kept"] = len(facts)
    status = "ok"
    runlog.record(
        run_dir,
        "ground",
        status,
        checks=checks,
        artifacts=raw_artifacts + ["02_facts.json"],
        run_id=run_id,
    )
    print(
        f"ground: {status} | facts_in={facts_in} facts_kept={len(facts)} "
        f"dropped={len(dropped)} duplicates_removed={duplicates_removed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
