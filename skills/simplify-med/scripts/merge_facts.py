#!/usr/bin/env python3
"""Merge every chunk's raw facts into one verified, renumbered ledger.

CLI: python3 merge_facts.py --run-dir D

Reads 01_units.json and every 02_facts.<k>.raw.json (ascending k, starting
at 1) it finds contiguously from chunk 1 up to the highest chunk number
referenced in 01_units.json's `chunks`. Runs anchor_check.check_fact on
every fact, keeps survivors, drops the rest (recorded), deduplicates exact
repeats, and writes 02_facts.json + 02_facts.txt.

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

    units_path = os.path.join(run_dir, "01_units.json")
    with open(units_path, "r", encoding="utf-8") as f:
        units_doc = json.load(f)
    units_by_id = {u["id"]: u for u in units_doc.get("units", [])}
    chunks_meta = units_doc.get("chunks", [])
    chunks_expected = len(chunks_meta)

    run_id = os.path.basename(os.path.normpath(run_dir))

    facts_raw_schema = validate.load_schema("facts_raw")

    kept: list[dict] = []
    dropped: list[dict] = []
    dropped_by_reason: dict = {}
    missing_chunks: list[int] = []
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
        except json.JSONDecodeError:
            missing_chunks.append(k)
            continue

        schema_errors = validate.validate(raw_doc, facts_raw_schema)
        if schema_errors:
            missing_chunks.append(k)
            continue

        raw_facts = raw_doc.get("facts", [])
        for raw_fact in raw_facts:
            facts_in += 1
            ok, reason, char_start, char_end = anchor_check.check_fact(raw_fact, units_by_id)
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
        runlog.record(run_dir, "ground", "failed", checks={"schema_errors": facts_errors})
        print(
            "merge_facts produced a facts document that failed its own schema; this is a bug in merge_facts.py.",
            file=sys.stderr,
        )
        return 1

    facts_path = os.path.join(run_dir, "02_facts.json")
    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts_doc, f, indent=2)
        f.write("\n")

    txt_path = os.path.join(run_dir, "02_facts.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for fact in facts:
            f.write(f"[{fact['id']}] ({fact['category']}) {fact['text']}\n")

    checks = {
        "chunks_expected": chunks_expected,
        "chunks_found": chunks_found,
        "facts_in": facts_in,
        "facts_kept": len(facts),
        "dropped_by_reason": dropped_by_reason,
        "duplicates_removed": duplicates_removed,
        "missing_chunks": missing_chunks,
    }

    if len(facts) == 0:
        runlog.record(run_dir, "ground", "failed", checks=checks)
        print(
            "The clinical document could not be read into any verified facts. "
            "Every proposed fact either cited a line that does not exist, quoted "
            "text that could not be found verbatim, or was too short to be useful. "
            "The document may be empty, malformed, or entirely unlike a clinical note.",
            file=sys.stderr,
        )
        return 1

    status = "ok" if not dropped and not missing_chunks else "degraded"
    runlog.record(run_dir, "ground", status, checks=checks)
    print(
        f"ground: {status} | facts_in={facts_in} facts_kept={len(facts)} "
        f"dropped={len(dropped)} duplicates_removed={duplicates_removed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
