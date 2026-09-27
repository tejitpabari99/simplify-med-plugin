#!/usr/bin/env python3
"""Markdown renderer for a final plan.

`render(plan, glossary=None) -> str` builds the short patient-facing
report, in the same order as `render_html.py`, via the shared `plan_view`
module. No HTML in the output; one bullet per line.

Stdlib only. Runnable as
``python3 render_md.py --run-dir D [--plan <path>] [--out <path>]``
(defaults: read ``05_plan.final.json``, write ``report.md``) and
importable as `render_md`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_view  # noqa: E402


def _bullet(row) -> str:
    if row["label"] and row["text"]:
        return f"- **{row['label']}:** {row['text']}"
    return f"- {row['label'] or row['text']}"


def _render_section(section) -> list[str]:
    kind = section["kind"]
    lines = [f"## {section['heading']}", ""] if section.get("heading") else []

    if kind == "paragraph":
        lines.extend([section["text"], ""])

    elif kind == "findings":
        if section["lead"]:
            lines.extend([section["lead"], ""])
        if section["items"]:
            lines.extend(_bullet(row) for row in section["items"])
            lines.append("")
        if section["diagnoses"]:
            lines.extend([f"**{section['diagnoses_label']}**", ""])
            lines.extend(_bullet(row) for row in section["diagnoses"])
            lines.append("")
        if section["disposition"]:
            lines.extend([section["disposition"], ""])

    elif kind == "list":
        lines.extend(_bullet(row) for row in section["items"])
        lines.append("")

    elif kind == "glossary":
        for item in section["items"]:
            lines.append(f"- **{item['term']}:** {item['definition']}")
        lines.append("")

    return lines


def render(plan: dict, glossary: dict | None = None) -> str:
    view = plan_view.build_view(plan, glossary=glossary)
    lines = [f"# {view['title']}", ""]
    for section in view["sections"]:
        lines.extend(_render_section(section))
    return "\n".join(lines).rstrip() + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a final plan to Markdown.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--plan", default=None, help=f"Path to the plan JSON (default: <run-dir>/{plan_view.FINAL_PLAN_NAME})"
    )
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    plan_path = args.plan or os.path.join(args.run_dir, plan_view.FINAL_PLAN_NAME)
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        plan_view.assert_renderable_plan(plan, args.run_dir, plan_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"render_md: {error}", file=sys.stderr)
        return 1

    out_path = args.out or os.path.join(args.run_dir, "report.md")
    text = render(plan)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"OK wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
