import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import plan_paths  # noqa: E402
import plan_view  # noqa: E402
import validate  # noqa: E402


ER_FIXTURE = os.path.join(_paths.FIXTURES_DIR, "plans", "er_visit.final.json")
NOTICE_MARKER = "INTERNAL-NOTICE-MARKER"


def _fixture_plan():
    with open(ER_FIXTURE, "r", encoding="utf-8") as handle:
        plan = json.load(handle)
    plan["notices"] = [NOTICE_MARKER]
    return plan


def _minimal_plan(visit_type="clinic_visit"):
    """Schema-valid final plan with only the required lead paragraph."""
    none = {"status": "none_in_source", "unit_ids": []}
    return {
        "schema_version": "3.0",
        "plugin_version": "0.1.0",
        "run_id": "run-1",
        "created_at": "2026-09-26T00:00:00+00:00",
        "word_count": 6,
        "score": {"before_grade": None, "after_grade": None},
        "notices": [],
        "visit_type": visit_type,
        "why_you_went": {"text": "You came in for a check-up.", "unit_ids": [1]},
        "findings_lead": None,
        "findings": [],
        "diagnoses": [],
        "disposition": None,
        "next_steps": [],
        "medicines": {"items": [], "none_statement": None},
        "return_precautions": [],
        "questions": [],
        "coverage": {
            key: dict(none)
            for key in (
                "medication_changes", "follow_up", "return_precautions",
                "diagnoses", "disposition", "abnormal_or_pending_results",
            )
        },
    }


def _glossary_doc(run_id="fixture-er-visit"):
    return {
        "schema_version": "3.0",
        "plugin_version": "0.1.0",
        "run_id": run_id,
        "terms": [
            {
                "term": "Bundle branch block",
                "matched_term": "bundle branch block",
                "definition": "A delay in the electrical signal along one side of the heart.",
                "source": "llm_proposed",
            },
        ],
    }


def _section(view, key):
    return next((section for section in view["sections"] if section["key"] == key), None)


class TestFixture(unittest.TestCase):
    def test_er_fixture_is_a_valid_final_plan(self):
        with open(ER_FIXTURE, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
        self.assertEqual(validate.validate(plan, validate.load_schema("plan")), [])
        self.assertEqual(plan["word_count"], plan_view.word_count(plan))

    def test_minimal_plan_is_a_valid_final_plan(self):
        self.assertEqual(validate.validate(_minimal_plan(), validate.load_schema("plan")), [])


class TestBuildView(unittest.TestCase):
    def test_er_sections_follow_the_target_order_and_headings(self):
        view = plan_view.build_view(_fixture_plan())
        self.assertEqual(view["title"], "Your ER visit, simplified")
        self.assertEqual(
            [(section["key"], section["heading"]) for section in view["sections"]],
            [
                ("why_you_went", None),
                ("findings", "What did they find?"),
                ("next_steps", "What should you do now?"),
                ("return_precautions", "When should you go back to the ER?"),
            ],
        )
        findings = _section(view, "findings")
        self.assertEqual(findings["lead"], "The important tests were reassuring:")
        self.assertEqual(findings["diagnoses_label"], "The ER diagnosed you with:")
        self.assertEqual(len(findings["items"]), 5)
        self.assertEqual(
            [row["text"] for row in findings["diagnoses"]],
            ["Acute headache", "Tingling in your left arm/hand"],
        )
        self.assertTrue(findings["disposition"].startswith("They did not find an emergency cause"))

    def test_titles_and_headings_follow_visit_type(self):
        expected = {
            "er_visit": ("Your ER visit, simplified", "When should you go back to the ER?", "The ER diagnosed you with:"),
            "hospital_stay": ("Your hospital stay, simplified", "When should you go back to the ER?", "Diagnosed with:"),
            "clinic_visit": ("Your visit, simplified", "When to get help right away", "Diagnosed with:"),
            "test_results": ("Your test results, simplified", "When to get help right away", "Diagnosed with:"),
            "procedure": ("Your procedure, simplified", "When to get help right away", "Diagnosed with:"),
            "other": ("Your documents, simplified", "When to get help right away", "Diagnosed with:"),
        }
        for visit_type, (title, return_heading, diagnoses_label) in expected.items():
            with self.subTest(visit_type=visit_type):
                plan = _minimal_plan(visit_type)
                plan["diagnoses"] = [{"name": "Sprained ankle", "unit_ids": [2]}]
                plan["return_precautions"] = [{"text": "Call 911 if you cannot breathe.", "unit_ids": [3]}]
                view = plan_view.build_view(plan)
                self.assertEqual(view["title"], title)
                self.assertEqual(_section(view, "return_precautions")["heading"], return_heading)
                self.assertEqual(_section(view, "findings")["diagnoses_label"], diagnoses_label)

    def test_empty_slots_are_hidden(self):
        view = plan_view.build_view(_minimal_plan())
        self.assertEqual([section["key"] for section in view["sections"]], ["why_you_went"])

    def test_diagnoses_alone_still_get_the_findings_section(self):
        plan = _minimal_plan()
        plan["diagnoses"] = [{"name": "Strep throat", "plain_name": "", "unit_ids": [2]}]
        findings = _section(plan_view.build_view(plan), "findings")
        self.assertEqual(findings["lead"], "")
        self.assertEqual(findings["items"], [])
        self.assertEqual([row["text"] for row in findings["diagnoses"]], ["Strep throat"])

    def test_plain_name_shown_only_when_it_adds_meaning(self):
        plan = _minimal_plan()
        plan["diagnoses"] = [
            {"name": "Acute headache", "plain_name": "acute headache", "unit_ids": [2]},
            {"name": "Headache, acute", "plain_name": "Acute headache", "unit_ids": [2]},
            {"name": "Left upper extremity paresthesias", "plain_name": "tingling in your left arm", "unit_ids": [2]},
            {"name": "Syncope", "plain_name": "   ", "unit_ids": [2]},
        ]
        rows = _section(plan_view.build_view(plan), "findings")["diagnoses"]
        self.assertEqual(
            [row["text"] for row in rows],
            [
                "Acute headache",
                "Headache, acute",
                "Left upper extremity paresthesias (tingling in your left arm)",
                "Syncope",
            ],
        )

    def test_next_steps_then_medicines_then_none_statement(self):
        plan = _minimal_plan()
        plan["next_steps"] = [{"text": "See your doctor in 1 week.", "unit_ids": [2]}]
        plan["medicines"] = {
            "items": [{"name": "Amoxicillin", "change": "start", "text": "Take 500 mg twice a day for 10 days.", "unit_ids": [3]}],
            "none_statement": {"text": "No other medicines changed.", "unit_ids": [4]},
        }
        rows = _section(plan_view.build_view(plan), "next_steps")["items"]
        self.assertEqual(
            [(row["path"], row["label"], row["text"]) for row in rows],
            [
                ("next_steps[0]", "", "See your doctor in 1 week."),
                ("medicines.items[0]", "Amoxicillin", "Take 500 mg twice a day for 10 days."),
                ("medicines.none_statement", "", "No other medicines changed."),
            ],
        )

    def test_questions_section(self):
        plan = _minimal_plan()
        plan["questions"] = [{"question": "Do I need another heart tracing?", "unit_ids": [2]}]
        section = _section(plan_view.build_view(plan), "questions")
        self.assertEqual(section["heading"], "Questions you may want to ask")
        self.assertEqual([row["text"] for row in section["items"]], ["Do I need another heart tracing?"])

    def test_patient_view_never_contains_internal_fields(self):
        rendered = repr(plan_view.build_view(_fixture_plan()))
        for hidden in (NOTICE_MARKER, "unit_ids", "coverage", "score", "notices", "fixture-er-visit", "word_count"):
            self.assertNotIn(hidden, rendered)

    def test_glossary_is_only_added_when_explicitly_supplied(self):
        plan = _fixture_plan()
        self.assertIsNone(_section(plan_view.build_view(plan), "glossary"))
        glossary = _section(plan_view.build_view(plan, glossary=_glossary_doc()), "glossary")
        self.assertEqual(glossary["heading"], "Medical terms explained")
        self.assertEqual(
            glossary["items"],
            [{"term": "Bundle branch block", "definition": "A delay in the electrical signal along one side of the heart."}],
        )

    def test_building_views_does_not_mutate_plan_or_glossary(self):
        plan = _fixture_plan()
        glossary = _glossary_doc()
        before_plan = copy.deepcopy(plan)
        before_glossary = copy.deepcopy(glossary)
        plan_view.build_view(plan, glossary=glossary)
        plan_view.visible_text(plan)
        self.assertEqual(plan, before_plan)
        self.assertEqual(glossary, before_glossary)


class TestVisibleText(unittest.TestCase):
    def test_visible_text_is_the_visible_strings_in_report_order(self):
        plan = _fixture_plan()
        expected = [text for _path, text, _ids in plan_paths.visible_strings(plan)]
        self.assertEqual(plan_view.visible_text(plan).split("\n\n"), expected)
        self.assertNotIn(NOTICE_MARKER, plan_view.visible_text(plan))

    def test_duplicate_plain_name_is_not_counted(self):
        plan = _minimal_plan()
        plan["diagnoses"] = [{"name": "Acute headache", "plain_name": "acute headache", "unit_ids": [2]}]
        self.assertEqual(plan_view.visible_text(plan).count("headache"), 1)
        plan["diagnoses"][0]["plain_name"] = "a sudden, painful headache"
        self.assertIn("a sudden, painful headache", plan_view.visible_text(plan))

    def test_word_count(self):
        plan = _minimal_plan()
        self.assertEqual(plan_view.word_count(plan), 6)
        plan["next_steps"] = [{"text": "Rest — and drink water.", "unit_ids": [2]}]
        self.assertEqual(plan_view.word_count(plan), 10)
        self.assertEqual(plan_view.word_count(_fixture_plan()), 175)


class TestAssertRenderablePlan(unittest.TestCase):
    def _run_dir(self, run_log):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        run_dir = temporary.name
        with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as handle:
            json.dump(run_log, handle)
        return run_dir

    def test_accepts_finalized_run_with_matching_identity(self):
        run_dir = self._run_dir({"run_id": "fixture-er-visit", "stages": {"finalize": {"status": "ok"}}})
        plan_view.assert_renderable_plan(_fixture_plan(), run_dir, os.path.join(run_dir, "05_plan.final.json"))

    def test_rejects_non_final_files_old_shapes_unfinished_runs_and_foreign_plans(self):
        ok_log = {"run_id": "fixture-er-visit", "stages": {"finalize": {"status": "ok"}}}
        run_dir = self._run_dir(ok_log)
        final_path = os.path.join(run_dir, "05_plan.final.json")
        with self.assertRaisesRegex(ValueError, "completed final report"):
            plan_view.assert_renderable_plan(_fixture_plan(), run_dir, os.path.join(run_dir, "04_plan.settled.json"))
        with self.assertRaisesRegex(ValueError, "completed final report"):
            plan_view.assert_renderable_plan(_fixture_plan(), run_dir, os.path.join(run_dir, "06_plan.final.json"))
        old = _fixture_plan()
        old["schema_version"] = "2.0"
        with self.assertRaisesRegex(ValueError, "completed final report"):
            plan_view.assert_renderable_plan(old, run_dir, final_path)
        unfinished = self._run_dir({"run_id": "fixture-er-visit", "stages": {"settle": {"status": "ok"}}})
        with self.assertRaisesRegex(ValueError, "completed final report"):
            plan_view.assert_renderable_plan(_fixture_plan(), unfinished, os.path.join(unfinished, "05_plan.final.json"))
        foreign = _fixture_plan()
        foreign["run_id"] = "other-run"
        with self.assertRaisesRegex(ValueError, "identities do not match"):
            plan_view.assert_renderable_plan(foreign, run_dir, final_path)


if __name__ == "__main__":
    unittest.main()
