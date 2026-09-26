#!/usr/bin/env python3
"""Self-contained HTML renderer for a final care plan.

`render(plan) -> str` fills `templates/report.html` (via `string.Template`)
with HTML-escaped content and produces one file: inline CSS, inline JS, no
external assets, no network calls. Section order and content come from
`plan_view`, shared with `render_md.py`.

Stdlib only. Runnable as
``python3 render_html.py --run-dir D [--plan <path>] [--out <path>]``
(defaults: read ``06_plan.final.json``, write ``report.html``) and
importable as `render_html`.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from string import Template

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_view  # noqa: E402
import runlog  # noqa: E402

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_PATH = os.path.normpath(
    os.path.join(_SCRIPTS_DIR, "..", "templates", "report.html")
)

# Sections whose bodies get glossary term spans wrapped in, per the design
# brief: summary, findings, next steps, watch. Not reason_for_visit,
# questions, or the glossary list itself.
_WRAPPABLE_KINDS = {"paragraph", "findings", "next_steps", "watch"}


def _esc(s) -> str:
    return html.escape(s or "", quote=True)


def _read_template() -> str:
    with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _glossary_patterns(view):
    """One compiled case-insensitive regex per glossary term, matched
    against already-HTML-escaped text (so the pattern is built from the
    escaped term too)."""
    patterns = []
    for section in view["sections"]:
        if section["key"] != "glossary":
            continue
        for item in section["items"]:
            term = item["term"]
            escaped_term = html.escape(term, quote=True)
            if not escaped_term:
                continue
            patterns.append({
                "term": term,
                "definition": item["definition"],
                "pattern": re.compile(re.escape(escaped_term), re.IGNORECASE),
            })
    return patterns


def _wrap_terms(escaped_text, glossary_terms, used_terms, enable):
    """Wrap the first not-yet-used glossary term found in `escaped_text`
    (already HTML-escaped) with a <span class="term" ...>. Mutates
    `used_terms` so each term is wrapped only once across the document."""
    if not enable or not escaped_text:
        return escaped_text
    for g in glossary_terms:
        if g["term"] in used_terms:
            continue
        m = g["pattern"].search(escaped_text)
        if m:
            used_terms.add(g["term"])
            span = (
                f'<span class="term" tabindex="0" data-def="{_esc(g["definition"])}">'
                f'{m.group(0)}</span>'
            )
            escaped_text = escaped_text[: m.start()] + span + escaped_text[m.end():]
    return escaped_text


def _render_row(row, glossary_terms, used_terms):
    title = _wrap_terms(_esc(row["title"]), glossary_terms, used_terms, True)
    detail = _wrap_terms(_esc(row.get("detail", "")), glossary_terms, used_terms, True)
    checked = " checked" if row["checked"] else ""
    key = _esc(row["key"])

    parts = ['<div class="row">']
    parts.append("<label>")
    parts.append(f'<input type="checkbox" data-key="{key}"{checked}>')
    parts.append('<span class="print-empty-box">☐</span>')
    parts.append('<span class="row-body">')
    parts.append(f'<span class="row-title">{title}</span> ')
    parts.append(f'<span class="type-label">({_esc(row["type_label"])})</span>')
    if detail:
        parts.append(f'<span class="row-detail">{detail}</span>')
    parts.append("</span>")
    parts.append("</label>")
    if row["sub"]:
        parts.append('<details><summary>Details</summary><ul>')
        for s in row["sub"]:
            wrapped = _wrap_terms(_esc(s), glossary_terms, used_terms, True)
            parts.append(f"<li>{wrapped}</li>")
        parts.append("</ul></details>")
    parts.append("</div>")
    return "\n".join(parts)


def _render_watch_row(row, glossary_terms, used_terms):
    symptom = _wrap_terms(_esc(row.get("symptom", "")), glossary_terms, used_terms, True)
    what_to_do = _wrap_terms(_esc(row.get("what_to_do", "")), glossary_terms, used_terms, True)
    meaning = _wrap_terms(_esc(row.get("what_it_might_mean", "")), glossary_terms, used_terms, True)
    related = _wrap_terms(_esc(row.get("related_to", "")), glossary_terms, used_terms, True)
    urgency = row.get("urgency_label", "")
    pill = f'<span class="pill">{_esc(urgency)}</span>' if urgency else ""

    parts = ['<div class="row watch-row">']
    parts.append(f'<div class="row-title">{symptom}{pill}</div>')
    if what_to_do:
        parts.append(f'<div class="row-detail">{what_to_do}</div>')
    extras = []
    if meaning:
        extras.append(f"<li>{meaning}</li>")
    if related:
        extras.append(f"<li>Related to: {related}</li>")
    if extras:
        parts.append('<ul class="watch-extra">' + "".join(extras) + "</ul>")
    parts.append("</div>")
    return "\n".join(parts)


def _render_section(section, glossary_terms, used_terms) -> str:
    kind = section["kind"]
    wrap_enabled = kind in _WRAPPABLE_KINDS
    open_attr = "" if kind == "glossary" else " open"
    out = [f'<details{open_attr}><summary>{_esc(section["heading"])}</summary>']

    if kind == "paragraph":
        text = _wrap_terms(_esc(section["text"]), glossary_terms, used_terms, wrap_enabled)
        out.append(f"<p>{text}</p>")

    elif kind == "list":
        out.append("<ul>")
        for item in section["items"]:
            out.append(f'<li>{_esc(item["text"])}</li>')
        out.append("</ul>")

    elif kind == "findings":
        for item in section["items"]:
            title = _esc(item.get("title", ""))
            plain = item.get("plain_name", "")
            if plain and plain != item.get("title", ""):
                title = f"{title} ({_esc(plain)})"
            title = _wrap_terms(title, glossary_terms, used_terms, wrap_enabled)
            sev = item.get("severity_label", "")
            pill = f'<span class="pill">{_esc(sev)}</span>' if sev else ""
            out.append(f'<div class="finding"><div class="finding-title">{title} {pill}</div>')
            desc = _wrap_terms(_esc(item.get("description", "")), glossary_terms, used_terms, wrap_enabled)
            if desc:
                out.append(f'<div class="finding-body">{desc}</div>')
            meaning = _wrap_terms(_esc(item.get("what_it_means", "")), glossary_terms, used_terms, wrap_enabled)
            if meaning:
                out.append(f'<div class="finding-body">{meaning}</div>')
            out.append("</div>")
        if "changed" in section:
            changed = _wrap_terms(_esc(section["changed"]), glossary_terms, used_terms, wrap_enabled)
            out.append(f'<p class="changed">{changed}</p>')

    elif kind == "next_steps":
        for group_key, group_label in (("todo", "To do"), ("done", "Already done")):
            rows = section[group_key]
            if not rows:
                continue
            out.append(f"<h3>{_esc(group_label)}</h3>")
            for row in rows:
                out.append(_render_row(row, glossary_terms, used_terms))

    elif kind == "watch":
        for row in section["items"]:
            out.append(_render_watch_row(row, glossary_terms, used_terms))

    elif kind == "numbered":
        out.append("<ol>")
        for item in section["items"]:
            out.append(f'<li>{_esc(item["text"])}</li>')
        out.append("</ol>")

    elif kind == "glossary":
        out.append("<dl>")
        for item in section["items"]:
            out.append(f'<dt>{_esc(item["term"])}</dt><dd>{_esc(item["definition"])}</dd>')
        out.append("</dl>")

    out.append("</details>")
    return "\n".join(out)


def render(plan: dict) -> str:
    view = plan_view.build_view(plan)

    body_parts = []

    if view["notices"]:
        notice_html = "".join(f"<p>{_esc(n)}</p>" for n in view["notices"])
        body_parts.append(f'<div class="notice">{notice_html}</div>')

    body_parts.append(f'<h1>{_esc(view["title"])}</h1>')
    body_parts.append(
        '<p class="interactive-hint">Tap a checkbox to mark a step done. '
        "Tap or focus a highlighted word for its definition.</p>"
    )

    score_line = view.get("score_line")
    if score_line:
        body_parts.append(f'<p class="score-line">{_esc(score_line)}</p>')

    glossary_terms = _glossary_patterns(view)
    used_terms: set[str] = set()

    for section in view["sections"]:
        body_parts.append(_render_section(section, glossary_terms, used_terms))

    plugin_version = plan.get("plugin_version") or runlog.plugin_version()
    body_parts.append(
        f"<footer>Made with simplify-med {_esc(plugin_version)}. "
        "This is a reading aid, not medical advice.</footer>"
    )

    body_html = "\n".join(body_parts)
    plan_json = json.dumps(plan, indent=2, sort_keys=False).replace("</", "<\\/")
    run_id = (plan.get("meta") or {}).get("run_id", "")

    template = Template(_read_template())
    return template.substitute(
        title=_esc(view["title"]),
        body=body_html,
        plan_json=plan_json,
        run_id=json.dumps(run_id),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a final care plan to a self-contained HTML report (on request only)."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--plan", default=None, help="Path to the plan JSON (default: <run-dir>/06_plan.final.json)")
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.html)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    plan_path = args.plan or os.path.join(args.run_dir, "06_plan.final.json")
    if not os.path.isfile(plan_path):
        print(
            f"render_html: cannot find {plan_path} -- run finalize.py first.",
            file=sys.stderr,
        )
        return 1

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    out_path = args.out or os.path.join(args.run_dir, "report.html")
    text = render(plan)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"OK wrote {out_path}")
    print(f"render_html: ok | path={out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
