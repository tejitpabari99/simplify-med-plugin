import copy
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import _version  # noqa: E402
import validate  # noqa: E402


CORE_SCHEMAS = {
    "care_plan",
    "care_plan_agent",
    "facts",
    "facts_raw",
    "flags",
    "review",
    "review_raw",
    "run",
    "units",
}
OPTIONAL_SCHEMAS = {"glossary", "glossary_raw"}

MINIMAL_AGENT_PLAN = {
    "summary": "Your blood pressure medicine dose changed.",
    "summary_fact_ids": [1],
    "reason_for_visit": [],
    "diagnosis": {
        "changed_since_last_visit_fact_ids": [],
        "details": [],
    },
    "medications": [
        {
            "title": "Lisinopril",
            "dosage": "10 mg",
            "status": "to_do",
            "source_fact_ids": [1],
        }
    ],
    "tests": [],
    "procedures": [],
    "other": [],
    "follow_up": [],
    "warning_signs": [],
    "questions": [
        {
            "question": "When should I start the new dose?",
            "source_fact_ids": [1],
        }
    ],
    "omitted_facts": [
        {
            "fact_id": 2,
            "reason": "stable_unchanged_background",
        }
    ],
}

MINIMAL_CARE_PLAN = {
    "schema_version": "2.0",
    "plugin_version": "0.1.0",
    "meta": {
        "run_id": "run-1",
        "schema_version": "2.0",
        "plugin_version": "0.1.0",
    },
    **MINIMAL_AGENT_PLAN,
}

MINIMAL_RAW_REVIEW = {
    "reviewed_fact_ids": [1, 2],
    "fact_reviews": [
        {"fact_id": 1, "result": "visible_accurate"},
        {"fact_id": 2, "result": "omission_acceptable"},
    ],
    "corrections": [],
    "numeric_resolutions": [
        {"flag_id": 1, "resolution": "equivalent"},
    ],
    "reassemble_fact_ids": [],
}


class TestAllSchemasParse(unittest.TestCase):
    def test_exact_v2_schema_inventory(self):
        schema_files = sorted(glob.glob(os.path.join(_paths.SCHEMA_DIR, "*.schema.json")))
        names = {os.path.basename(path).removesuffix(".schema.json") for path in schema_files}
        self.assertEqual(names, CORE_SCHEMAS | OPTIONAL_SCHEMAS)

        for path in schema_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIsInstance(data, dict)

    def test_schema_version_is_v2_without_changing_plugin_version(self):
        self.assertEqual(_version.SCHEMA_VERSION, "2.0")
        self.assertEqual(_version.PLUGIN_VERSION, "0.1.0")


class TestCarePlanSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("care_plan")

    def test_schema_v2_plan_with_dispositions_and_cited_questions_is_valid(self):
        self.assertEqual(validate.validate(MINIMAL_CARE_PLAN, self.schema), [])

    def test_old_schema_version_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["schema_version"] = "1.0"
        self.assertTrue(validate.validate(instance, self.schema))

    def test_invalid_omission_reason_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["omitted_facts"][0]["reason"] = "low_priority"
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("omitted_facts[0].reason" in error for error in errors))

    def test_duplicate_omission_shape_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["omitted_facts"] *= 2
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("omitted_facts" in error and "uniqueItems" in error for error in errors))

    def test_unknown_omission_field_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["omitted_facts"][0]["note"] = "routine detail"
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("note" in error for error in errors))

    def test_old_low_priority_shape_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["low_priority"] = ["routine detail"]
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("low_priority" in error for error in errors))

    def test_question_must_be_cited(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["questions"][0]["source_fact_ids"] = []
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("questions[0].source_fact_ids" in error for error in errors))

    def test_legacy_string_question_is_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["questions"] = ["Do I need another test?"]
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("questions[0]" in error for error in errors))

    def test_questions_are_capped_at_three(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["questions"] = instance["questions"] * 4
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("questions" in error for error in errors))


class TestCarePlanAgentSchema(unittest.TestCase):
    def test_agent_plan_uses_same_content_contract_without_system_metadata(self):
        schema = validate.load_schema("care_plan_agent")
        self.assertEqual(validate.validate(MINIMAL_AGENT_PLAN, schema), [])

    def test_agent_plan_rejects_system_metadata(self):
        schema = validate.load_schema("care_plan_agent")
        instance = copy.deepcopy(MINIMAL_AGENT_PLAN)
        instance["schema_version"] = "2.0"
        errors = validate.validate(instance, schema)
        self.assertTrue(any("schema_version" in error for error in errors))


class TestFlagsSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("flags")
        self.instance = {
            "schema_version": "2.0",
            "plugin_version": "0.1.0",
            "run_id": "run-1",
            "numeric_parity": [
                {
                    "flag_id": 1,
                    "path": "medications[0].dosage",
                    "tokens_in_field": ["20", "mg"],
                    "tokens_in_facts": ["10", "mg"],
                }
            ],
            "thin_fields": [],
        }

    def test_numeric_flags_have_stable_ids(self):
        self.assertEqual(validate.validate(self.instance, self.schema), [])

    def test_numeric_flag_without_id_is_rejected(self):
        del self.instance["numeric_parity"][0]["flag_id"]
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(any("flag_id" in error for error in errors))


class TestCombinedReviewSchemas(unittest.TestCase):
    def test_complete_raw_review_is_valid(self):
        schema = validate.load_schema("review_raw")
        self.assertEqual(validate.validate(MINIMAL_RAW_REVIEW, schema), [])

    def test_incomplete_raw_review_is_rejected(self):
        schema = validate.load_schema("review_raw")
        for field in (
            "reviewed_fact_ids",
            "fact_reviews",
            "corrections",
            "numeric_resolutions",
            "reassemble_fact_ids",
        ):
            with self.subTest(field=field):
                instance = copy.deepcopy(MINIMAL_RAW_REVIEW)
                del instance[field]
                self.assertTrue(validate.validate(instance, schema))

    def test_invalid_fact_review_result_is_rejected(self):
        schema = validate.load_schema("review_raw")
        instance = copy.deepcopy(MINIMAL_RAW_REVIEW)
        instance["fact_reviews"][0]["result"] = "looks_fine"
        errors = validate.validate(instance, schema)
        self.assertTrue(any("fact_reviews[0].result" in error for error in errors))

    def test_duplicate_reviewed_fact_id_is_rejected(self):
        schema = validate.load_schema("review_raw")
        instance = copy.deepcopy(MINIMAL_RAW_REVIEW)
        instance["reviewed_fact_ids"] = [1, 1]
        errors = validate.validate(instance, schema)
        self.assertTrue(any("reviewed_fact_ids" in error and "uniqueItems" in error for error in errors))

    def test_bounded_correction_and_numeric_resolution_are_valid(self):
        schema = validate.load_schema("review_raw")
        instance = copy.deepcopy(MINIMAL_RAW_REVIEW)
        instance["fact_reviews"][0]["result"] = "visible_needs_correction"
        instance["corrections"] = [
            {
                "op": "replace",
                "path": "medications[0].dosage",
                "value": "10 mg",
                "source_fact_ids": [1],
            }
        ]
        instance["numeric_resolutions"] = [
            {
                "flag_id": 1,
                "resolution": "corrected",
                "correction_path": "medications[0].dosage",
            }
        ]
        self.assertEqual(validate.validate(instance, schema), [])

    def test_unknown_operation_is_rejected(self):
        schema = validate.load_schema("review_raw")
        instance = copy.deepcopy(MINIMAL_RAW_REVIEW)
        instance["corrections"] = [
            {"op": "rewrite", "path": "summary", "value": "new summary"}
        ]
        self.assertTrue(validate.validate(instance, schema))

    def test_sanitized_review_includes_derived_result(self):
        schema = validate.load_schema("review")
        instance = {
            "schema_version": "2.0",
            "plugin_version": "0.1.0",
            "run_id": "run-1",
            **MINIMAL_RAW_REVIEW,
            "dropped_operations": [],
            "counts": {
                "facts_reviewed": 2,
                "visible_accurate": 1,
                "visible_needs_correction": 0,
                "omission_acceptable": 1,
                "must_include": 0,
                "corrections": 0,
                "numeric_resolutions": 1,
                "dropped_operations": 0,
                "reassemble_facts": 0,
            },
            "verdict": "pass",
        }
        self.assertEqual(validate.validate(instance, schema), [])


class TestRunSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("run")
        self.instance = {
            "schema_version": "2.0",
            "plugin_version": "0.1.0",
            "run_id": "run-1",
            "created_at": "2026-09-26T12:00:00+00:00",
            "level": "standard",
            "inputs": [
                {
                    "file": "visit.txt",
                    "extraction_method": "native",
                    "pages": 1,
                    "sha256": "abc123",
                }
            ],
            "stages": {
                "unitize": {
                    "status": "ok",
                    "attempts": 1,
                    "started_at": "2026-09-26T12:00:00+00:00",
                    "finished_at": "2026-09-26T12:00:01+00:00",
                    "checks": {},
                    "artifacts": [{"path": "01_units.json"}],
                },
                "glossary": {
                    "status": "skipped",
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "checks": {},
                    "artifacts": [],
                    "skip_reason": "not requested",
                },
            },
            "notices": [],
        }

    def test_recognized_stages_and_artifacts_are_valid(self):
        self.assertEqual(validate.validate(self.instance, self.schema), [])

    def test_unknown_stage_name_is_rejected(self):
        self.instance["stages"]["review_fidelity"] = self.instance["stages"]["unitize"]
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(any("review_fidelity" in error for error in errors))

    def test_core_stage_rejects_degraded_and_skipped(self):
        for status in ("degraded", "skipped"):
            with self.subTest(status=status):
                instance = copy.deepcopy(self.instance)
                instance["stages"]["unitize"]["status"] = status
                self.assertTrue(validate.validate(instance, self.schema))

    def test_optional_stage_rejects_unknown_status(self):
        self.instance["stages"]["glossary"]["status"] = "pending"
        self.assertTrue(validate.validate(self.instance, self.schema))

    def test_skipped_optional_stage_requires_skip_reason(self):
        del self.instance["stages"]["glossary"]["skip_reason"]
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(errors)

    def test_non_skipped_optional_stage_rejects_skip_reason(self):
        self.instance["stages"]["glossary"]["status"] = "ok"
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(errors)

    def test_core_stage_rejects_skip_reason(self):
        self.instance["stages"]["unitize"]["skip_reason"] = "not applicable"
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(any("skip_reason" in error for error in errors))

    def test_malformed_artifact_record_is_rejected(self):
        self.instance["stages"]["unitize"]["artifacts"] = [{"name": "01_units.json"}]
        errors = validate.validate(self.instance, self.schema)
        self.assertTrue(any("path" in error for error in errors))


class TestOptionalGlossarySchemas(unittest.TestCase):
    def test_optional_glossary_is_capped_at_five_terms(self):
        schema = validate.load_schema("glossary")
        term = {
            "term": "hypertension",
            "matched_term": "high blood pressure",
            "definition": "Blood pressure that stays too high.",
            "source": "llm_proposed",
        }
        instance = {
            "schema_version": "2.0",
            "plugin_version": "0.1.0",
            "run_id": "run-1",
            "terms": [term] * 5,
        }
        self.assertEqual(validate.validate(instance, schema), [])
        instance["terms"].append(term)
        self.assertTrue(validate.validate(instance, schema))


if __name__ == "__main__":
    unittest.main()
