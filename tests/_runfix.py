"""Shared schema-v2 run fixtures for integration and renderer tests."""

from __future__ import annotations

import copy
import json
import os

import numeric_parity
import runlog
import settle_review
from _version import SCHEMA_VERSION

NOTE_LINES = (
    "You came in for chest pain.",
    "Start metoprolol 25 mg twice daily.",
    "Follow up with Dr. Alok Singh in 3 months.",
    "Call 911 for severe chest pain.",
    "All adults should exercise regularly.",
)
NOTE_TEXT = "\n".join(NOTE_LINES) + "\n"
PII_NAME = "Dr. Alok Singh"
OMITTED_MARKER = "All adults should exercise regularly."

CORE_ARTIFACTS_ONE_CHUNK = (
    "run.json",
    "01_units.json",
    "01_units.1.txt",
    "02_facts.1.raw.json",
    "02_facts.json",
    "03_plan.raw.json",
    "03_plan.draft.json",
    "03_flags.json",
    "04_review.raw.json",
    "04_review.json",
    "05_plan.settled.json",
    "06_plan.final.json",
    "report.md",
)

REQUIRED_CORE_STAGES = (
    "unitize",
    "ground",
    "assemble",
    "plan_check",
    "numeric_parity",
    "review",
    "settle_review",
)


def write_json(path: str, document: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def facts_raw_for_units(units: list[dict]) -> dict:
    categories = (
        "reason_for_visit",
        "medications",
        "follow_up",
        "warning_signs",
        "other",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "facts": [
            {
                "category": categories[(unit["id"] - 1) % len(categories)],
                "unit_id": unit["id"],
                "quote": unit["text"],
                "text": unit["text"],
            }
            for unit in units
        ],
    }


def plan_raw(
    facts: list[dict],
    *,
    include_supporting: bool = False,
    omission_reason: str = "generic_not_patient_specific",
) -> dict:
    ids = {fact["category"]: fact["id"] for fact in facts}
    omitted = [] if include_supporting else [
        {"fact_id": ids["other"], "reason": omission_reason},
    ]
    other = [] if omitted else [{
        "title": "Additional information",
        "why": None,
        "steps": [],
        "description": next(fact["text"] for fact in facts if fact["id"] == ids["other"]),
        "frequency": "",
        "duration": "",
        "status": "to_do",
        "source_fact_ids": [ids["other"]],
    }]
    return {
        "summary": "You came in for chest pain and will start metoprolol.",
        "summary_fact_ids": [ids["reason_for_visit"], ids["medications"]],
        "reason_for_visit": [{
            "reason": "Chest pain",
            "description": "You came in for chest pain.",
            "source_fact_ids": [ids["reason_for_visit"]],
        }],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [],
        },
        "medications": [{
            "title": "Metoprolol",
            "plain_name": "metoprolol",
            "why": "For chest pain.",
            "dosage": "25 mg",
            "frequency": "twice daily",
            "timing": "",
            "duration": "",
            "instructions": "Start this medicine.",
            "side_effects_to_watch": "",
            "change": "Start",
            "status": "to_do",
            "source_fact_ids": [ids["medications"]],
        }],
        "tests": [],
        "procedures": [],
        "other": other,
        "follow_up": [{
            "time_frame": "3 months",
            "description": f"Follow up with {PII_NAME} in 3 months.",
            "status": "to_do",
            "source_fact_ids": [ids["follow_up"]],
        }],
        "warning_signs": [{
            "symptom": "Severe chest pain",
            "what_it_might_mean": "",
            "what_to_do": "Call 911.",
            "urgency": "emergency",
            "related_to": "Chest pain",
            "source_fact_ids": [ids["warning_signs"]],
        }],
        "questions": [{
            "question": "When should I return for follow-up?",
            "source_fact_ids": [ids["follow_up"]],
        }],
        "omitted_facts": omitted,
    }


def review_raw(draft: dict, facts: list[dict], flags: dict, *, reassemble_ids=()) -> dict:
    visible_ids = set(draft.get("summary_fact_ids", []))
    for key in ("reason_for_visit", "medications", "tests", "procedures", "other", "follow_up", "warning_signs", "questions"):
        for item in draft.get(key, []):
            visible_ids.update(item.get("source_fact_ids", []))
    for detail in draft.get("diagnosis", {}).get("details", []):
        visible_ids.update(detail.get("source_fact_ids", []))
    visible_ids.update(draft.get("diagnosis", {}).get("changed_since_last_visit_fact_ids", []))
    reassemble_ids = set(reassemble_ids)
    fact_reviews = []
    for fact in facts:
        fact_id = fact["id"]
        if fact_id in reassemble_ids:
            result = "must_include"
        elif fact_id in visible_ids:
            result = "visible_accurate"
        else:
            result = "omission_acceptable"
        fact_reviews.append({"fact_id": fact_id, "result": result})
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "reviewed_fact_ids": [fact["id"] for fact in facts],
        "fact_reviews": fact_reviews,
        "corrections": [],
        "numeric_resolutions": [
            {"flag_id": flag["flag_id"], "resolution": "equivalent"}
            for flag in flags["numeric_parity"]
        ],
        "reassemble_fact_ids": sorted(reassemble_ids),
    }


def make_run_dir(run_dir: str) -> str:
    """Create a complete, valid schema-v2 run through settlement."""
    run_id = os.path.basename(os.path.normpath(run_dir))
    plugin_version = runlog.plugin_version()
    os.makedirs(run_dir, exist_ok=True)
    input_dir = os.path.join(run_dir, "00_input")
    os.makedirs(input_dir, exist_ok=True)
    with open(os.path.join(input_dir, "note.txt"), "w", encoding="utf-8") as handle:
        handle.write(NOTE_TEXT)

    units = [
        {
            "id": index,
            "file": "note.txt",
            "page": 1,
            "line": index,
            "text": text,
            "extraction_method": "native",
        }
        for index, text in enumerate(NOTE_LINES, start=1)
    ]
    units_document = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "run_id": run_id,
        "units": units,
        "chunks": [{"k": 1, "first_id": 1, "last_id": len(units)}],
    }
    write_json(os.path.join(run_dir, "01_units.json"), units_document)
    with open(os.path.join(run_dir, "01_units.1.txt"), "w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(f"[{unit['id']}] {unit['text']}\n")

    raw_facts = facts_raw_for_units(units)
    write_json(os.path.join(run_dir, "02_facts.1.raw.json"), raw_facts)
    facts = [
        {
            "id": index,
            "category": raw["category"],
            "unit_id": raw["unit_id"],
            "quote": raw["quote"],
            "char_start": 0,
            "char_end": len(raw["quote"]),
            "text": raw["text"],
        }
        for index, raw in enumerate(raw_facts["facts"], start=1)
    ]
    facts_document = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "run_id": run_id,
        "facts": facts,
        "dropped": [],
    }
    write_json(os.path.join(run_dir, "02_facts.json"), facts_document)

    raw_plan = plan_raw(facts)
    write_json(os.path.join(run_dir, "03_plan.raw.json"), raw_plan)
    draft = copy.deepcopy(raw_plan)
    draft.update({
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "meta": {
            "run_id": run_id,
            "plugin_version": plugin_version,
            "schema_version": SCHEMA_VERSION,
            "level": "standard",
            "created_at": "2026-09-26T00:00:00+00:00",
        },
    })
    write_json(os.path.join(run_dir, "03_plan.draft.json"), draft)
    flags = numeric_parity.build_numeric_flags(
        draft, facts_document, run_id=run_id, plugin_version=plugin_version,
    )
    write_json(os.path.join(run_dir, "03_flags.json"), flags)
    raw_review = review_raw(draft, facts, flags)
    write_json(os.path.join(run_dir, "04_review.raw.json"), raw_review)

    runlog.initialize(run_dir, run_id, [{
        "file": "note.txt",
        "extraction_method": "native",
        "pages": 1,
        "sha256": "fixture",
    }])
    runlog.record(
        run_dir, "unitize", "ok", attempts=1,
        artifacts=["00_input/note.txt", "01_units.json", "01_units.1.txt"],
        run_id=run_id,
    )
    runlog.record(
        run_dir, "ground", "ok", attempts=1,
        checks={"chunks_expected": 1, "chunks_found": 1, "facts_kept": len(facts), "missing_chunks": []},
        artifacts=["02_facts.1.raw.json", "02_facts.json"], run_id=run_id,
    )
    runlog.record(
        run_dir, "assemble", "ok", attempts=1,
        artifacts=["03_plan.raw.json"], run_id=run_id,
    )
    runlog.record(
        run_dir, "plan_check", "ok", attempts=1,
        artifacts=["03_plan.draft.json"], run_id=run_id,
    )
    runlog.record(
        run_dir, "numeric_parity", "ok", attempts=1,
        artifacts=["03_flags.json"], run_id=run_id,
    )
    runlog.record(
        run_dir, "review", "ok", attempts=1, started=True, finished=False,
        artifacts=["04_review.raw.json"], run_id=run_id,
    )
    if settle_review.main(["--run-dir", run_dir]) != 0:
        raise AssertionError("shared schema-v2 fixture failed settlement")
    return run_id
