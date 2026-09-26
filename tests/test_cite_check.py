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
     "quote": "start metoprolol 25 mg twice daily", "char_start": 0, "char_end": 36,
     "text": "Start metoprolol 25 mg twice daily."},
    {"id": 3, "category": "diagnosis", "unit_id": 3,
     "quote": "hypertension is worse", "char_start": 0, "char_end": 21,
     "text": "Hypertension is worse than at the last visit."},
    {"id": 4, "category": "follow_up", "unit_id": 4,
     "quote": "follow up in 3 months", "char_start": 0, "char_end": 21,
     "text": "Follow up in 3 months."},
    {"id": 5, "category": "other", "unit_id": 5,
     "quote": "All adults should exercise regularly", "char_start": 0, "char_end": 36,
     "text": "All adults should exercise regularly. This is general education."},
    {"id": 6, "category": "tests", "unit_id": 6,
     "quote": "CT used 75 mL contrast with 1 mm slices", "char_start": 0, "char_end": 40,
     "text": "Technical CT detail: 75 mL contrast and 1 mm slice thickness."},
]


def _facts_document(run_dir: str) -> dict:
    return {
        "schema_version": "2.0",
        "plugin_version": "0.2.0",
        "run_id": os.path.basename(run_dir),
        "facts": copy.deepcopy(FACTS),
        "dropped": [],
    }


def _raw_plan() -> dict:
    return {
        "summary": "You came in for chest pain, and your blood pressure diagnosis is worse.",
        "summary_fact_ids": [1, 3],
        "reason_for_visit": [
            {"reason": "Chest pain", "description": "Chest pain for two weeks.",
             "source_fact_ids": [1]},
        ],
        "diagnosis": {
            "changed_since_last_visit": "Your hypertension is worse than at your last visit.",
            "changed_since_last_visit_fact_ids": [3],
            "details": [
                {"title": "Hypertension", "plain_name": "high blood pressure",
                 "description": "Your hypertension is worse.",
                 "what_it_means_for_you": "Treatment is needed.", "severity": None,
                 "source_fact_ids": [3]},
            ],
        },
        "medications": [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "25 mg", "frequency": "twice daily", "timing": "",
             "duration": "", "instructions": "Start this medicine.",
             "side_effects_to_watch": "", "change": "Start", "status": "to_do",
             "source_fact_ids": [2]},
        ],
        "tests": [],
        "procedures": [],
        "other": [],
        "follow_up": [
            {"time_frame": "3 months", "description": "Return in 3 months.",
             "status": "to_do", "source_fact_ids": [4]},
        ],
        "warning_signs": [],
        "questions": [
            {"question": "What should I expect at the 3-month follow-up?",
             "source_fact_ids": [4]},
        ],
        "omitted_facts": [
            {"fact_id": 5, "reason": "generic_not_patient_specific"},
            {"fact_id": 6, "reason": "technical_detail"},
        ],
    }


class TestPlanAssertions(unittest.TestCase):
    def test_accepts_exhaustive_visible_or_omitted_dispositions(self):
        checks = cite_check.assert_plan_citations(_raw_plan(), FACTS)
        self.assertEqual(checks["facts_total"], 6)
        self.assertEqual(checks["facts_visible"], 4)
        self.assertEqual(checks["facts_omitted"], 2)
        self.assertEqual(checks["questions_cited"], 1)

    def test_rejects_unknown_visible_fact_id(self):
        plan = _raw_plan()
        plan["medications"][0]["source_fact_ids"] = [999]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "unknown fact ID 999"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_unknown_omitted_fact_id(self):
        plan = _raw_plan()
        plan["omitted_facts"][0]["fact_id"] = 999
        with self.assertRaisesRegex(cite_check.PlanCitationError, "unknown omitted fact ID 999"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_duplicate_omission_entries(self):
        plan = _raw_plan()
        plan["omitted_facts"].append({"fact_id": 5, "reason": "routine_non_actionable"})
        with self.assertRaisesRegex(cite_check.PlanCitationError, "omitted more than once"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_visible_and_omitted_overlap(self):
        plan = _raw_plan()
        plan["omitted_facts"].append({"fact_id": 4, "reason": "duplicate_or_already_represented"})
        with self.assertRaisesRegex(cite_check.PlanCitationError, "both visible and omitted"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_uncovered_fact(self):
        plan = _raw_plan()
        plan["omitted_facts"] = plan["omitted_facts"][:1]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "fact ID 6 is uncovered"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_unsupported_summary(self):
        plan = _raw_plan()
        plan["summary_fact_ids"] = []
        with self.assertRaisesRegex(cite_check.PlanCitationError, "summary has content but no citations"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_unsupported_changed_since_content(self):
        plan = _raw_plan()
        plan["diagnosis"]["changed_since_last_visit_fact_ids"] = []
        with self.assertRaisesRegex(cite_check.PlanCitationError, "changed_since_last_visit has content but no citations"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_uncited_question(self):
        plan = _raw_plan()
        plan["questions"][0]["source_fact_ids"] = []
        with self.assertRaisesRegex(cite_check.PlanCitationError, r"questions\[0\] has content but no citations"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_uncited_visible_item(self):
        plan = _raw_plan()
        plan["follow_up"][0]["source_fact_ids"] = []
        with self.assertRaisesRegex(cite_check.PlanCitationError, r"follow_up\[0\] has content but no citations"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_invalid_omission_reason(self):
        plan = _raw_plan()
        plan["omitted_facts"][0]["reason"] = "not_important"
        with self.assertRaisesRegex(cite_check.PlanCitationError, "invalid omission reason"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_critical_fact_hidden_as_routine(self):
        plan = _raw_plan()
        plan["medications"] = []
        plan["omitted_facts"].append({"fact_id": 2, "reason": "routine_non_actionable"})
        with self.assertRaisesRegex(cite_check.PlanCitationError, "critical fact ID 2"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_critical_fact_hidden_as_duplicate(self):
        plan = _raw_plan()
        plan["medications"] = []
        plan["omitted_facts"].append({"fact_id": 2, "reason": "duplicate_or_already_represented"})
        with self.assertRaisesRegex(cite_check.PlanCitationError, "critical fact ID 2"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_pending_contrast_ct_hidden_as_technical_detail(self):
        facts = copy.deepcopy(FACTS)
        facts[5]["quote"] = "CT with contrast was ordered for next week"
        facts[5]["text"] = "A CT with contrast was ordered for next week."
        plan = _raw_plan()
        with self.assertRaisesRegex(cite_check.PlanCitationError, "critical fact ID 6"):
            cite_check.assert_plan_citations(plan, facts)

    def test_rejects_disposition_explaining_normal_result_as_routine(self):
        facts = copy.deepcopy(FACTS)
        facts[5]["quote"] = "Normal CT found no pulmonary embolism, so the patient was discharged"
        facts[5]["text"] = "Normal CT found no pulmonary embolism, so the patient was discharged."
        plan = _raw_plan()
        plan["omitted_facts"][1]["reason"] = "routine_non_actionable"
        with self.assertRaisesRegex(cite_check.PlanCitationError, "critical fact ID 6"):
            cite_check.assert_plan_citations(plan, facts)

    def test_rejects_required_follow_up_hidden_as_stable_background(self):
        plan = _raw_plan()
        plan["follow_up"] = []
        plan["questions"] = []
        plan["omitted_facts"].append({"fact_id": 4, "reason": "stable_unchanged_background"})
        facts = copy.deepcopy(FACTS)
        facts[3]["text"] = "Stable condition; required follow up in 3 months."
        with self.assertRaisesRegex(cite_check.PlanCitationError, "critical fact ID 4"):
            cite_check.assert_plan_citations(plan, facts)

    def test_allows_actual_duplicate_of_visible_fact(self):
        facts = copy.deepcopy(FACTS)
        duplicate = copy.deepcopy(facts[1])
        duplicate["id"] = 7
        facts.append(duplicate)
        plan = _raw_plan()
        plan["omitted_facts"].append({"fact_id": 7, "reason": "duplicate_or_already_represented"})
        cite_check.assert_plan_citations(plan, facts)

    def test_rejects_generic_advice_presented_as_patient_specific(self):
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [
            {"title": "Exercise", "why": "This is good for you.",
             "steps": ["Exercise regularly."], "description": "Exercise regularly.",
             "frequency": "", "duration": "", "status": "to_do",
             "source_fact_ids": [5]},
        ]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "generic advice fact ID 5"):
            cite_check.assert_plan_citations(plan, FACTS)

    def test_rejects_unlabeled_broad_wellness_advice(self):
        facts = copy.deepcopy(FACTS)
        facts[4]["quote"] = "Exercise regularly and eat a healthy diet"
        facts[4]["text"] = "Exercise regularly and eat a healthy diet."
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [{
            "title": "Healthy habits", "why": None, "steps": [],
            "description": "Exercise regularly and eat a healthy diet.",
            "frequency": "", "duration": "", "status": "to_do",
            "source_fact_ids": [5],
        }]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "generic advice fact ID 5"):
            cite_check.assert_plan_citations(plan, facts)

    def test_allows_explicit_patient_specific_wellness_instruction(self):
        facts = copy.deepcopy(FACTS)
        facts[4]["quote"] = "For this patient, exercise 30 minutes daily"
        facts[4]["text"] = "For this patient, exercise 30 minutes daily because of hypertension."
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [{
            "title": "Exercise", "why": "Because of your hypertension.", "steps": [],
            "description": "Exercise 30 minutes daily.", "frequency": "daily",
            "duration": "", "status": "to_do", "source_fact_ids": [5],
        }]
        cite_check.assert_plan_citations(plan, facts)

    def test_rejects_quantified_generic_wellness_advice(self):
        facts = copy.deepcopy(FACTS)
        facts[4]["quote"] = "Exercise 150 minutes each week"
        facts[4]["text"] = "Exercise 150 minutes each week."
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [{
            "title": "Exercise", "why": None, "steps": [],
            "description": "Exercise 150 minutes each week.", "frequency": "weekly",
            "duration": "", "status": "to_do", "source_fact_ids": [5],
        }]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "generic advice fact ID 5"):
            cite_check.assert_plan_citations(plan, facts)

    def test_rejects_quantified_generic_wellness_with_reordered_words(self):
        facts = copy.deepcopy(FACTS)
        facts[4]["quote"] = "Aim for 150 minutes of exercise per week"
        facts[4]["text"] = "Aim for 150 minutes of exercise per week."
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [{
            "title": "Exercise", "why": None, "steps": [],
            "description": "Aim for 150 minutes of exercise per week.",
            "frequency": "weekly", "duration": "", "status": "to_do",
            "source_fact_ids": [5],
        }]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "generic advice fact ID 5"):
            cite_check.assert_plan_citations(plan, facts)

    def test_allows_personalized_quantified_wellness_instruction(self):
        facts = copy.deepcopy(FACTS)
        facts[4]["quote"] = "For this patient, exercise 150 minutes each week"
        facts[4]["text"] = "For this patient, exercise 150 minutes each week because of hypertension."
        plan = _raw_plan()
        plan["omitted_facts"] = [entry for entry in plan["omitted_facts"] if entry["fact_id"] != 5]
        plan["other"] = [{
            "title": "Exercise", "why": "Because of your hypertension.", "steps": [],
            "description": "Exercise 150 minutes each week.", "frequency": "weekly",
            "duration": "", "status": "to_do", "source_fact_ids": [5],
        }]
        cite_check.assert_plan_citations(plan, facts)

    def test_rejects_unknown_citation_even_when_paired_text_is_empty(self):
        plan = _raw_plan()
        plan["summary"] = ""
        plan["summary_fact_ids"] = [999]
        with self.assertRaisesRegex(cite_check.PlanCitationError, "unknown fact ID 999"):
            cite_check.assert_plan_citations(plan, FACTS)


class TestCiteCheckCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = self._tmp.name
        with open(os.path.join(self.run_dir, "02_facts.json"), "w", encoding="utf-8") as handle:
            json.dump(_facts_document(self.run_dir), handle)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_raw(self, plan: dict) -> None:
        with open(os.path.join(self.run_dir, "03_plan.raw.json"), "w", encoding="utf-8") as handle:
            json.dump(plan, handle)

    def test_writes_schema_valid_draft_without_repairing_clinical_content(self):
        plan = _raw_plan()
        self._write_raw(plan)
        self.assertEqual(cite_check._run_assemble(self.run_dir), 0)
        with open(os.path.join(self.run_dir, "03_plan.draft.json"), encoding="utf-8") as handle:
            draft = json.load(handle)
        for field in plan:
            self.assertEqual(draft[field], plan[field])
        self.assertEqual(validate.validate(draft, validate.load_schema("care_plan")), [])

    def test_fails_without_silent_drop_or_output(self):
        plan = _raw_plan()
        plan["medications"][0]["source_fact_ids"] = [999]
        self._write_raw(plan)
        self.assertEqual(cite_check._run_assemble(self.run_dir), 1)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "03_plan.draft.json")))
        with open(os.path.join(self.run_dir, "03_plan.raw.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), plan)

    def test_failed_rerun_removes_stale_draft_and_records_failure(self):
        self._write_raw(_raw_plan())
        self.assertEqual(cite_check._run_assemble(self.run_dir), 0)
        plan = _raw_plan()
        plan["medications"][0]["source_fact_ids"] = [999]
        self._write_raw(plan)
        self.assertEqual(cite_check._run_assemble(self.run_dir), 1)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "03_plan.draft.json")))
        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as handle:
            run_log = json.load(handle)
        self.assertEqual(run_log["stages"]["plan_check"]["status"], "failed")

    def test_additions_mode_is_removed(self):
        script = os.path.join(_paths.SCRIPTS_DIR, "cite_check.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir, "--additions"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --additions", result.stderr)


if __name__ == "__main__":
    unittest.main()
