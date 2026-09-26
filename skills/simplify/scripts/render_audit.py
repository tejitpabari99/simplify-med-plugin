#!/usr/bin/env python3
"""Render an optional source-traceability audit for a finalized run."""

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
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"{os.path.basename(path)} must contain a JSON object")
    return document


def _fact_index(facts_doc: dict) -> dict:
    return {fact["id"]: fact for fact in facts_doc.get("facts", [])}


def _unit_index(units_doc: dict) -> dict:
    return {unit["id"]: unit for unit in units_doc.get("units", [])}


def _fact_line(fact_id, facts_by_id, units_by_id, indent="  ", details=None) -> str:
    fact = facts_by_id.get(fact_id)
    if fact is None:
        return f"{indent}- fact {fact_id} · (unknown fact)"
    unit = units_by_id.get(fact.get("unit_id"))
    if unit:
        location = f'{unit.get("file", "?")}:{unit.get("page", "?")}:{unit.get("line", "?")}'
        extraction = f' · extraction={unit.get("extraction_method", "unknown")}'
    else:
        location = "?:?:?"
        extraction = " · extraction=unknown"
    suffix = ""
    for key, value in (details or []):
        suffix += f" · {key}={value}"
    return f'{indent}- fact {fact_id} · {location}{extraction}{suffix} · "{fact.get("quote", "")}"'


def _fact_lines(fact_ids, facts_by_id, units_by_id) -> list[str]:
    return [_fact_line(fact_id, facts_by_id, units_by_id) for fact_id in (fact_ids or [])]


def _stage_table(run_log: dict) -> list[str]:
    lines = ["| Stage | Status | Attempts | Key checks |", "|---|---|---|---|"]
    for stage, entry in run_log.get("stages", {}).items():
        checks = entry.get("checks", {}) or {}
        checks_text = "; ".join(f"{key}={value}" for key, value in checks.items())
        lines.append(f"| {stage} | {entry.get('status', '')} | {entry.get('attempts', '')} | {checks_text} |")
    return lines


def _question_text(question):
    return question.get("question", "") if isinstance(question, dict) else question


def render(
    plan: dict,
    facts_doc: dict,
    units_doc: dict,
    run_log: dict,
    review_doc: dict | None = None,
    coverage_doc: dict | None = None,
) -> str:
    facts_by_id = _fact_index(facts_doc)
    units_by_id = _unit_index(units_doc)
    review_by_fact = {
        item.get("fact_id"): item.get("result", "")
        for item in (review_doc or {}).get("fact_reviews", [])
    }
    run_id = (plan.get("meta") or {}).get("run_id") or run_log.get("run_id", "")

    lines = [f"# Audit view — {run_id}", "", "## Stages", ""]
    lines.extend(_stage_table(run_log))
    lines.append("")

    if plan.get("summary"):
        lines.extend(["## What you need to know", "", plan["summary"]])
        lines.extend(_fact_lines(plan.get("summary_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    reasons = plan.get("reason_for_visit", []) or []
    if reasons:
        lines.extend(["## Why you were seen", ""])
        for item in reasons:
            text = (item.get("reason") or "") + (f": {item['description']}" if item.get("description") else "")
            lines.append(f"- {text}")
            lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    diagnosis = plan.get("diagnosis", {}) or {}
    details = diagnosis.get("details", []) or []
    if details or diagnosis.get("changed_since_last_visit"):
        lines.extend(["## What the doctor found", ""])
        for item in details:
            lines.append(f"- {item.get('title', '')}")
            lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        if diagnosis.get("changed_since_last_visit"):
            lines.append(f"- Changed since last time: {diagnosis['changed_since_last_visit']}")
            lines.extend(_fact_lines(diagnosis.get("changed_since_last_visit_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    if any(plan.get(field) for field, _ in _NEXT_STEP_FIELDS):
        lines.extend(["## Your next steps", ""])
        for field, label in _NEXT_STEP_FIELDS:
            for item in plan.get(field, []) or []:
                title = item.get("title") or item.get("time_frame") or label
                lines.append(f"- [{label}] {title}")
                lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    warnings = plan.get("warning_signs", []) or []
    if warnings:
        lines.extend(["## What to watch for", ""])
        order = {urgency: index for index, urgency in enumerate(plan_view.URGENCY_ORDER)}
        for item in sorted(warnings, key=lambda warning: order.get(warning.get("urgency"), len(order))):
            lines.append(f"- {item.get('symptom', '')}")
            lines.extend(_fact_lines(item.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    questions = plan.get("questions", []) or []
    if questions:
        lines.extend(["## Questions to ask your doctor", ""])
        for index, question in enumerate(questions, start=1):
            lines.append(f"{index}. {_question_text(question)}")
            if isinstance(question, dict):
                lines.extend(_fact_lines(question.get("source_fact_ids"), facts_by_id, units_by_id))
        lines.append("")

    if plan.get("schema_version") == "2.0":
        lines.extend(["## Omitted facts", ""])
        omissions = plan.get("omitted_facts", []) or []
        if omissions:
            for omission in omissions:
                fact_id = omission.get("fact_id")
                lines.append(_fact_line(
                    fact_id,
                    facts_by_id,
                    units_by_id,
                    indent="",
                    details=(
                        ("reason", omission.get("reason", "")),
                        ("review", review_by_fact.get(fact_id, "not_reviewed")),
                    ),
                ))
        else:
            lines.append("(none)")
        lines.append("")
    else:
        lines.extend(["## Low priority (not shown to the patient)", ""])
        low_priority = plan.get("low_priority", []) or []
        lines.extend(f"- {item}" for item in low_priority)
        if not low_priority:
            lines.append("(none)")
        lines.extend(["", "## Facts not present in the plan", ""])
        missing = (coverage_doc or {}).get("missing", []) or []
        if missing:
            for fact_id in missing:
                lines.append(_fact_line(fact_id, facts_by_id, units_by_id, indent=""))
        else:
            lines.append("(none)")
        lines.append("")

    lines.extend(["## Facts dropped at grounding", ""])
    dropped = facts_doc.get("dropped", []) or []
    if dropped:
        for item in dropped:
            fact = item.get("fact", {}) or {}
            lines.append(f'- chunk {item.get("chunk")} · {item.get("reason")} · "{fact.get("quote", "")}"')
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render an optional audit view for a finalized run.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.audit.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    run_dir = args.run_dir
    plan_path = os.path.join(run_dir, "06_plan.final.json")
    try:
        plan = _read_json(plan_path)
        plan_view.assert_renderable_plan(plan, run_dir, plan_path)
        facts_doc = _read_json(os.path.join(run_dir, "02_facts.json"))
        units_doc = _read_json(os.path.join(run_dir, "01_units.json"))
        run_log = _read_json(os.path.join(run_dir, "run.json"))
        review_doc = None
        coverage_doc = None
        if plan.get("schema_version") == "2.0":
            review_doc = _read_json(os.path.join(run_dir, "04_review.json"))
        else:
            coverage_path = os.path.join(run_dir, "04_coverage.json")
            if os.path.isfile(coverage_path):
                coverage_doc = _read_json(coverage_path)
        text = render(
            plan,
            facts_doc,
            units_doc,
            run_log,
            review_doc=review_doc,
            coverage_doc=coverage_doc,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"render_audit: {error}", file=sys.stderr)
        return 1

    out_path = args.out or os.path.join(run_dir, "report.audit.md")
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    print(f"OK wrote {out_path}")
    print("render_audit: ok | written=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
