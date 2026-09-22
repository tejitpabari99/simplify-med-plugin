#!/usr/bin/env python3
"""Finalize a run: merge additions, re-check citations, re-detect glossary
terms, sweep for leaked PII, score readability, and render the report.

CLI: ``python3 finalize.py --run-dir D``

Preconditions: `run.json` must record `unitize`, `ground`, and `assemble`
with status other than `failed`; otherwise this exits 1 with a plain
explanation and writes nothing.

Stdlib only. Importable as `finalize`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cite_check  # noqa: E402
import plan_view  # noqa: E402
import readability  # noqa: E402
import render_html  # noqa: E402
import render_md  # noqa: E402
import runlog  # noqa: E402
import textnorm  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402

_REQUIRED_STAGES = ("unitize", "ground", "assemble")

_DRAFT_FALLBACK_NOTICE = "We could not run every check on this summary."
_GENERIC_VERIFY_NOTICE = (
    "We could not fully verify every part of this summary against your "
    "document. Please compare important details, like medicine doses and "
    "dates, with your original paperwork."
)

# PII sweep, bounded on purpose (it is not a name detector): "Dr./Doctor
# <Name>" and "<Name>, MD/DO/NP/PA/RN" both become "your doctor".
_PII_HONORIFIC_RE = re.compile(r"\b(?:Dr\.?|Doctor)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")
_PII_CREDENTIAL_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+,?\s+(?:MD|DO|NP|PA|RN)\b")

# field used to detect an "exact duplicate" addition, per plan section.
_DUP_KEY_FIELD = {
    "diagnosis_details": "title",
    "reason_for_visit": "reason",
    "medications": "title",
    "tests": "title",
    "procedures": "title",
    "other": "title",
    "follow_up": "time_frame",
    "warning_signs": "symptom",
}
_ADDITIONS_TO_PLAN_FIELD = {
    "diagnosis_details": None,  # special-cased: goes to diagnosis.details
    "reason_for_visit": "reason_for_visit",
    "medications": "medications",
    "tests": "tests",
    "procedures": "procedures",
    "other": "other",
    "follow_up": "follow_up",
    "warning_signs": "warning_signs",
}


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _check_preconditions(run_dir: str) -> str | None:
    run_log = runlog.read(run_dir)
    stages = run_log.get("stages", {})
    missing = [s for s in _REQUIRED_STAGES if s not in stages]
    failed = [s for s in _REQUIRED_STAGES if s in stages and stages[s].get("status") == "failed"]
    if not missing and not failed:
        return None
    parts = []
    if missing:
        parts.append("missing stage record(s): " + ", ".join(missing))
    if failed:
        parts.append("failed stage(s): " + ", ".join(failed))
    return (
        "finalize: cannot produce a report -- " + "; ".join(parts) + ". "
        "Unitize, ground, and assemble must all have run and not failed."
    )


def _load_plan(run_dir: str):
    corrected_path = os.path.join(run_dir, "05_plan.corrected.json")
    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    if os.path.isfile(corrected_path):
        return _read_json(corrected_path), "corrected"
    if os.path.isfile(draft_path):
        return _read_json(draft_path), "draft"
    return None, None


def _dup_key(item: dict, key_field: str | None):
    ids = frozenset(item.get("source_fact_ids", []) or [])
    value = item.get(key_field, "") if key_field else ""
    return (ids, value)


def _merge_additions(plan: dict, run_dir: str) -> int:
    additions_path = os.path.join(run_dir, "05_additions.json")
    if not os.path.isfile(additions_path):
        return 0
    additions = _read_json(additions_path)
    merged = 0

    existing_details = plan.setdefault("diagnosis", {}).setdefault("details", [])
    seen = {_dup_key(d, "title") for d in existing_details}
    for d in additions.get("diagnosis_details", []) or []:
        key = _dup_key(d, "title")
        if key in seen:
            continue
        existing_details.append(d)
        seen.add(key)
        merged += 1

    for field, key_field in _DUP_KEY_FIELD.items():
        plan_field = _ADDITIONS_TO_PLAN_FIELD[field]
        if plan_field is None:
            continue
        existing_list = plan.setdefault(plan_field, [])
        seen = {_dup_key(item, key_field) for item in existing_list}
        for item in additions.get(field, []) or []:
            key = _dup_key(item, key_field)
            if key in seen:
                continue
            existing_list.append(item)
            seen.add(key)
            merged += 1

    existing_low = plan.setdefault("low_priority", [])
    for text in additions.get("low_priority", []) or []:
        if text in existing_low:
            continue
        existing_low.append(text)
        merged += 1

    return merged


def _apply_citation_guard(plan: dict, run_dir: str):
    facts_path = os.path.join(run_dir, "02_facts.json")
    valid_ids: set[int] = set()
    if os.path.isfile(facts_path):
        facts_doc = _read_json(facts_path)
        valid_ids = {f["id"] for f in facts_doc.get("facts", [])}
    guarded, checks = cite_check._apply_guards(plan, valid_ids)
    dropped = sum(checks.get("dropped_uncited_by_section", {}).values())
    return guarded, dropped


def _apply_glossary(plan: dict, run_dir: str):
    glossary_path = os.path.join(run_dir, "02_glossary.json")
    terms_in = 0
    terms_kept = 0
    terms: dict = {}
    if os.path.isfile(glossary_path):
        glossary = _read_json(glossary_path)
        entries = glossary.get("terms", []) or []
        terms_in = len(entries)
        visible_normalized = textnorm.normalize_text(plan_view.visible_text(plan))
        for entry in entries:
            matched = entry.get("matched_term", "") or ""
            normalized_matched = textnorm.normalize_text(matched)
            if normalized_matched and normalized_matched in visible_normalized:
                terms[matched] = {
                    "definition": entry.get("definition", "") or "",
                    "source": entry.get("source", "") or "",
                }
                terms_kept += 1
    plan["terms"] = terms
    return plan, terms_in, terms_kept


def _pii_sweep(plan: dict):
    count = 0

    def sweep_string(s: str) -> str:
        nonlocal count
        new_s, n1 = _PII_HONORIFIC_RE.subn("your doctor", s)
        new_s, n2 = _PII_CREDENTIAL_RE.subn("your doctor", new_s)
        count += n1 + n2
        return new_s

    def walk(value, key=None):
        if isinstance(value, str):
            return sweep_string(value)
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: (v if k == "meta" else walk(v, k)) for k, v in value.items()}
        return value

    return walk(plan), count


def _concatenate_input_text(run_dir: str) -> str:
    input_dir = os.path.join(run_dir, "00_input")
    if not os.path.isdir(input_dir):
        return ""
    parts = []
    for name in sorted(os.listdir(input_dir)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            parts.append(f.read().replace("\f", "\n"))
    return "\n".join(parts)


def _compute_score(plan: dict, run_dir: str) -> dict:
    before = readability.fk_grade(_concatenate_input_text(run_dir))
    after = readability.fk_grade(plan_view.visible_text(plan))
    return {"before_grade": before, "after_grade": after}


def _build_notices(run_dir: str, used_draft_fallback: bool, items_dropped: int):
    run_log = runlog.read(run_dir)
    stages = run_log.get("stages", {})
    notices = list(run_log.get("notices", []) or [])
    added = False

    if used_draft_fallback and _DRAFT_FALLBACK_NOTICE not in notices:
        notices.append(_DRAFT_FALLBACK_NOTICE)
        added = True

    any_failed = any(entry.get("status") == "failed" for entry in stages.values())
    any_key_degraded = any(
        stages.get(name, {}).get("status") == "degraded"
        for name in ("ground", "assemble", "correct")
    )
    needs_generic = any_failed or any_key_degraded or items_dropped > 0
    if needs_generic and _GENERIC_VERIFY_NOTICE not in notices:
        notices.append(_GENERIC_VERIFY_NOTICE)
        added = True

    seen: set[str] = set()
    deduped = []
    for n in notices:
        if n not in seen:
            deduped.append(n)
            seen.add(n)

    return deduped, added


def _run(run_dir: str) -> int:
    precondition_error = _check_preconditions(run_dir)
    if precondition_error:
        print(precondition_error, file=sys.stderr)
        return 1

    plan, source = _load_plan(run_dir)
    if plan is None:
        print(
            "finalize: could not find 03_plan.draft.json or "
            "05_plan.corrected.json in the run directory.",
            file=sys.stderr,
        )
        return 1
    used_draft_fallback = source == "draft"

    additions_merged = _merge_additions(plan, run_dir)
    plan, items_dropped = _apply_citation_guard(plan, run_dir)
    plan, glossary_terms_in, glossary_terms_kept = _apply_glossary(plan, run_dir)
    plan, pii_substitutions = _pii_sweep(plan)

    score = _compute_score(plan, run_dir)
    plan["score"] = score

    notices, notice_added = _build_notices(run_dir, used_draft_fallback, items_dropped)
    plan["notices"] = notices

    run_id = os.path.basename(os.path.normpath(run_dir))
    plugin_version = runlog.plugin_version()
    old_meta = plan.get("meta") or {}
    plan["meta"] = {
        "run_id": old_meta.get("run_id", run_id),
        "plugin_version": plugin_version,
        "schema_version": SCHEMA_VERSION,
        "level": old_meta.get("level", "standard"),
        "created_at": old_meta.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    plan["schema_version"] = SCHEMA_VERSION
    plan["plugin_version"] = plugin_version

    care_plan_schema = validate.load_schema("care_plan")
    errors = validate.validate(plan, care_plan_schema)
    if errors:
        print(
            "finalize: internal bug -- the final plan does not match "
            "care_plan.schema.json:",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    _write_json(os.path.join(run_dir, "06_plan.final.json"), plan)

    md_path = os.path.join(run_dir, "report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_md.render(plan))

    html_path = os.path.join(run_dir, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html.render(plan))

    checks = {
        "plan_source": source,
        "additions_merged": additions_merged,
        "items_dropped_uncited": items_dropped,
        "glossary_terms_in": glossary_terms_in,
        "glossary_terms_kept": glossary_terms_kept,
        "pii_substitutions": pii_substitutions,
        "before_grade": score["before_grade"],
        "after_grade": score["after_grade"],
        "notices": notices,
    }
    status = "degraded" if notice_added else "ok"
    runlog.record(run_dir, "finalize", status, checks=checks)

    print(html_path)
    print(md_path)
    line = plan_view.score_line(score)
    print(line if line else "Reading level: not enough text to estimate.")
    for n in notices:
        print(n)
    print(
        f"finalize: {status} | before_grade={score['before_grade']} "
        f"after_grade={score['after_grade']} notices={len(notices)}"
    )

    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Finalize a run: merge, guard, glossary re-detect, PII sweep, score, render."
    )
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return _run(args.run_dir)


if __name__ == "__main__":
    sys.exit(main())
