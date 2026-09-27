import copy
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import _version  # noqa: E402
import validate  # noqa: E402


CORE_SCHEMAS = {
    "units",
    "protected",
    "draft",
    "draft_checked",
    "check",
    "verify_raw",
    "verify",
    "plan",
    "run",
}
OPTIONAL_SCHEMAS = {"glossary", "glossary_raw"}
RETIRED_SCHEMAS = {
    "facts_raw", "facts", "care_plan_agent", "care_plan", "flags", "review_raw", "review",
}

IDENTITY = {"schema_version": "3.0", "run_id": "run-1"}


def _draft():
    return _runfix.draft_raw()


def _checked():
    return {**IDENTITY, **_draft()}


def _plan():
    return {
        **IDENTITY,
        "plugin_version": "0.1.0",
        "created_at": "2026-09-26T12:00:00+00:00",
        "word_count": 60,
        "score": {"before_grade": 9.1, "after_grade": 5.2},
        "notices": [],
        **_draft(),
    }


def _check():
    return {
        **IDENTITY,
        "round": 1,
        "word_count": 60,
        "budget": {"target": 300, "warn": 350, "max": 500},
        "over_budget": False,
        "numeric_flags": [{"flag_id": "n1", "path": "findings[0].result", "token": "5 mg", "unit_ids": [3]}],
        "uncited_protected": [{"unit_id": 9, "categories": ["abnormal_or_pending_results"]}],
    }


def _verify_raw():
    return {
        "claims": [{"path": "why_you_went", "result": "supported"},
                   {"path": "findings[0]", "result": "needs_correction", "note": "wrong dose"}],
        "operations": [
            {"op": "replace", "path": "findings[0].result", "value": "Normal.", "unit_ids": [3]},
            {"op": "clear", "path": "findings_lead"},
            {"op": "remove", "path": "next_steps[1]", "reason": "noise"},
        ],
        "numeric_resolutions": [
            {"flag_id": "n1", "resolution": "corrected", "correction_path": "findings[0].result"},
        ],
        "protected_units": [
            {"unit_id": 9, "result": "not_needed", "reason": "false_positive"},
            {"unit_id": 10, "result": "missing", "category": "follow_up"},
        ],
    }


def _verify():
    raw = _verify_raw()
    return {
        **IDENTITY,
        "round": 1,
        "outcome": "repair_requested",
        **raw,
        "accepted_numeric": [{"path": "findings[0].result", "token": "5 mg"}],
        "missing": [{"unit_id": 10, "category": "follow_up"}],
        "counts": {
            "claims": 2, "supported": 1, "needs_correction": 1, "unsupported": 0,
            "operations": 3, "numeric_flags": 1, "protected_units": 2, "missing": 1,
            "word_count_before": 60, "word_count_after": 55,
        },
    }


class TestSchemaInventory(unittest.TestCase):
    def test_exact_schema_inventory(self):
        schema_files = sorted(glob.glob(os.path.join(_paths.SCHEMA_DIR, "*.schema.json")))
        names = {os.path.basename(path).removesuffix(".schema.json") for path in schema_files}
        self.assertEqual(names, CORE_SCHEMAS | OPTIONAL_SCHEMAS)
        self.assertFalse(names & RETIRED_SCHEMAS)
        for path in schema_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertEqual(data.get("title"), os.path.basename(path).removesuffix(".schema.json"))

    def test_schema_version_is_v3_without_changing_plugin_version(self):
        self.assertEqual(_version.SCHEMA_VERSION, "3.0")
        with open(os.path.join(_paths.REPO_ROOT, "build-versions.json"), "r", encoding="utf-8") as f:
            self.assertEqual(_version.PLUGIN_VERSION, json.load(f)["prod"])

    def test_versioned_schemas_accept_only_the_current_version(self):
        for name in CORE_SCHEMAS | OPTIONAL_SCHEMAS:
            schema = validate.load_schema(name)
            version = schema.get("properties", {}).get("schema_version")
            if version is not None:
                with self.subTest(name=name):
                    self.assertEqual(version.get("enum"), ["3.0"])


class TestDraftSchemas(unittest.TestCase):
    def test_minimal_documents_are_valid(self):
        for name, document in (
            ("draft", _draft()), ("draft_checked", _checked()), ("plan", _plan()),
        ):
            with self.subTest(name=name):
                self.assertEqual(validate.validate(document, validate.load_schema(name)), [])

    def test_draft_rejects_identity_and_checked_draft_requires_it(self):
        draft = _draft()
        draft["run_id"] = "run-1"
        self.assertTrue(validate.validate(draft, validate.load_schema("draft")))
        checked = _checked()
        del checked["run_id"]
        self.assertTrue(validate.validate(checked, validate.load_schema("draft_checked")))

    def test_visible_items_must_cite_units(self):
        draft = _draft()
        draft["findings"][0]["unit_ids"] = []
        errors = validate.validate(draft, validate.load_schema("draft"))
        self.assertTrue(any("findings[0].unit_ids" in error for error in errors))

    def test_slot_caps(self):
        draft = _draft()
        draft["findings"] = draft["findings"] * 7
        draft["questions"] = [{"question": "Why?", "unit_ids": [1]}] * 4
        errors = validate.validate(draft, validate.load_schema("draft"))
        self.assertTrue(any(error.startswith("findings") for error in errors))
        self.assertTrue(any(error.startswith("questions") for error in errors))

    def test_plan_requires_score_and_word_count(self):
        for field in ("score", "word_count", "notices", "created_at"):
            with self.subTest(field=field):
                plan = _plan()
                del plan[field]
                self.assertTrue(validate.validate(plan, validate.load_schema("plan")))


class TestCheckSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("check")

    def test_valid(self):
        self.assertEqual(validate.validate(_check(), self.schema), [])

    def test_flag_ids_are_strings_and_rounds_are_bounded(self):
        check = _check()
        check["numeric_flags"][0]["flag_id"] = 1
        check["round"] = 3
        errors = validate.validate(check, self.schema)
        self.assertTrue(any("flag_id" in error for error in errors))
        self.assertTrue(any("round" in error for error in errors))

    def test_unknown_protected_category(self):
        check = _check()
        check["uncited_protected"][0]["categories"] = ["labs"]
        self.assertTrue(validate.validate(check, self.schema))


class TestVerifySchemas(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate.validate(_verify_raw(), validate.load_schema("verify_raw")), [])
        self.assertEqual(validate.validate(_verify(), validate.load_schema("verify")), [])

    def test_raw_rejects_unknown_operation_and_verdicts(self):
        schema = validate.load_schema("verify_raw")
        raw = _verify_raw()
        raw["operations"].append({"op": "rewrite", "path": "why_you_went.text", "value": "x"})
        self.assertTrue(validate.validate(raw, schema))
        raw = _verify_raw()
        raw["verdict"] = "pass"
        self.assertTrue(validate.validate(raw, schema))

    def test_remove_requires_a_reason(self):
        raw = _verify_raw()
        del raw["operations"][2]["reason"]
        self.assertTrue(validate.validate(raw, validate.load_schema("verify_raw")))

    def test_record_outcome_is_closed(self):
        record = _verify()
        record["outcome"] = "pass"
        self.assertTrue(validate.validate(record, validate.load_schema("verify")))


class TestRunSchema(unittest.TestCase):
    def setUp(self):
        self.schema = validate.load_schema("run")
        stage = {
            "status": "ok",
            "attempts": 1,
            "started_at": "2026-09-26T12:00:00+00:00",
            "finished_at": "2026-09-26T12:00:01+00:00",
            "checks": {},
            "artifacts": [{"path": "01_units.json"}],
        }
        self.instance = {
            "schema_version": "3.0",
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
                name: copy.deepcopy(stage)
                for name in ("unitize", "write", "check", "verify", "settle", "finalize")
            },
            "notices": [],
        }
        self.instance["stages"]["glossary"] = {
            "status": "skipped",
            "attempts": 0,
            "started_at": None,
            "finished_at": None,
            "checks": {},
            "artifacts": [],
            "skip_reason": "not requested",
        }

    def test_recognized_stages_and_artifacts_are_valid(self):
        self.assertEqual(validate.validate(self.instance, self.schema), [])

    def test_retired_and_unknown_stage_names_are_rejected(self):
        for name in ("review_fidelity", "ground", "assemble", "settle_review"):
            with self.subTest(name=name):
                instance = copy.deepcopy(self.instance)
                instance["stages"][name] = instance["stages"]["unitize"]
                errors = validate.validate(instance, self.schema)
                self.assertTrue(any(name in error for error in errors))

    def test_core_stage_rejects_degraded_skipped_and_repair_requested(self):
        for status in ("degraded", "skipped", "repair_requested"):
            with self.subTest(status=status):
                instance = copy.deepcopy(self.instance)
                instance["stages"]["verify"]["status"] = status
                self.assertTrue(validate.validate(instance, self.schema))

    def test_settle_may_request_repair(self):
        self.instance["stages"]["settle"]["status"] = "repair_requested"
        self.assertEqual(validate.validate(self.instance, self.schema), [])
        self.instance["stages"]["settle"]["status"] = "degraded"
        self.assertTrue(validate.validate(self.instance, self.schema))

    def test_old_schema_version_is_rejected(self):
        self.instance["schema_version"] = "2.0"
        self.assertTrue(validate.validate(self.instance, self.schema))

    def test_optional_stage_rejects_unknown_status(self):
        self.instance["stages"]["glossary"]["status"] = "pending"
        self.assertTrue(validate.validate(self.instance, self.schema))

    def test_skipped_optional_stage_requires_skip_reason(self):
        del self.instance["stages"]["glossary"]["skip_reason"]
        self.assertTrue(validate.validate(self.instance, self.schema))

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
            "schema_version": "3.0",
            "plugin_version": "0.1.0",
            "run_id": "run-1",
            "terms": [term] * 5,
        }
        self.assertEqual(validate.validate(instance, schema), [])
        instance["terms"].append(term)
        self.assertTrue(validate.validate(instance, schema))


if __name__ == "__main__":
    unittest.main()
