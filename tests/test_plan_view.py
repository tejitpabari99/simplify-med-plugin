import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import plan_view  # noqa: E402


def _base_plan():
    return {
        "schema_version": "1.0",
        "plugin_version": "0.1.0",
        "meta": {"run_id": "run-1", "plugin_version": "0.1.0", "schema_version": "1.0",
                  "level": "standard", "created_at": "2026-09-22T00:00:00+00:00"},
        "notices": ["A notice."],
        "score": {"before_grade": 9.0, "after_grade": 6.0},
        "summary": "You have a condition that needs treatment.",
        "summary_fact_ids": [1],
        "reason_for_visit": [
            {"reason": "Chest pain", "description": "Two weeks of chest pain.", "source_fact_ids": [1]},
        ],
        "diagnosis": {
            "changed_since_last_visit": "Your blood pressure is now higher.",
            "changed_since_last_visit_fact_ids": [2],
            "details": [
                {"title": "Hypertension", "plain_name": "high blood pressure",
                 "description": "Stage two.", "what_it_means_for_you": "Needs treatment.",
                 "severity": "high", "source_fact_ids": [2]},
            ],
        },
        "medications": [
            {"title": "Med A", "plain_name": "", "why": None, "dosage": "10 mg",
             "frequency": "daily", "timing": "", "duration": "", "instructions": "",
             "side_effects_to_watch": "", "change": "", "status": "to_do",
             "source_fact_ids": [3]},
            {"title": "Med B", "plain_name": "medb", "why": "Controls symptoms.",
             "dosage": "20 mg", "frequency": "twice daily", "timing": "", "duration": "",
             "instructions": "Take with water.", "side_effects_to_watch": "Nausea.",
             "change": "", "status": "done", "source_fact_ids": [4]},
        ],
        "tests": [
            {"title": "Blood test", "plain_name": "", "why": None,
             "description": "CBC.", "preparation": "Fast overnight.",
             "status": "to_do", "source_fact_ids": [5]},
        ],
        "procedures": [
            {"title": "Scan", "plain_name": "", "why": "Checks the heart.",
             "what_to_expect": "A quick scan.", "timeframe": "next week",
             "status": "to_do", "source_fact_ids": [6]},
        ],
        "other": [
            {"title": "Diet", "why": None, "steps": ["Eat less salt.", "Walk daily."],
             "description": "Lifestyle change.", "frequency": "Daily", "duration": "Ongoing",
             "status": "to_do", "source_fact_ids": [7]},
        ],
        "follow_up": [
            {"time_frame": "3 months", "description": "Recheck blood pressure.",
             "status": "to_do", "source_fact_ids": [8]},
        ],
        "warning_signs": [
            {"symptom": "Dizziness", "what_it_might_mean": "", "what_to_do": "Sit down.",
             "urgency": None, "related_to": "", "source_fact_ids": [1]},
            {"symptom": "Chest pain worsens", "what_it_might_mean": "Heart attack.",
             "what_to_do": "Call 911.", "urgency": "emergency", "related_to": "",
             "source_fact_ids": [1]},
            {"symptom": "Mild rash", "what_it_might_mean": "Side effect.",
             "what_to_do": "Watch it.", "urgency": "normal_side_effect", "related_to": "",
             "source_fact_ids": [4]},
            {"symptom": "Swelling", "what_it_might_mean": "Fluid buildup.",
             "what_to_do": "Mention at visit.", "urgency": "monitor", "related_to": "",
             "source_fact_ids": [2]},
        ],
        "questions": ["Will I need surgery?"],
        "low_priority": ["Billing code noted."],
        "terms": {
            "hypertension": {"definition": "High blood pressure.", "source": "llm_proposed"},
            "cbc": {"definition": "A blood test.", "source": "llm_proposed"},
        },
    }


class TestBuildView(unittest.TestCase):
    def setUp(self):
        self.plan = _base_plan()
        self.view = plan_view.build_view(self.plan)

    def test_title_and_notices(self):
        self.assertEqual(self.view["title"], "Your visit, explained")
        self.assertEqual(self.view["notices"], ["A notice."])

    def test_score_line_both_present(self):
        self.assertEqual(self.view["score_line"], "Reading level: grade 9.0 before, grade 6.0 after.")

    def test_score_line_after_only(self):
        plan = _base_plan()
        plan["score"] = {"before_grade": None, "after_grade": 6.0}
        view = plan_view.build_view(plan)
        self.assertEqual(view["score_line"], "Reading level: about grade 6.0.")

    def test_score_line_omitted_when_after_missing(self):
        plan = _base_plan()
        plan["score"] = {"before_grade": 9.0, "after_grade": None}
        view = plan_view.build_view(plan)
        self.assertNotIn("score_line", view)

    def test_score_line_omitted_when_both_missing(self):
        plan = _base_plan()
        plan["score"] = {"before_grade": None, "after_grade": None}
        view = plan_view.build_view(plan)
        self.assertNotIn("score_line", view)

    def test_section_order(self):
        keys = [s["key"] for s in self.view["sections"]]
        self.assertEqual(
            keys,
            ["summary", "reason", "findings", "next_steps", "watch", "questions", "glossary"],
        )

    def test_section_omitted_when_empty(self):
        plan = _base_plan()
        plan["questions"] = []
        view = plan_view.build_view(plan)
        keys = [s["key"] for s in view["sections"]]
        self.assertNotIn("questions", keys)

    def test_findings_severity_labels_and_changed(self):
        findings = next(s for s in self.view["sections"] if s["key"] == "findings")
        self.assertEqual(findings["items"][0]["severity_label"], "Serious")
        self.assertIn("What changed since last time: Your blood pressure is now higher.", findings["changed"])

    def test_next_steps_todo_done_split(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        todo_titles = [r["title"] for r in next_steps["todo"]]
        done_titles = [r["title"] for r in next_steps["done"]]
        self.assertIn("Med A", todo_titles)
        self.assertIn("Med B (medb)", done_titles)
        self.assertNotIn("Med B (medb)", todo_titles)

    def test_next_steps_type_precedence(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        todo_labels = [r["type_label"] for r in next_steps["todo"]]
        # medication, medication, test, procedure, appointment, instruction
        order_seen = []
        for label in todo_labels:
            if label not in order_seen:
                order_seen.append(label)
        self.assertEqual(order_seen, ["Medication", "Test", "Procedure", "Appointment", "Instruction"])

    def test_medication_why_always_present_including_not_stated(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        med_a = next(r for r in next_steps["todo"] if r["title"] == "Med A")
        self.assertEqual(med_a["sub"][0], "Why: not stated in your note")
        med_b = next(r for r in next_steps["done"] if r["title"].startswith("Med B"))
        self.assertEqual(med_b["sub"][0], "Why: Controls symptoms.")

    def test_test_procedure_instruction_why_always_present(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        test_row = next(r for r in next_steps["todo"] if r["type_label"] == "Test")
        self.assertTrue(test_row["sub"][0].startswith("Why:"))
        proc_row = next(r for r in next_steps["todo"] if r["type_label"] == "Procedure")
        self.assertTrue(proc_row["sub"][0].startswith("Why:"))
        instr_row = next(r for r in next_steps["todo"] if r["type_label"] == "Instruction")
        self.assertTrue(instr_row["sub"][0].startswith("Why:"))
        self.assertIn("Step 1: Eat less salt.", instr_row["sub"])
        self.assertIn("Step 2: Walk daily.", instr_row["sub"])

    def test_follow_up_has_no_why_line(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        appt = next(r for r in next_steps["todo"] if r["type_label"] == "Appointment")
        self.assertEqual(appt["sub"], [])

    def test_next_steps_keys_stable_and_section_prefixed(self):
        next_steps = next(s for s in self.view["sections"] if s["key"] == "next_steps")
        keys = {r["key"] for r in next_steps["todo"] + next_steps["done"]}
        self.assertIn("medications-0", keys)
        self.assertIn("medications-1", keys)
        self.assertIn("tests-0", keys)
        self.assertIn("procedures-0", keys)
        self.assertIn("follow_up-0", keys)
        self.assertIn("other-0", keys)

    def test_watch_urgency_ordering_null_last_never_dropped(self):
        watch = next(s for s in self.view["sections"] if s["key"] == "watch")
        urgencies = [r["urgency_label"] for r in watch["items"]]
        self.assertEqual(len(watch["items"]), 4)
        # emergency, monitor, normal_side_effect, then null (no call_doctor present)
        self.assertEqual(urgencies, ["Emergency", "Keep an eye on it", "Normal side effect", ""])

    def test_glossary_sorted_alphabetically(self):
        glossary = next(s for s in self.view["sections"] if s["key"] == "glossary")
        terms = [i["term"] for i in glossary["items"]]
        self.assertEqual(terms, sorted(terms, key=str.lower))
        self.assertEqual(set(terms), {"hypertension", "cbc"})

    def test_low_priority_never_in_view(self):
        rendered = repr(self.view)
        self.assertNotIn("Billing code noted.", rendered)

    def test_fact_ids_never_in_view(self):
        rendered = repr(self.view)
        self.assertNotIn("source_fact_ids", rendered)
        self.assertNotIn("summary_fact_ids", rendered)
        self.assertNotIn("changed_since_last_visit_fact_ids", rendered)

    def test_meta_and_run_id_never_in_view(self):
        rendered = repr(self.view)
        self.assertNotIn("run-1", rendered)
        self.assertNotIn("meta", rendered)


class TestVisibleText(unittest.TestCase):
    def test_excludes_glossary_and_notices(self):
        plan = _base_plan()
        text = plan_view.visible_text(plan)
        self.assertNotIn("High blood pressure.", text)  # glossary definition
        self.assertNotIn("A blood test.", text)
        self.assertNotIn("A notice.", text)

    def test_includes_summary_and_next_step_text(self):
        plan = _base_plan()
        text = plan_view.visible_text(plan)
        self.assertIn("You have a condition that needs treatment.", text)
        self.assertIn("Med A", text)
        self.assertIn("Why: not stated in your note", text)

    def test_deep_copy_safe(self):
        plan = _base_plan()
        before = copy.deepcopy(plan)
        plan_view.visible_text(plan)
        plan_view.build_view(plan)
        self.assertEqual(plan, before)


if __name__ == "__main__":
    unittest.main()
