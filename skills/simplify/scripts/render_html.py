#!/usr/bin/env python3
"""Self-contained HTML renderer for a final plan.

`render(plan, glossary=None) -> str` fills `templates/report.html` (via
`string.Template`) with HTML-escaped content and produces one printable
file: inline CSS, a little inline JS for glossary pop-ups, no external
assets, no network calls. Section order and content come from
`plan_view`, shared with `render_md.py`.

Stdlib only. Runnable as
``python3 render_html.py --run-dir D [--plan <path>] [--glossary <path>] [--out <path>]``
(defaults: read ``05_plan.final.json``, write ``report.html``) and
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
import validate  # noqa: E402

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_PATH = os.path.normpath(
    os.path.join(_SCRIPTS_DIR, "..", "templates", "report.html")
)
GLOSSARY_NAME = "07_glossary.json"

# Section keys whose text gets glossary term spans wrapped in. Not
# questions or the glossary list itself.
_WRAPPABLE_KEYS = {"why_you_went", "findings", "next_steps", "return_precautions"}


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


def _render_list(rows, wrap) -> list[str]:
    out = ["<ul>"]
    for row in rows:
        text = wrap(_esc(row["text"]))
        if row["label"]:
            label = wrap(_esc(row["label"]))
            body = f"<strong>{label}:</strong> {text}" if text else f"<strong>{label}</strong>"
        else:
            body = text
        out.append(f"<li>{body}</li>")
    out.append("</ul>")
    return out


def _render_section(section, glossary_terms, used_terms) -> str:
    kind = section["kind"]
    enabled = section["key"] in _WRAPPABLE_KEYS

    def wrap(escaped):
        return _wrap_terms(escaped, glossary_terms, used_terms, enabled)

    out = [f'<section class="{_esc(section["key"]).replace("_", "-")}">']
    if section.get("heading"):
        out.append(f'<h2>{_esc(section["heading"])}</h2>')

    if kind == "paragraph":
        out.append(f'<p class="lead">{wrap(_esc(section["text"]))}</p>')

    elif kind == "findings":
        if section["lead"]:
            out.append(f"<p>{wrap(_esc(section['lead']))}</p>")
        if section["items"]:
            out.extend(_render_list(section["items"], wrap))
        if section["diagnoses"]:
            out.append(f'<p class="label"><strong>{_esc(section["diagnoses_label"])}</strong></p>')
            out.extend(_render_list(section["diagnoses"], wrap))
        if section["disposition"]:
            out.append(f"<p>{wrap(_esc(section['disposition']))}</p>")

    elif kind == "list":
        out.extend(_render_list(section["items"], wrap))

    elif kind == "glossary":
        out.append("<dl>")
        for item in section["items"]:
            out.append(f'<dt>{_esc(item["term"])}</dt><dd>{_esc(item["definition"])}</dd>')
        out.append("</dl>")

    out.append("</section>")
    return "\n".join(out)


def render(plan: dict, glossary: dict | None = None) -> str:
    view = plan_view.build_view(plan, glossary=glossary)

    body_parts = [f'<h1>{_esc(view["title"])}</h1>']

    glossary_terms = _glossary_patterns(view)
    if glossary_terms:
        body_parts.append(
            '<p class="interactive-hint">Tap or focus a highlighted word for its definition.</p>'
        )
    used_terms: set[str] = set()

    for section in view["sections"]:
        body_parts.append(_render_section(section, glossary_terms, used_terms))

    plugin_version = plan.get("plugin_version") or runlog.plugin_version()
    body_parts.append(
        f"<footer>Made with simplify-med {_esc(plugin_version)}. "
        "This is a reading aid, not medical advice.</footer>"
    )

    template = Template(_read_template())
    return template.substitute(title=_esc(view["title"]), body="\n".join(body_parts))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a final plan to a self-contained HTML report (on request only)."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--plan", default=None, help=f"Path to the plan JSON (default: <run-dir>/{plan_view.FINAL_PLAN_NAME})"
    )
    parser.add_argument(
        "--glossary", default=None, help=f"Optional glossary JSON (default: <run-dir>/{GLOSSARY_NAME} when present)"
    )
    parser.add_argument("--out", default=None, help="Output path (default: <run-dir>/report.html)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    plan_path = args.plan or os.path.join(args.run_dir, plan_view.FINAL_PLAN_NAME)
    if not os.path.isfile(plan_path):
        print(
            f"render_html: cannot find {plan_path} -- run finalize.py first.",
            file=sys.stderr,
        )
        return 1

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        plan_view.assert_renderable_plan(plan, args.run_dir, plan_path)
        glossary_path = args.glossary or os.path.join(args.run_dir, GLOSSARY_NAME)
        glossary = None
        if os.path.isfile(glossary_path):
            with open(glossary_path, "r", encoding="utf-8") as f:
                glossary = json.load(f)
            glossary_errors = validate.validate(glossary, validate.load_schema("glossary"))
            if glossary_errors:
                raise ValueError("invalid optional glossary: " + "; ".join(glossary_errors))
            if glossary.get("run_id") != plan.get("run_id"):
                raise ValueError("optional glossary does not belong to the finalized plan")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"render_html: {error}", file=sys.stderr)
        return 1

    out_path = args.out or os.path.join(args.run_dir, "report.html")
    text = render(plan, glossary=glossary)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    if os.path.isfile(os.path.join(args.run_dir, "run.json")):
        relative_output = os.path.relpath(out_path, args.run_dir)
        artifacts = [] if relative_output == ".." or relative_output.startswith(".." + os.sep) else [relative_output]
        runlog.record(
            args.run_dir,
            "render_html",
            "ok",
            checks={"glossary_terms": len((glossary or {}).get("terms", []))},
            artifacts=artifacts,
            run_id=plan.get("run_id"),
        )

    print(f"OK wrote {out_path}")
    print(f"render_html: ok | path={out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
