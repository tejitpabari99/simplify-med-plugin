"""Shared fixture builder for finalize/render tests.

`make_run_dir(run_dir)` populates an already-created temp directory with a
consistent, internally-linked run: input text, units, a verified fact
ledger, a glossary, a draft care plan, coverage, and additions, plus a
run.json with unitize/ground/assemble already recorded ok. Every test
module that needs a realistic run directory for finalize/render should
build one with this instead of hand-rolling its own.
"""

from __future__ import annotations

import json
import os

import runlog

NOTE_TEXT = (
    "Patient presents with chest pain for two weeks and shortness of breath during exertion.\n"
    "Vital signs stable; blood pressure elevated at one hundred fifty over ninety five today.\n"
    "Diagnosis: hypertension stage two, discussed treatment options with the patient at length.\n"
    "Start metoprolol twenty five milligrams by mouth twice daily for blood pressure control.\n"
    "Continue lisinopril ten milligrams once daily as previously prescribed by cardiology team.\n"
    "Order complete blood count and basic metabolic panel prior to the next visit.\n"
    "Schedule an echocardiogram to evaluate cardiac function within the next thirty days.\n"
    "Reduce sodium intake to less than two thousand milligrams per day starting immediately.\n"
    "Follow up with primary care in three months to reassess blood pressure control.\n"
    "Call 911 immediately if chest pain worsens or becomes severe at any time.\n"
    "Seek care if you notice swelling in your legs that does not go away.\n"
    "This visit note was reviewed and signed by Dr. Alok Singh before discharge today.\n"
)

UNIT_LINES = [line for line in NOTE_TEXT.split("\n") if line]

# A distinctive marker used to assert low_priority items never reach any
# patient-facing renderer.
LOW_PRIORITY_MARKER = "ROUTINE-LOW-PRIORITY-MARKER"

# A glossary term deliberately absent from the plan text, to exercise the
# finalize-time re-detection drop.
ABSENT_GLOSSARY_TERM = "nephrology"

PII_NAME = "Dr. Alok Singh"


def _write(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def make_run_dir(run_dir: str) -> str:
    """Populate `run_dir` (must already exist) with the fixture run.
    Returns the run id used (the directory's basename)."""
    run_id = os.path.basename(os.path.normpath(run_dir))

    input_dir = os.path.join(run_dir, "00_input")
    os.makedirs(input_dir, exist_ok=True)
    with open(os.path.join(input_dir, "note.txt"), "w", encoding="utf-8") as f:
        f.write(NOTE_TEXT)

    units = [
        {"id": i + 1, "file": "note.txt", "page": 1, "line": i + 1,
         "text": text, "extraction_method": "native"}
        for i, text in enumerate(UNIT_LINES)
    ]
    _write(os.path.join(run_dir, "01_units.json"), {
        "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
        "units": units,
        "chunks": [{"k": 1, "first_id": 1, "last_id": len(units)}],
    })

    facts = [
        {"id": 1, "category": "reason_for_visit", "unit_id": 1,
         "quote": "chest pain for two weeks", "char_start": 0, "char_end": 25,
         "text": UNIT_LINES[0]},
        {"id": 2, "category": "diagnosis", "unit_id": 3,
         "quote": "hypertension stage two", "char_start": 0, "char_end": 23,
         "text": UNIT_LINES[2]},
        {"id": 3, "category": "medications", "unit_id": 4,
         "quote": "metoprolol twenty five milligrams", "char_start": 0, "char_end": 34,
         "text": UNIT_LINES[3]},
        {"id": 4, "category": "medications", "unit_id": 5,
         "quote": "lisinopril ten milligrams", "char_start": 0, "char_end": 26,
         "text": UNIT_LINES[4]},
        {"id": 5, "category": "tests", "unit_id": 6,
         "quote": "complete blood count and basic metabolic panel", "char_start": 0, "char_end": 48,
         "text": UNIT_LINES[5]},
        {"id": 6, "category": "procedures", "unit_id": 7,
         "quote": "echocardiogram to evaluate cardiac function", "char_start": 0, "char_end": 45,
         "text": UNIT_LINES[6]},
        {"id": 7, "category": "follow_up", "unit_id": 9,
         "quote": "follow up with primary care in three months", "char_start": 0, "char_end": 45,
         "text": UNIT_LINES[8]},
        {"id": 8, "category": "warning_signs", "unit_id": 10,
         "quote": "call 911 immediately if chest pain worsens", "char_start": 0, "char_end": 44,
         "text": UNIT_LINES[9]},
    ]
    _write(os.path.join(run_dir, "02_facts.json"), {
        "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
        "facts": facts, "dropped": [],
    })

    _write(os.path.join(run_dir, "02_glossary.json"), {
        "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
        "terms": [
            {"term": "Hypertension", "matched_term": "Hypertension",
             "definition": "High blood pressure.", "source": "llm_proposed"},
            {"term": "Echocardiogram", "matched_term": "Echocardiogram",
             "definition": "An ultrasound test of the heart.", "source": "llm_proposed"},
            {"term": "Nephrology", "matched_term": ABSENT_GLOSSARY_TERM,
             "definition": "The medical specialty focused on kidney care.",
             "source": "llm_proposed"},
        ],
    })

    plan = {
        "schema_version": "1.0",
        "plugin_version": "0.1.0",
        "meta": {"run_id": run_id, "plugin_version": "0.1.0", "schema_version": "1.0",
                  "level": "standard", "created_at": "2026-09-22T00:00:00+00:00"},
        "notices": [],
        "score": {"before_grade": None, "after_grade": None},
        "summary": "You have chest pain and high blood pressure that need treatment.",
        "summary_fact_ids": [1, 2],
        "reason_for_visit": [
            {"reason": "Chest pain",
             "description": "Chest pain for two weeks with exertional shortness of breath.",
             "source_fact_ids": [1]},
        ],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [
                {"title": "Hypertension", "plain_name": "high blood pressure",
                 "description": f"Diagnosed by {PII_NAME} during today's visit. "
                                 "Hypertension stage two requires treatment.",
                 "what_it_means_for_you": "You will need ongoing treatment.",
                 "severity": "medium", "source_fact_ids": [2]},
            ],
        },
        "medications": [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "25 mg", "frequency": "twice daily", "timing": "", "duration": "",
             "instructions": "Take with food.", "side_effects_to_watch": "Dizziness.",
             "change": "", "status": "to_do", "source_fact_ids": [3]},
            {"title": "Lisinopril", "plain_name": "lisinopril",
             "why": "Prevents further blood pressure complications.",
             "dosage": "10 mg", "frequency": "once daily", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [4]},
        ],
        "tests": [
            {"title": "Blood tests", "plain_name": "", "why": "Confirms overall blood counts.",
             "description": "Complete blood count and basic metabolic panel.",
             "preparation": "", "status": "to_do", "source_fact_ids": [5]},
        ],
        "procedures": [
            {"title": "Echocardiogram", "plain_name": "heart ultrasound",
             "why": "Evaluates heart function.",
             "what_to_expect": "An ultrasound of the heart to check its function.",
             "timeframe": "within 30 days", "status": "done", "source_fact_ids": [6]},
        ],
        "other": [
            {"title": "Diet changes", "why": None,
             "steps": ["Reduce sodium intake to less than 2000 mg per day.",
                       "Monitor blood pressure at home weekly."],
             "description": "Follow the DASH diet guidelines.",
             "frequency": "Daily", "duration": "Ongoing", "status": "to_do",
             "source_fact_ids": [1]},
        ],
        "follow_up": [
            {"time_frame": "3 months", "description": "Reassess blood pressure control.",
             "status": "to_do", "source_fact_ids": [7]},
        ],
        "warning_signs": [
            {"symptom": "Severe chest pain", "what_it_might_mean": "Possible heart attack.",
             "what_to_do": "Call 911 right away.", "urgency": "emergency",
             "related_to": "", "source_fact_ids": [1]},
            {"symptom": "Leg swelling", "what_it_might_mean": "Fluid buildup.",
             "what_to_do": "Mention it at your next visit.", "urgency": "monitor",
             "related_to": "", "source_fact_ids": [2]},
        ],
        "questions": ["Will I need surgery?", "Should I change my diet?"],
        "low_priority": [f"{LOW_PRIORITY_MARKER}: billing code 99213 noted for insurance purposes."],
        "terms": {},
    }
    _write(os.path.join(run_dir, "03_plan.draft.json"), plan)

    _write(os.path.join(run_dir, "04_coverage.json"), {
        "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
        "coverage": [{"fact_id": i, "present": i != 8} for i in range(1, 9)],
        "missing": [8],
    })

    _write(os.path.join(run_dir, "05_additions.json"), {
        "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
        "reason_for_visit": [], "diagnosis_details": [],
        "medications": [
            {"title": "Aspirin", "plain_name": "", "why": "Reduces risk of blood clots.",
             "dosage": "81 mg", "frequency": "once daily", "timing": "", "duration": "",
             "instructions": "Take with food.", "side_effects_to_watch": "",
             "change": "", "status": "to_do", "source_fact_ids": [8]},
        ],
        "tests": [], "procedures": [], "other": [], "follow_up": [], "warning_signs": [],
        "low_priority": [], "dropped": [],
    })

    runlog.record(run_dir, "unitize", "ok")
    runlog.record(run_dir, "ground", "ok")
    runlog.record(run_dir, "assemble", "ok")

    return run_id
