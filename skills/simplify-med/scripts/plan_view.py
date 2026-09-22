#!/usr/bin/env python3
"""Renderer-neutral view model for a final care plan.

`build_view(plan)` turns a validated final plan dict into an ordered list
of sections so `render_md.py` and `render_html.py` share one ordering and
content-selection logic instead of each re-deriving it. `visible_text(plan)`
gives the flat patient-visible text used for glossary re-detection and the
after-readability score.

Nothing here ever surfaces `low_priority`, any `*_fact_ids` field, `meta`,
or `run_id` -- those are audit-trail-only and belong to `render_audit.py`,
which reads the plan directly instead of going through this view.

Stdlib only. Importable as `plan_view`.
"""

from __future__ import annotations

SEVERITY_LABELS = {"high": "Serious", "medium": "Moderate", "low": "Minor", None: ""}
URGENCY_LABELS = {
    "emergency": "Emergency",
    "call_doctor": "Call your doctor",
    "monitor": "Keep an eye on it",
    "normal_side_effect": "Normal side effect",
    None: "",
}
URGENCY_ORDER = ["emergency", "call_doctor", "monitor", "normal_side_effect", None]
TYPE_PRECEDENCE = ["medication", "test", "procedure", "appointment", "instruction"]
TYPE_LABELS = {
    "medication": "Medication",
    "test": "Test",
    "procedure": "Procedure",
    "appointment": "Appointment",
    "instruction": "Instruction",
}
# Maps a next-steps row's type to the plan section (and therefore the
# `key` prefix) it came from, so a row's key stays stable regardless of
# how todo/done groups sort it.
_SECTION_FOR_TYPE = {
    "medication": "medications",
    "test": "tests",
    "procedure": "procedures",
    "appointment": "follow_up",
    "instruction": "other",
}


def _not_stated_why(why):
    return why if why else "not stated in your note"


def _join_nonempty(parts, sep=", "):
    return sep.join(p for p in parts if p)


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


# --- section builders -------------------------------------------------

def _section_summary(plan):
    text = plan.get("summary", "")
    if not text:
        return None
    return {"key": "summary", "heading": "What you need to know", "kind": "paragraph", "text": text}


def _section_reason(plan):
    rows = []
    for item in plan.get("reason_for_visit", []) or []:
        reason = item.get("reason", "") or ""
        desc = item.get("description", "") or ""
        text = reason + (f": {desc}" if desc else "")
        if text:
            rows.append({"text": text})
    if not rows:
        return None
    return {"key": "reason", "heading": "Why you were seen", "kind": "list", "items": rows}


def _section_findings(plan):
    diagnosis = plan.get("diagnosis", {}) or {}
    details = diagnosis.get("details", []) or []
    items = []
    for d in details:
        items.append({
            "title": d.get("title", "") or "",
            "plain_name": d.get("plain_name", "") or "",
            "description": d.get("description", "") or "",
            "what_it_means": d.get("what_it_means_for_you", "") or "",
            "severity_label": SEVERITY_LABELS.get(d.get("severity"), ""),
        })
    changed = diagnosis.get("changed_since_last_visit", "") or ""
    if not items and not changed:
        return None
    section = {"key": "findings", "heading": "What the doctor found", "kind": "findings", "items": items}
    if changed:
        section["changed"] = f"What changed since last time: {changed}"
    return section


def _med_row(item):
    title = item.get("title", "") or ""
    plain = item.get("plain_name", "") or ""
    if plain and plain != title:
        title = f"{title} ({plain})"
    detail = _join_nonempty([item.get("dosage", ""), item.get("frequency", ""),
                              item.get("timing", ""), item.get("duration", "")])
    sub = [f"Why: {_not_stated_why(item.get('why'))}"]
    if item.get("instructions"):
        sub.append(f"Instructions: {item['instructions']}")
    if item.get("side_effects_to_watch"):
        sub.append(f"Side effects to watch for: {item['side_effects_to_watch']}")
    if item.get("change"):
        sub.append(f"Change: {item['change']}")
    return title, detail, sub


def _test_row(item):
    title = item.get("title", "") or ""
    plain = item.get("plain_name", "") or ""
    if plain and plain != title:
        title = f"{title} ({plain})"
    detail = item.get("description", "") or ""
    sub = [f"Why: {_not_stated_why(item.get('why'))}"]
    if item.get("preparation"):
        sub.append(f"How to prepare: {item['preparation']}")
    return title, detail, sub


def _procedure_row(item):
    title = item.get("title", "") or ""
    plain = item.get("plain_name", "") or ""
    if plain and plain != title:
        title = f"{title} ({plain})"
    detail = item.get("what_to_expect", "") or ""
    sub = [f"Why: {_not_stated_why(item.get('why'))}"]
    if item.get("timeframe"):
        sub.append(f"When: {item['timeframe']}")
    return title, detail, sub


def _follow_up_row(item):
    title = "Appointment"
    time_frame = item.get("time_frame", "") or ""
    desc = item.get("description", "") or ""
    detail = time_frame + (f" — {desc}" if desc else "")
    return title, detail, []


def _other_row(item):
    title = item.get("title", "") or ""
    detail = item.get("description", "") or ""
    sub = [f"Why: {_not_stated_why(item.get('why'))}"]
    for i, step in enumerate(item.get("steps", []) or [], start=1):
        sub.append(f"Step {i}: {step}")
    if item.get("frequency"):
        sub.append(f"How often: {item['frequency']}")
    if item.get("duration"):
        sub.append(f"For how long: {item['duration']}")
    return title, detail, sub


_ROW_BUILDERS = {
    "medication": _med_row,
    "test": _test_row,
    "procedure": _procedure_row,
    "appointment": _follow_up_row,
    "instruction": _other_row,
}
_SOURCE_FIELDS = {
    "medication": "medications",
    "test": "tests",
    "procedure": "procedures",
    "appointment": "follow_up",
    "instruction": "other",
}


def _section_next_steps(plan):
    todo = []
    done = []
    order = {t: i for i, t in enumerate(TYPE_PRECEDENCE)}

    for type_key in TYPE_PRECEDENCE:
        field = _SOURCE_FIELDS[type_key]
        builder = _ROW_BUILDERS[type_key]
        for idx, item in enumerate(plan.get(field, []) or []):
            title, detail, sub = builder(item)
            row = {
                "type_label": TYPE_LABELS[type_key],
                "title": title,
                "detail": detail,
                "sub": sub,
                "checked": item.get("status") == "done",
                "key": f"{_SECTION_FOR_TYPE[type_key]}-{idx}",
            }
            (done if row["checked"] else todo).append((order[type_key], row))

    if not todo and not done:
        return None

    todo_rows = [row for _, row in sorted(todo, key=lambda pair: pair[0])]
    done_rows = [row for _, row in sorted(done, key=lambda pair: pair[0])]
    return {
        "key": "next_steps", "heading": "Your next steps", "kind": "next_steps",
        "todo": todo_rows, "done": done_rows,
    }


def _section_watch(plan):
    items = plan.get("warning_signs", []) or []
    if not items:
        return None
    order = {u: i for i, u in enumerate(URGENCY_ORDER)}
    indexed = list(enumerate(items))
    indexed.sort(key=lambda pair: (order.get(pair[1].get("urgency"), len(URGENCY_ORDER)), pair[0]))
    rows = []
    for _, item in indexed:
        rows.append({
            "symptom": item.get("symptom", "") or "",
            "what_to_do": item.get("what_to_do", "") or "",
            "what_it_might_mean": item.get("what_it_might_mean", "") or "",
            "related_to": item.get("related_to", "") or "",
            "urgency_label": URGENCY_LABELS.get(item.get("urgency"), ""),
        })
    return {"key": "watch", "heading": "What to watch for", "kind": "watch", "items": rows}


def _section_questions(plan):
    qs = [q for q in (plan.get("questions", []) or []) if q]
    if not qs:
        return None
    items = [{"n": i, "text": q} for i, q in enumerate(qs, start=1)]
    return {"key": "questions", "heading": "Questions to ask your doctor", "kind": "numbered", "items": items}


def _section_glossary(plan):
    terms = plan.get("terms", {}) or {}
    if not terms:
        return None
    items = sorted(
        ({"term": term, "definition": (data or {}).get("definition", "") or ""}
         for term, data in terms.items()),
        key=lambda t: t["term"].lower(),
    )
    return {"key": "glossary", "heading": "Medical terms explained", "kind": "glossary", "items": items}


_SECTION_BUILDERS = (
    _section_summary, _section_reason, _section_findings,
    _section_next_steps, _section_watch, _section_questions, _section_glossary,
)


def build_view(plan: dict) -> dict:
    notices = list(plan.get("notices", []) or [])
    sections = []
    for builder in _SECTION_BUILDERS:
        section = builder(plan)
        if section:
            sections.append(section)

    view = {
        "title": "Your visit, explained",
        "notices": notices,
        "sections": sections,
    }
    line = score_line(plan.get("score"))
    if line:
        view["score_line"] = line
    return view


# --- visible text -------------------------------------------------------

def _texts_for_section(section):
    kind = section["kind"]
    texts = []
    if kind == "paragraph":
        texts.append(section["text"])
    elif kind == "list":
        texts.extend(item["text"] for item in section["items"])
    elif kind == "findings":
        for item in section["items"]:
            texts.append(item.get("title", ""))
            texts.append(item.get("plain_name", ""))
            texts.append(item.get("description", ""))
            texts.append(item.get("what_it_means", ""))
        if "changed" in section:
            texts.append(section["changed"])
    elif kind == "next_steps":
        for group in (section["todo"], section["done"]):
            for row in group:
                texts.append(row["title"])
                texts.append(row["detail"])
                texts.extend(row["sub"])
    elif kind == "watch":
        for row in section["items"]:
            texts.append(row.get("symptom", ""))
            texts.append(row.get("what_to_do", ""))
            texts.append(row.get("what_it_might_mean", ""))
            texts.append(row.get("related_to", ""))
    elif kind == "numbered":
        texts.extend(item["text"] for item in section["items"])
    # kind == "glossary": excluded from visible_text by design.
    return [t for t in texts if t]


def visible_text(plan: dict) -> str:
    """All patient-visible strings of `plan`, in view order, joined by
    blank lines. Excludes glossary definitions and notices."""
    view = build_view(plan)
    parts = []
    for section in view["sections"]:
        if section["key"] == "glossary":
            continue
        parts.extend(_texts_for_section(section))
    return "\n\n".join(parts)
