#!/usr/bin/env python3
"""Markdown renderer for a final care plan.

`render(plan) -> str` builds the same seven sections, in the same order,
as `render_html.py`, via the shared `plan_view` module. No HTML in the
output.

Stdlib only. Runnable as
``python3 render_md.py --run-dir D [--plan <path>] [--out <path>]``
(defaults: read ``06_plan.final.json``, write ``report.md``) and
importable as `render_md`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_view  # noqa: E402


def _render_next_steps(section):
    lines = []
    for group_key, group_heading in (("todo", "To do"), ("done", "Already done")):
        rows = section[group_key]
        if not rows:
            continue
        lines.append(f"### {group_heading}")
        lines.append("")
        for row in rows:
            mark = "x" if row["checked"] else " "
            detail = f" — {row['detail']}" if row.get("detail") else ""
            lines.append(f"- [{mark}] **{row['title']}**{detail}")
            lines.append(f"  _{row['type_label']}_")
            for s in row["sub"]:
                lines.append(f"  - {s}")
        lines.append("")
    return lines


def _render_section(section) -> list[str]:
    kind = section["kind"]
    lines = [f"## {section['heading']}", ""]

    if kind == "paragraph":
        lines.append(section["text"])
        lines.append("")

    elif kind == "list":
        for item in section["items"]:
            lines.append(f"- {item['text']}")
        lines.append("")

    elif kind == "findings":
        for item in section["items"]:
            title = item.get("title", "")
            plain = item.get("plain_name", "")
            head = title + (f" ({plain})" if plain and plain != title else "")
            sev = item.get("severity_label", "")
            if sev:
                head += f" _({sev})_"
            lines.append(f"- **{head}**")
            if item.get("description"):
                lines.append(f"  - {item['description']}")
            if item.get("what_it_means"):
                lines.append(f"  - {item['what_it_means']}")
        if "changed" in section:
            lines.append("")
            lines.append(section["changed"])
        lines.append("")

    elif kind == "next_steps":
        lines.extend(_render_next_steps(section))

    elif kind == "watch":
        for row in section["items"]:
            urgency = f" _({row['urgency_label']})_" if row.get("urgency_label") else ""
            lines.append(f"- **{row['symptom']}**{urgency} — {row['what_to_do']}")
            if row.get("what_it_might_mean"):
                lines.append(f"  - {row['what_it_might_mean']}")
            if row.get("related_to"):
                lines.append(f"  - Related to: {row['related_to']}")
        lines.append("")

    elif kind == "numbered":
        for item in section["items"]:
            lines.append(f"{item['n']}. {item['text']}")
        lines.append("")

    elif kind == "glossary":
        for item in section["items"]:
            lines.append(f"- **{item['term']}** — {item['definition']}")
        lines.append("")

    return lines


def render(plan: dict) -> str:
    view = plan_view.build_view(plan)
    lines = [f"# {view['title']}", ""]

    for notice in view["notices"]:
        lines.append(f"> {notice}")
        lines.append("")

    score_line = view.get("score_line")
    if score_line:
        lines.append(f"_{score_line}_")
        lines.append("")

    for section in view["sections"]:
        lines.extend(_render_section(section))

    return "\n".join(lines).rstrip() + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a final care plan to Markdown.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--plan", default=None, help="Path to the plan JSON (default: <run-dir>/06_plan.final.json)")
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    plan_path = args.plan or os.path.join(args.run_dir, "06_plan.final.json")
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    out_path = args.out or os.path.join(args.run_dir, "report.md")
    text = render(plan)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"OK wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
