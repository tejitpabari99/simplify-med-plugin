#!/usr/bin/env python3
"""Audit view: every plan item paired with the facts backing it, a stage
table, coverage misses, and grounding drops. Produced only on request --
never part of the normal `finalize.py` run.

CLI: ``python3 render_audit.py --run-dir D [--out report.audit.md]``

Stdlib only. Importable as `render_audit`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_view  # noqa: E402

_NEXT_STEP_FIELDS = (
    ("medications", "Medication"),
    ("tests", "Test"),
    ("procedures", "Procedure"),
    ("follow_up", "Appointment"),
    ("other", "Instruction"),
)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fact_index(facts_doc: dict) -> dict:
    return {f["id"]: f for f in facts_doc.get("facts", [])}


def _unit_index(units_doc: dict) -> dict:
    return {u["id"]: u for u in units_doc.get("units", [])}


def _fact_line(fact_id, facts_by_id, units_by_id, indent="  ") -> str:
    fact = facts_by_id.get(fact_id)
    if fact is None:
        return f"{indent}- fact {fact_id} · (unknown fact)"
    unit = units_by_id.get(fact.get("unit_id"))
    loc = f'{unit["file"]}:{unit["page"]}:{unit["line"]}' if unit else "?:?:?"
    return f'{indent}- fact {fact_id} · {loc} · "{fact.get("quote", "")}"'


def _fact_lines(fact_ids, facts_by_id, units_by_id) -> list[str]:
    return [_fact_line(fid, facts_by_id, units_by_id) for fid in (fact_ids or [])]


def _stage_table(run_log: dict) -> list[str]:
    lines = ["| Stage | Status | Attempts | Key checks |", "|---|---|---|---|"]
    for stage, entry in run_log.get("stages", {}).items():
        checks = entry.get("checks", {}) or {}
        checks_str = "; ".join(f"{k}={v}" for k, v in checks.items())
        lines.append(f"| {stage} | {entry.get('status', '')} | {entry.get('attempts', '')} | {checks_str} |")
    return lines


def render(plan: dict, facts_doc: dict, units_doc: dict, coverage_doc: dict | None, run_log: dict) -> str:
    facts_by_id = _fact_index(facts_doc)
    units_by_id = _unit_index(units_doc)
    run_id = (plan.get("meta") or {}).get("run_id") or run_log.get("run_id", "")

    lines = [f"# Audit view — {run_id}", "", "## Stages", ""]
    lines.extend(_stage_table(run_log))
    lines.append("")

    if plan.get("summary"):
        lines.append("## What you need to know")
        lines.append("")
        lines.append(plan["summary"])
        lines.extend(_fact_lines(plan.get("summary_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    reasons = plan.get("reason_for_visit", []) or []
    if reasons:
        lines.append("## Why you were seen")
        lines.append("")
        for item in reasons:
            text = (item.get("reason") or "") + (f": {item['description']}" if item.get("description") else "")
            lines.append(f"- {text}")
            lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    diagnosis = plan.get("diagnosis", {}) or {}
    details = diagnosis.get("details", []) or []
    if details or diagnosis.get("changed_since_last_visit"):
        lines.append("## What the doctor found")
        lines.append("")
        for d in details:
            lines.append(f"- {d.get('title', '')}")
            lines.extend(_fact_lines(d.get("source_fact_ids"), facts_by_id, units_by_id))
        if diagnosis.get("changed_since_last_visit"):
            lines.append(f"- Changed since last time: {diagnosis['changed_since_last_visit']}")
            lines.extend(_fact_lines(diagnosis.get("changed_since_last_visit_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    any_next = any(plan.get(field) for field, _ in _NEXT_STEP_FIELDS)
    if any_next:
        lines.append("## Your next steps")
        lines.append("")
        for field, label in _NEXT_STEP_FIELDS:
            for item in plan.get(field, []) or []:
                title = item.get("title") or item.get("time_frame") or label
                lines.append(f"- [{label}] {title}")
                lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    warnings = plan.get("warning_signs", []) or []
    if warnings:
        lines.append("## What to watch for")
        lines.append("")
        order = {u: i for i, u in enumerate(plan_view.URGENCY_ORDER)}
        for item in sorted(warnings, key=lambda w: order.get(w.get("urgency"), len(order))):
            lines.append(f"- {item.get('symptom', '')}")
            lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    questions = plan.get("questions", []) or []
    if questions:
        lines.append("## Questions to ask your doctor")
        lines.append("")
        for i, q in enumerate(questions, start=1):
            lines.append(f"{i}. {q}")
        lines.append("")

    terms = plan.get("terms", {}) or {}
    if terms:
        lines.append("## Medical terms explained")
        lines.append("")
        for term in sorted(terms.keys(), key=str.lower):
            lines.append(f"- **{term}** — {terms[term].get('definition', '')}")
        lines.append("")

    lines.append("## Low priority (not shown to the patient)")
    lines.append("")
    low_priority = plan.get("low_priority", []) or []
    if low_priority:
        for text in low_priority:
            lines.append(f"- {text}")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Facts not present in the plan")
    lines.append("")
    missing = (coverage_doc or {}).get("missing", []) or []
    if missing:
        for fid in missing:
            lines.append(_fact_line(fid, facts_by_id, units_by_id, indent=""))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Facts dropped at grounding")
    lines.append("")
    dropped = facts_doc.get("dropped", []) or []
    if dropped:
        for d in dropped:
            fact = d.get("fact", {}) or {}
            quote = fact.get("quote", "")
            lines.append(f'- chunk {d.get("chunk")} · {d.get("reason")} · "{quote}"')
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the audit view for a run (on request only).")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.audit.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir

    plan = _read_json(os.path.join(run_dir, "06_plan.final.json"))
    facts_doc = _read_json(os.path.join(run_dir, "02_facts.json"))
    units_doc = _read_json(os.path.join(run_dir, "01_units.json"))
    coverage_path = os.path.join(run_dir, "04_coverage.json")
    coverage_doc = _read_json(coverage_path) if os.path.isfile(coverage_path) else None
    run_log_path = os.path.join(run_dir, "run.json")
    run_log = _read_json(run_log_path) if os.path.isfile(run_log_path) else {}

    text = render(plan, facts_doc, units_doc, coverage_doc, run_log)

    out_path = args.out or os.path.join(run_dir, "report.audit.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"OK wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
