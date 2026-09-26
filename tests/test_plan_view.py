import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import plan_view  # noqa: E402


OMITTED_MARKER = "GENERIC-EDUCATION-MARKER"
NOTICE_MARKER = "INTERNAL-NOTICE-MARKER"


def _base_plan(schema_version="2.0"):
    questions = (
        [{"question": "Do I need another heart tracing?", "source_fact_ids": [7]}]
        if schema_version == "2.0"
        else ["Do I need another heart tracing?"]
    )
    plan = {
        "schema_version": schema_version,
        "plugin_version": "0.1.0",
        "meta": {
            "run_id": "run-1",
            "plugin_version": "0.1.0",
            "schema_version": schema_version,
            "level": "standard",
            "created_at": "2026-09-26T00:00:00+00:00",
        },
        "notices": [NOTICE_MARKER],
        "score": {"before_grade": 9.0, "after_grade": 6.0},
        "summary": "Your emergency tests did not show a stroke.",
        "summary_fact_ids": [1],
        "reason_for_visit": [
            {"reason": "Headache and hand tingling", "description": "You were checked in the ER.", "source_fact_ids": [1]},
        ],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [
                {
                    "title": "First-degree AV block",
                    "plain_name": "delayed electrical signal",
                    "description": "The ECG showed a PR interval of 310 ms.",
                    "what_it_means_for_you": "Discuss this finding with primary care.",
                    "severity": None,
                    "source_fact_ids": [2],
                },
            ],
        },
        "medications": [],
        "tests": [
            {
                "title": "Brain MRI",
                "plain_name": "brain magnetic resonance imaging",
                "why": "To look for a stroke.",
                "description": "The MRI was normal.",
                "preparation": "",
                "status": "done",
                "source_fact_ids": [3],
            },
        ],
        "procedures": [],
        "other": [],
        "follow_up": [
            {
                "time_frame": "As soon as possible",
                "description": "Arrange primary care follow-up.",
                "status": "to_do",
                "source_fact_ids": [4],
            },
        ],
        "warning_signs": [
            {
                "symptom": "New weakness or trouble speaking",
                "what_it_might_mean": "A new neurologic emergency.",
                "what_to_do": "Return to the emergency department.",
                "urgency": "emergency",
                "related_to": "Headache or tingling",
                "source_fact_ids": [5],
            },
        ],
        "questions": questions,
    }
    if schema_version == "2.0":
        plan["omitted_facts"] = [
            {"fact_id": 6, "reason": "generic_not_patient_specific"},
        ]
        plan["internal_checks"] = OMITTED_MARKER
    else:
        plan["low_priority"] = [OMITTED_MARKER]
        plan["terms"] = {
            "MRI": {"definition": "A scan that uses magnets."},
        }
    return plan


def _glossary_doc():
    return {
        "schema_version": "2.0",
        "plugin_version": "0.1.0",
        "run_id": "run-1",
        "terms": [
            {
                "term": "MRI",
                "matched_term": "MRI",
                "definition": "A scan that uses magnets.",
                "source": "llm_proposed",
            },
        ],
    }


class TestPlanView(unittest.TestCase):
    def test_v2_cited_questions_render_as_text(self):
        view = plan_view.build_view(_base_plan())
        questions = next(section for section in view["sections"] if section["key"] == "questions")
        self.assertEqual(questions["items"], [{"n": 1, "text": "Do I need another heart tracing?"}])

    def test_v1_string_questions_remain_renderable(self):
        view = plan_view.build_view(_base_plan("1.0"))
        questions = next(section for section in view["sections"] if section["key"] == "questions")
        self.assertEqual(questions["items"][0]["text"], "Do I need another heart tracing?")

    def test_patient_view_never_contains_internal_fields(self):
        rendered = repr(plan_view.build_view(_base_plan()))
        for hidden in (
            OMITTED_MARKER,
            NOTICE_MARKER,
            "omitted_facts",
            "internal_checks",
            "source_fact_ids",
            "summary_fact_ids",
            "score",
            "notices",
            "run-1",
        ):
            self.assertNotIn(hidden, rendered)

    def test_glossary_is_only_added_when_explicitly_supplied(self):
        plan = _base_plan()
        default_keys = [section["key"] for section in plan_view.build_view(plan)["sections"]]
        enriched = plan_view.build_view(plan, glossary=_glossary_doc())
        self.assertNotIn("glossary", default_keys)
        glossary = next(section for section in enriched["sections"] if section["key"] == "glossary")
        self.assertEqual(glossary["items"], [{"term": "MRI", "definition": "A scan that uses magnets."}])

    def test_legacy_terms_are_available_only_for_explicit_enrichment(self):
        plan = _base_plan("1.0")
        default_keys = [section["key"] for section in plan_view.build_view(plan)["sections"]]
        enriched_keys = [section["key"] for section in plan_view.build_view(plan, legacy_glossary=True)["sections"]]
        self.assertNotIn("glossary", default_keys)
        self.assertIn("glossary", enriched_keys)

    def test_visible_text_excludes_internal_and_glossary_content(self):
        text = plan_view.visible_text(_base_plan(), glossary=_glossary_doc())
        self.assertIn("Your emergency tests did not show a stroke.", text)
        self.assertIn("Do I need another heart tracing?", text)
        self.assertNotIn("A scan that uses magnets.", text)
        self.assertNotIn(OMITTED_MARKER, text)
        self.assertNotIn(NOTICE_MARKER, text)

    def test_building_views_does_not_mutate_plan_or_glossary(self):
        plan = _base_plan()
        glossary = _glossary_doc()
        before_plan = copy.deepcopy(plan)
        before_glossary = copy.deepcopy(glossary)
        plan_view.build_view(plan, glossary=glossary)
        plan_view.visible_text(plan, glossary=glossary)
        self.assertEqual(plan, before_plan)
        self.assertEqual(glossary, before_glossary)


if __name__ == "__main__":
    unittest.main()
