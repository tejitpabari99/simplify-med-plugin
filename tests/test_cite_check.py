import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import cite_check  # noqa: E402
import validate  # noqa: E402


FACTS = [
    {"id": 1, "category": "reason_for_visit", "unit_id": 1,
     "quote": "chest pain for two weeks", "char_start": 0, "char_end": 25,
     "text": "Patient presents with chest pain for two weeks."},
    {"id": 2, "category": "medications", "unit_id": 2,
     "quote": "metoprolol 25mg twice daily", "char_start": 0, "char_end": 28,
     "text": "Start metoprolol 25mg twice daily."},
    {"id": 3, "category": "diagnosis", "unit_id": 3,
     "quote": "hypertension, stage 2", "char_start": 0, "char_end": 22,
     "text": "Diagnosis: hypertension, stage 2."},
    {"id": 4, "category": "follow_up", "unit_id": 4,
     "quote": "follow up in 3 months", "char_start": 0, "char_end": 22,
     "text": "Patient to follow up in 3 months."},
    {"id": 5, "category": "tests", "unit_id": 5,
     "quote": "order CBC and BMP", "char_start": 0, "char_end": 18,
     "text": "Order CBC and BMP today."},
    {"id": 6, "category": "warning_signs", "unit_id": 6,
     "quote": "call 911 if chest pain worsens", "char_start": 0, "char_end": 31,
     "text": "Call 911 if chest pain worsens."},
    {"id": 7, "category": "procedures", "unit_id": 7,
     "quote": "schedule an echocardiogram", "char_start": 0, "char_end": 27,
     "text": "Schedule an echocardiogram next week."},
    {"id": 8, "category": "other", "unit_id": 8,
     "quote": "reduce sodium intake to less than 2000 mg per day", "char_start": 0, "char_end": 50,
     "text": "Reduce sodium intake to less than 2000 mg per day."},
]


def _write_facts(run_dir: str, facts=None) -> None:
    data = {
        "schema_version": "1.0",
        "plugin_version": "0.1.0",
        "run_id": os.path.basename(run_dir),
        "facts": facts if facts is not None else FACTS,
        "dropped": [],
    }
    with open(os.path.join(run_dir, "02_facts.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _minimal_valid_raw_plan() -> dict:
    """A raw assemble-agent plan that already validates against
    care_plan_agent.schema.json -- callers mutate a deep copy."""
    return {
        "summary": "You have chest pain and high blood pressure.",
        "summary_fact_ids": [1, 3],
        "reason_for_visit": [
            {"reason": "Chest pain", "description": "You had chest pain for two weeks.",
             "source_fact_ids": [1]},
        ],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [
                {"title": "Hypertension", "plain_name": "high blood pressure",
                 "description": "Stage 2 hypertension.",
                 "what_it_means_for_you": "You need treatment.",
                 "severity": None, "source_fact_ids": [3]},
            ],
        },
        "medications": [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "25 mg", "frequency": "twice a day", "timing": "",
             "duration": "", "instructions": "", "side_effects_to_watch": "",
             "change": "", "status": "to_do", "source_fact_ids": [2]},
        ],
        "tests": [
            {"title": "Blood tests", "plain_name": "", "why": None,
             "description": "CBC and BMP.", "preparation": "", "status": "to_do",
             "source_fact_ids": [5]},
        ],
        "procedures": [
            {"title": "Echocardiogram", "plain_name": "", "why": None,
             "what_to_expect": "", "timeframe": "next week", "status": "to_do",
             "source_fact_ids": [7]},
        ],
        "other": [
            {"title": "Diet change", "why": None, "steps": [],
             "description": "Reduce sodium intake to less than 2000 mg per day.",
             "frequency": "", "duration": "", "status": "to_do",
             "source_fact_ids": [8]},
        ],
        "follow_up": [
            {"time_frame": "3 months", "description": "See your doctor in 3 months.",
             "status": "to_do", "source_fact_ids": [4]},
        ],
        "warning_signs": [
            {"symptom": "Worsening chest pain", "what_it_might_mean": "",
             "what_to_do": "Call 911.", "urgency": "emergency", "related_to": "",
             "source_fact_ids": [6]},
        ],
        "questions": ["Will I need surgery?"],
        "low_priority": [],
    }


class TestCiteCheckAssemble(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = self._tmp.name
        _write_facts(self.run_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_raw(self, plan: dict) -> None:
        _write_json(os.path.join(self.run_dir, "03_plan.raw.json"), plan)

    # --- schema-invalid raw -------------------------------------------------

    def test_schema_invalid_raw_exits_1_with_errors(self):
        plan = _minimal_valid_raw_plan()
        del plan["summary"]  # required by care_plan_agent.schema.json
        self._write_raw(plan)

        script = os.path.join(_paths.SCRIPTS_DIR, "cite_check.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("summary", result.stderr)
        self.assertFalse(os.path.isfile(os.path.join(self.run_dir, "03_plan.draft.json")))

    # --- uncited item dropped per section ------------------------------------

    def test_uncited_item_dropped(self):
        plan = _minimal_valid_raw_plan()
        plan["medications"][0]["source_fact_ids"] = [999]
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)

        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)
        self.assertEqual(draft["medications"], [])

        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as f:
            run_log = json.load(f)
        checks = run_log["stages"]["assemble"]["checks"]
        self.assertEqual(checks["dropped_uncited_by_section"], {"medications": 1})
        self.assertEqual(run_log["stages"]["assemble"]["status"], "degraded")

    def test_uncited_diagnosis_detail_dropped(self):
        plan = _minimal_valid_raw_plan()
        plan["diagnosis"]["details"][0]["source_fact_ids"] = [999]
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)
        self.assertEqual(draft["diagnosis"]["details"], [])

    # --- partial id filtering -------------------------------------------------

    def test_partial_id_filtering_keeps_item(self):
        plan = _minimal_valid_raw_plan()
        plan["medications"][0]["source_fact_ids"] = [2, 999]
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)
        self.assertEqual(len(draft["medications"]), 1)
        self.assertEqual(draft["medications"][0]["source_fact_ids"], [2])

    # --- summary uncited flag -------------------------------------------------

    def test_summary_uncited_flag(self):
        plan = _minimal_valid_raw_plan()
        plan["summary_fact_ids"] = [999]
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)
        # summary text survives even though nothing backs it
        self.assertTrue(draft["summary"])
        self.assertEqual(draft["summary_fact_ids"], [])

        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as f:
            run_log = json.load(f)
        self.assertTrue(run_log["stages"]["assemble"]["checks"]["summary_uncited"])

    # --- questions truncation --------------------------------------------------
    # care_plan_agent.schema.json itself enforces maxItems 3 on `questions`, so
    # a raw plan with 4+ questions never reaches the guard through the full CLI
    # (it is rejected -- correctly -- at the schema-validation step first, and
    # the assemble agent is retried). _apply_guards is exercised directly here
    # to prove the truncation guard itself is correct in isolation / as a
    # defense-in-depth safety net.

    def test_questions_truncated_to_three(self):
        plan = _minimal_valid_raw_plan()
        plan["questions"] = ["Q1?", "Q2?", "Q3?", "Q4?"]
        valid_ids = {f["id"] for f in FACTS}

        guarded, checks = cite_check._apply_guards(plan, valid_ids)
        self.assertEqual(guarded["questions"], ["Q1?", "Q2?", "Q3?"])
        self.assertTrue(checks["questions_truncated"])

    def test_questions_not_truncated_when_within_limit(self):
        plan = _minimal_valid_raw_plan()
        valid_ids = {f["id"] for f in FACTS}
        guarded, checks = cite_check._apply_guards(plan, valid_ids)
        self.assertFalse(checks["questions_truncated"])

    # --- why "" -> null ---------------------------------------------------------

    def test_why_empty_string_becomes_null(self):
        plan = _minimal_valid_raw_plan()
        plan["medications"][0]["why"] = ""
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)
        self.assertIsNone(draft["medications"][0]["why"])

        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as f:
            run_log = json.load(f)
        self.assertEqual(run_log["stages"]["assemble"]["checks"]["why_nulled"], 1)

    # --- status default ----------------------------------------------------------
    # As with `questions`, care_plan_agent.schema.json requires `status` on
    # every actionable item, so a raw plan missing it is rejected at the
    # schema step (and the agent retried) before the CLI ever reaches this
    # guard. Exercise _apply_guards directly.

    def test_status_defaulted_to_to_do(self):
        plan = _minimal_valid_raw_plan()
        del plan["medications"][0]["status"]
        valid_ids = {f["id"] for f in FACTS}

        guarded, checks = cite_check._apply_guards(plan, valid_ids)
        self.assertEqual(guarded["medications"][0]["status"], "to_do")
        self.assertEqual(checks["status_defaulted"], 1)

    # --- draft validates against care_plan.schema.json ---------------------------

    def test_draft_validates_against_care_plan_schema(self):
        plan = _minimal_valid_raw_plan()
        self._write_raw(plan)

        rc = cite_check._run_assemble(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
            draft = json.load(f)

        schema = validate.load_schema("care_plan")
        errors = validate.validate(draft, schema)
        self.assertEqual(errors, [])


class TestCiteCheckAdditions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = self._tmp.name
        _write_facts(self.run_dir)
        _write_json(os.path.join(self.run_dir, "04_coverage.json"), {
            "schema_version": "1.0", "plugin_version": "0.1.0",
            "run_id": os.path.basename(self.run_dir),
            "coverage": [{"fact_id": f["id"], "present": f["id"] != 6} for f in FACTS],
            "missing": [6],
        })

    def tearDown(self):
        self._tmp.cleanup()

    def test_skipped_when_raw_absent(self):
        script = os.path.join(_paths.SCRIPTS_DIR, "cite_check.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir, "--additions"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        with open(os.path.join(self.run_dir, "05_additions.json"), encoding="utf-8") as f:
            additions = json.load(f)
        self.assertEqual(additions["dropped"], [])
        self.assertEqual(additions["medications"], [])

        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as f:
            run_log = json.load(f)
        self.assertEqual(run_log["stages"]["assemble_missing"]["status"], "skipped")

    def test_subset_of_missing_rule(self):
        raw = {
            "reason_for_visit": [], "diagnosis_details": [], "medications": [],
            "tests": [], "procedures": [],
            "other": [], "follow_up": [], "warning_signs": [
                {"symptom": "Worsening chest pain", "what_it_might_mean": "",
                 "what_to_do": "Call 911.", "urgency": "emergency",
                 "related_to": "", "source_fact_ids": [6]},
                {"symptom": "Wrong addition", "what_it_might_mean": "",
                 "what_to_do": "Not actually missing.", "urgency": None,
                 "related_to": "", "source_fact_ids": [1]},
            ],
            "low_priority": [],
        }
        _write_json(os.path.join(self.run_dir, "05_additions.raw.json"), raw)

        rc = cite_check._run_additions(self.run_dir)
        self.assertEqual(rc, 0)

        with open(os.path.join(self.run_dir, "05_additions.json"), encoding="utf-8") as f:
            additions = json.load(f)
        self.assertEqual(len(additions["warning_signs"]), 1)
        self.assertEqual(additions["warning_signs"][0]["source_fact_ids"], [6])
        self.assertEqual(len(additions["dropped"]), 1)
        self.assertEqual(additions["dropped"][0]["reason"], "not_missing")

        schema = validate.load_schema("additions")
        errors = validate.validate(additions, schema)
        self.assertEqual(errors, [])

    def test_uncited_addition_dropped(self):
        raw = {
            "reason_for_visit": [], "diagnosis_details": [],
            "medications": [
                {"title": "Aspirin", "plain_name": "", "why": None, "dosage": "",
                 "frequency": "", "timing": "", "duration": "", "instructions": "",
                 "side_effects_to_watch": "", "change": "", "status": "to_do",
                 "source_fact_ids": []},
            ],
            "tests": [], "procedures": [], "other": [], "follow_up": [],
            "warning_signs": [], "low_priority": [],
        }
        _write_json(os.path.join(self.run_dir, "05_additions.raw.json"), raw)

        rc = cite_check._run_additions(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "05_additions.json"), encoding="utf-8") as f:
            additions = json.load(f)
        self.assertEqual(additions["medications"], [])
        self.assertEqual(additions["dropped"][0]["reason"], "uncited")

    def test_schema_invalid_raw_additions_exits_1(self):
        _write_json(os.path.join(self.run_dir, "05_additions.raw.json"), {"medications": "not-a-list"})
        rc = cite_check._run_additions(self.run_dir)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
