import copy
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import validate  # noqa: E402


MINIMAL_CARE_PLAN = {
    "schema_version": "1.0",
    "plugin_version": "0.1.0",
    "summary": "",
    "summary_fact_ids": [],
    "reason_for_visit": [],
    "diagnosis": {
        "changed_since_last_visit_fact_ids": [],
        "details": [],
    },
    "medications": [],
    "tests": [],
    "procedures": [],
    "other": [],
    "follow_up": [],
    "warning_signs": [],
    "questions": [],
    "low_priority": [],
}


class TestAllSchemasParse(unittest.TestCase):
    def test_every_schema_file_is_valid_json(self):
        schema_files = sorted(glob.glob(os.path.join(_paths.SCHEMA_DIR, "*.schema.json")))
        self.assertGreater(len(schema_files), 0, "expected at least one schema file")
        for path in schema_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIsInstance(data, dict)


class TestCarePlanSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("care_plan")

    def test_minimal_instance_is_valid(self):
        errors = validate.validate(MINIMAL_CARE_PLAN, self.schema)
        self.assertEqual(errors, [])

    def test_bad_status_enum_names_path(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["medications"] = [
            {"status": "pending", "source_fact_ids": [1]}
        ]
        errors = validate.validate(instance, self.schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("medications[0].status", errors[0])

    def test_why_null_is_accepted(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["medications"] = [
            {"status": "to_do", "source_fact_ids": [1], "why": None}
        ]
        errors = validate.validate(instance, self.schema)
        self.assertEqual(errors, [])

    def test_questions_over_max_items_fails(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["questions"] = ["q1", "q2", "q3", "q4"]
        errors = validate.validate(instance, self.schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("questions", errors[0])

    def test_missing_required_field_fails(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        del instance["summary"]
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("summary" in e for e in errors))

    def test_additional_top_level_property_rejected(self):
        instance = copy.deepcopy(MINIMAL_CARE_PLAN)
        instance["not_a_real_field"] = True
        errors = validate.validate(instance, self.schema)
        self.assertTrue(any("not_a_real_field" in e for e in errors))


class TestCarePlanAgentSchema(unittest.TestCase):
    def test_minimal_instance_without_meta_fields_is_valid(self):
        schema = validate.load_schema("care_plan_agent")
        instance = {k: v for k, v in MINIMAL_CARE_PLAN.items() if k not in ("schema_version", "plugin_version")}
        errors = validate.validate(instance, schema)
        self.assertEqual(errors, [])

    def test_schema_version_rejected(self):
        schema = validate.load_schema("care_plan_agent")
        instance = {k: v for k, v in MINIMAL_CARE_PLAN.items() if k != "plugin_version"}
        errors = validate.validate(instance, schema)
        self.assertTrue(any("schema_version" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
