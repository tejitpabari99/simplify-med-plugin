#!/usr/bin/env python3
"""Visible-item paths shared by check_draft, settle, and the renderers.

A draft, settled plan, and final plan share one body shape
(`schema/draft.schema.json`). `visible_items(plan)` lists every
patient-visible item with its path, in report order, so every script
enumerates the same claims the verifier must review.

Stdlib only. Importable as `plan_paths`.
"""

from __future__ import annotations

# Top-level single items (object or null) in report order.
_SINGLE_BEFORE = ("why_you_went", "findings_lead")
_SINGLE_AFTER_DIAGNOSES = ("disposition",)
# Visible string fields per item kind; everything else (unit_ids) is metadata.
TEXT_FIELDS = {
    "why_you_went": ("text",),
    "findings_lead": ("text",),
    "findings": ("name", "result"),
    "diagnoses": ("name", "plain_name"),
    "disposition": ("text",),
    "next_steps": ("text",),
    "medicines.items": ("name", "text"),
    "medicines.none_statement": ("text",),
    "return_precautions": ("text",),
    "questions": ("question",),
}
# Fields a verifier may `clear`: the value becomes null (single items) or "" (plain_name).
CLEARABLE_ITEMS = ("findings_lead", "disposition", "medicines.none_statement")
CLEARABLE_FIELDS = ("plain_name",)


def _kind(path: str) -> str:
    """Map "findings[2]" -> "findings", "medicines.items[0]" -> "medicines.items"."""
    return path.split("[", 1)[0]


def visible_items(plan: dict) -> list[tuple[str, dict]]:
    """Return [(path, item)] for every patient-visible item, in report order."""
    items: list[tuple[str, dict]] = []
    for key in _SINGLE_BEFORE:
        if isinstance(plan.get(key), dict):
            items.append((key, plan[key]))
    for key in ("findings", "diagnoses"):
        for index, item in enumerate(plan.get(key) or []):
            items.append((f"{key}[{index}]", item))
    for key in _SINGLE_AFTER_DIAGNOSES:
        if isinstance(plan.get(key), dict):
            items.append((key, plan[key]))
    for index, item in enumerate(plan.get("next_steps") or []):
        items.append((f"next_steps[{index}]", item))
    medicines = plan.get("medicines") or {}
    for index, item in enumerate(medicines.get("items") or []):
        items.append((f"medicines.items[{index}]", item))
    if isinstance(medicines.get("none_statement"), dict):
        items.append(("medicines.none_statement", medicines["none_statement"]))
    for key in ("return_precautions", "questions"):
        for index, item in enumerate(plan.get(key) or []):
            items.append((f"{key}[{index}]", item))
    return items


def item_texts(path: str, item: dict) -> list[tuple[str, str]]:
    """Return [(field_path, text)] for the visible, non-empty strings of one item."""
    fields = TEXT_FIELDS.get(_kind(path), ())
    return [
        (f"{path}.{field}", item[field])
        for field in fields
        if isinstance(item.get(field), str) and item[field].strip()
    ]


def visible_strings(plan: dict) -> list[tuple[str, str, list[int]]]:
    """Return [(field_path, text, unit_ids)] for every visible string."""
    out = []
    for path, item in visible_items(plan):
        unit_ids = list(item.get("unit_ids") or [])
        for field_path, text in item_texts(path, item):
            out.append((field_path, text, unit_ids))
    return out


def cited_unit_ids(plan: dict) -> set[int]:
    """Every unit id cited by a visible item."""
    return {uid for _path, item in visible_items(plan) for uid in (item.get("unit_ids") or [])}
