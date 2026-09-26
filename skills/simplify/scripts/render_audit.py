#!/usr/bin/env python3
"""Render an optional source-traceability audit for a finalized run.

For every patient-visible item (`plan_paths.visible_items`, report order)
the audit prints the item as the patient sees it, then each cited source
unit with its file, page, line, extraction method, and text from
`01_units.json`. It ends with the protected-content coverage and a stage
table from `run.json`. The patient report never contains any of this.

Stdlib only. Runnable as ``python3 render_audit.py --run-dir D [--out <path>]``
(default output ``report.audit.md``) and importable as `render_audit`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_paths  # noqa: E402
import plan_view  # noqa: E402


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"{os.path.basename(path)} must contain a JSON object")
    return document


def _unit_index(units_doc: dict) -> dict:
    return {
        unit["id"]: unit
        for unit in (units_doc.get("units") or [])
        if isinstance(unit, dict) and "id" in unit
    }


def _unit_line(unit_id, units_by_id) -> str:
    unit = units_by_id.get(unit_id)
    if unit is None:
        return f"  - unit {unit_id} · (unknown unit)"
    location = f'{unit.get("file", "?")}:{unit.get("page", "?")}:{unit.get("line", "?")}'
    details = f' · extraction={unit.get("extraction_method", "unknown")}'
    if unit.get("skip"):
        details += f' · skip={unit["skip"]}'
    return f'  - unit {unit_id} · {location}{details} · "{unit.get("text", "")}"'


def _cell(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _stage_table(run_log: dict) -> list[str]:
    lines = ["| Stage | Status | Attempts | Key checks |", "|---|---|---|---|"]
    stages = run_log.get("stages")
    if not isinstance(stages, dict) or not stages:
        return ["(no stages recorded)"]
    for stage, entry in stages.items():
        entry = entry if isinstance(entry, dict) else {}
        checks = entry.get("checks")
        checks_text = "; ".join(f"{key}={value}" for key, value in checks.items()) if isinstance(checks, dict) else ""
        lines.append(
            f"| {_cell(stage)} | {_cell(entry.get('status'))} | {_cell(entry.get('attempts'))} | {_cell(checks_text)} |"
        )
    return lines


def _coverage_lines(plan: dict) -> list[str]:
    coverage = plan.get("coverage")
    if not isinstance(coverage, dict) or not coverage:
        return ["(none)"]
    lines = []
    for category, entry in coverage.items():
        entry = entry if isinstance(entry, dict) else {}
        unit_ids = ", ".join(str(uid) for uid in entry.get("unit_ids") or []) or "-"
        lines.append(f"- {category}: {entry.get('status', '')} · units {unit_ids}")
    return lines


def render(plan: dict, units_doc: dict, run_log: dict) -> str:
    units_by_id = _unit_index(units_doc)
    run_id = plan.get("run_id") or run_log.get("run_id", "")
    title = plan_view.title_for(plan.get("visit_type"))

    lines = [f"# Audit view — {run_id}", "", f"Report: {title}", "", "## Visible items", ""]
    items = plan_paths.visible_items(plan)
    if not items:
        lines.extend(["(none)", ""])
    for path, item in items:
        lines.append(f"### {path}")
        lines.append("")
        lines.append(plan_view.row_plain_text(plan_view.item_row(path, item)))
        unit_ids = item.get("unit_ids") or []
        if unit_ids:
            lines.extend(_unit_line(unit_id, units_by_id) for unit_id in unit_ids)
        else:
            lines.append("  - (no cited units)")
        lines.append("")

    lines.extend(["## Protected content coverage", ""])
    lines.extend(_coverage_lines(plan))
    lines.extend(["", "## Stages", ""])
    lines.extend(_stage_table(run_log))
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
    plan_path = os.path.join(run_dir, plan_view.FINAL_PLAN_NAME)
    try:
        plan = _read_json(plan_path)
        plan_view.assert_renderable_plan(plan, run_dir, plan_path)
        units_doc = _read_json(os.path.join(run_dir, "01_units.json"))
        run_log = _read_json(os.path.join(run_dir, "run.json"))
        text = render(plan, units_doc, run_log)
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
