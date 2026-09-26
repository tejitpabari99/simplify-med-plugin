#!/usr/bin/env python3
"""Renderer-neutral view model for a final plan (schema 3.0).

`build_view(plan)` turns a final plan dict into a title and an ordered list
of sections so `render_md.py`, `render_html.py`, and `render_audit.py`
share one ordering, one set of headings, and one content-selection logic.
`visible_text(plan)` gives the flat patient-visible text (built on
`plan_paths.visible_strings`) used for the word count, the readability
score, and glossary re-detection.

Section order and headings follow the PRD target report: lead paragraph,
"What did they find?" (findings lead, findings, diagnoses, disposition),
"What should you do now?" (next steps, then medicines), return
precautions, questions. Empty slots are hidden. Nothing here surfaces
unit ids, coverage, notices, scores, or run identifiers; those belong only
in the audit view.

Stdlib only. Importable as `plan_view`.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_paths  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402

FINAL_PLAN_NAME = "05_plan.final.json"

TITLES = {
    "er_visit": "Your ER visit, simplified",
    "hospital_stay": "Your hospital stay, simplified",
    "clinic_visit": "Your visit, simplified",
    "test_results": "Your test results, simplified",
    "procedure": "Your procedure, simplified",
    "other": "Your documents, simplified",
}
DEFAULT_TITLE = TITLES["clinic_visit"]

FINDINGS_HEADING = "What did they find?"
NEXT_STEPS_HEADING = "What should you do now?"
QUESTIONS_HEADING = "Questions you may want to ask"
GLOSSARY_HEADING = "Medical terms explained"
_ER_RETURN_HEADING = "When should you go back to the ER?"
_OTHER_RETURN_HEADING = "When to get help right away"
_ER_DIAGNOSES_LABEL = "The ER diagnosed you with:"
_OTHER_DIAGNOSES_LABEL = "Diagnosed with:"

_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9]")
_NAME_TOKEN_RE = re.compile(r"[a-z0-9]+")


def title_for(visit_type: str | None) -> str:
    return TITLES.get(visit_type or "", DEFAULT_TITLE)


def return_heading(visit_type: str | None) -> str:
    return _ER_RETURN_HEADING if visit_type in ("er_visit", "hospital_stay") else _OTHER_RETURN_HEADING


def diagnoses_label(visit_type: str | None) -> str:
    return _ER_DIAGNOSES_LABEL if visit_type == "er_visit" else _OTHER_DIAGNOSES_LABEL


def score_line(score: dict | None) -> str | None:
    """"Reading level: grade X before, grade Y after." Omitted (None) if
    `after_grade` is missing; "about grade Y" if only `before_grade` is
    missing."""
    if not score:
        return None
    before = score.get("before_grade")
    after = score.get("after_grade")
    if after is None:
        return None
    if before is None:
        return f"Reading level: about grade {after}."
    return f"Reading level: grade {before} before, grade {after} after."


# --- item display -------------------------------------------------------

def _name_tokens(text: str) -> list[str]:
    return sorted(_NAME_TOKEN_RE.findall((text or "").lower()))


def plain_name_adds_meaning(name: str, plain_name: str | None) -> bool:
    """True when `plain_name` is non-empty and is not just `name` again
    (ignoring case, punctuation, and word order)."""
    if not plain_name or not plain_name.strip():
        return False
    return _name_tokens(plain_name) != _name_tokens(name)


def diagnosis_text(item: dict) -> str:
    name = (item.get("name") or "").strip()
    plain = (item.get("plain_name") or "").strip()
    if plain_name_adds_meaning(name, plain):
        return f"{name} ({plain})"
    return name


def _text(item: dict | None, field: str = "text") -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get(field)
    return value.strip() if isinstance(value, str) else ""


def item_row(path: str, item: dict) -> dict:
    """The displayed row for one visible item: `label` (bold lead-in,
    possibly empty) and `text`. `path` is the plan_paths item path."""
    kind = path.split("[", 1)[0]
    if kind == "findings":
        return {"path": path, "label": _text(item, "name"), "text": _text(item, "result")}
    if kind == "diagnoses":
        return {"path": path, "label": "", "text": diagnosis_text(item)}
    if kind == "medicines.items":
        return {"path": path, "label": _text(item, "name"), "text": _text(item)}
    if kind == "questions":
        return {"path": path, "label": "", "text": _text(item, "question")}
    return {"path": path, "label": "", "text": _text(item)}


def row_plain_text(row: dict) -> str:
    """"Label: text" (or just text) without markup, for audit and tests."""
    if row["label"] and row["text"]:
        return f"{row['label']}: {row['text']}"
    return row["label"] or row["text"]


def _rows(plan: dict, prefix: str) -> list[dict]:
    rows = []
    for path, item in plan_paths.visible_items(plan):
        if path.split("[", 1)[0] != prefix:
            continue
        row = item_row(path, item)
        if row["label"] or row["text"]:
            rows.append(row)
    return rows


# --- section builders -------------------------------------------------

def _section_why(plan):
    text = _text(plan.get("why_you_went"))
    if not text:
        return None
    return {"key": "why_you_went", "heading": None, "kind": "paragraph", "text": text}


def _section_findings(plan):
    lead = _text(plan.get("findings_lead"))
    items = _rows(plan, "findings")
    diagnoses = _rows(plan, "diagnoses")
    disposition = _text(plan.get("disposition"))
    if not (lead or items or diagnoses or disposition):
        return None
    return {
        "key": "findings",
        "heading": FINDINGS_HEADING,
        "kind": "findings",
        "lead": lead,
        "items": items,
        "diagnoses_label": diagnoses_label(plan.get("visit_type")),
        "diagnoses": diagnoses,
        "disposition": disposition,
    }


def _section_next_steps(plan):
    items = _rows(plan, "next_steps") + _rows(plan, "medicines.items") + _rows(plan, "medicines.none_statement")
    if not items:
        return None
    return {"key": "next_steps", "heading": NEXT_STEPS_HEADING, "kind": "list", "items": items}


def _section_return(plan):
    items = _rows(plan, "return_precautions")
    if not items:
        return None
    return {
        "key": "return_precautions",
        "heading": return_heading(plan.get("visit_type")),
        "kind": "list",
        "items": items,
    }


def _section_questions(plan):
    items = _rows(plan, "questions")
    if not items:
        return None
    return {"key": "questions", "heading": QUESTIONS_HEADING, "kind": "list", "items": items}


def _section_glossary(glossary):
    if not isinstance(glossary, dict) or not isinstance(glossary.get("terms"), list):
        return None
    items = [
        {"term": item.get("term", "") or "", "definition": item.get("definition", "") or ""}
        for item in glossary["terms"]
        if item.get("term") and item.get("definition")
    ]
    items.sort(key=lambda item: item["term"].lower())
    if not items:
        return None
    return {"key": "glossary", "heading": GLOSSARY_HEADING, "kind": "glossary", "items": items}


_SECTION_BUILDERS = (
    _section_why, _section_findings, _section_next_steps, _section_return, _section_questions,
)


def build_view(plan: dict, glossary: dict | None = None) -> dict:
    """Title plus ordered, non-empty sections. The glossary section is added
    only when a validated glossary document is passed explicitly."""
    sections = []
    for builder in _SECTION_BUILDERS:
        section = builder(plan)
        if section:
            sections.append(section)
    glossary_section = _section_glossary(glossary)
    if glossary_section:
        sections.append(glossary_section)
    return {"title": title_for(plan.get("visit_type")), "sections": sections}


def assert_renderable_plan(plan: dict, run_dir: str, plan_path: str) -> None:
    """Refuse anything but a finalized schema-3.0 plan whose run log records
    a successful `finalize` for the same run."""
    label = "completed final report"
    if os.path.basename(plan_path) != FINAL_PLAN_NAME or plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"rendering requires a {label}")
    try:
        with open(os.path.join(run_dir, "run.json"), "r", encoding="utf-8") as handle:
            run_log = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"rendering requires a {label}") from error
    stages = run_log.get("stages") if isinstance(run_log, dict) else None
    if (((stages or {}).get("finalize")) or {}).get("status") != "ok":
        raise ValueError(f"rendering requires a {label}")
    plan_run_id = plan.get("run_id")
    run_log_id = run_log.get("run_id")
    if plan_run_id and run_log_id and plan_run_id != run_log_id:
        raise ValueError("final plan and run log identities do not match")


# --- visible text -------------------------------------------------------

def _shown(plan: dict, field_path: str, text: str) -> bool:
    """False for a diagnosis `plain_name` the renderers hide as a duplicate."""
    if not field_path.endswith(".plain_name"):
        return True
    item_path = field_path.rsplit(".", 1)[0]
    item = dict(plan_paths.visible_items(plan)).get(item_path) or {}
    return plain_name_adds_meaning(item.get("name") or "", text)


def visible_text(plan: dict) -> str:
    """All patient-visible strings of `plan`, in report order, joined by
    blank lines. Excludes headings, glossary definitions, and metadata."""
    return "\n\n".join(
        text.strip()
        for field_path, text, _unit_ids in plan_paths.visible_strings(plan)
        if _shown(plan, field_path, text)
    )


def word_count(plan: dict) -> int:
    """Words in `visible_text(plan)`: whitespace tokens with a letter or digit."""
    return sum(1 for token in visible_text(plan).split() if _WORD_CHAR_RE.search(token))
