import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import numeric_parity  # noqa: E402
import runlog  # noqa: E402
import settle_review  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def _fact(fact_id, category, text):
    return {
        "id": fact_id,
        "category": category,
        "unit_id": fact_id,
        "quote": text,
        "char_start": 0,
        "char_end": len(text),
        "text": text,
    }


FACTS = [
    _fact(1, "reason_for_visit", "You came in for chest pain."),
    _fact(2, "medications", "Start metoprolol 25 mg twice daily."),
    _fact(3, "follow_up", "Follow up in 3 months."),
    _fact(4, "warning_signs", "Call your doctor for worsening chest pain."),
    _fact(5, "other", "All adults should exercise regularly. This is general education."),
]


def _plan(run_id, dosage="25 mg"):
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "meta": {
            "run_id": run_id,
            "plugin_version": PLUGIN_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        "summary": "You came in for chest pain and will start metoprolol.",
        "summary_fact_ids": [1, 2],
        "reason_for_visit": [{
            "reason": "Chest pain",
            "description": "You came in for chest pain.",
            "source_fact_ids": [1],
        }],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [],
        },
        "medications": [{
            "title": "Metoprolol",
            "plain_name": "metoprolol",
            "why": None,
            "dosage": dosage,
            "frequency": "twice daily",
            "timing": "",
            "duration": "",
            "instructions": "Start this medicine.",
            "side_effects_to_watch": "",
            "change": "Start",
            "status": "to_do",
            "source_fact_ids": [2],
        }],
        "tests": [],
        "procedures": [],
        "other": [],
        "follow_up": [{
            "time_frame": "3 months",
            "description": "Return in 3 months.",
            "status": "to_do",
            "source_fact_ids": [3],
        }],
        "warning_signs": [{
            "symptom": "Worsening chest pain",
            "what_it_might_mean": "",
            "what_to_do": "Call your doctor.",
            "urgency": "call_doctor",
            "related_to": "Chest pain",
            "source_fact_ids": [4],
        }],
        "questions": [{
            "question": "What should I expect at follow-up?",
            "source_fact_ids": [3],
        }],
        "omitted_facts": [{"fact_id": 5, "reason": "generic_not_patient_specific"}],
    }


def _review_raw(overrides=None):
    document = {
        "reviewed_fact_ids": [1, 2, 3, 4, 5],
        "fact_reviews": [
            {"fact_id": 1, "result": "visible_accurate"},
            {"fact_id": 2, "result": "visible_accurate"},
            {"fact_id": 3, "result": "visible_accurate"},
            {"fact_id": 4, "result": "visible_accurate"},
            {"fact_id": 5, "result": "omission_acceptable"},
        ],
        "corrections": [],
        "numeric_resolutions": [],
        "reassemble_fact_ids": [],
    }
    if overrides:
        document.update(overrides)
    return document


class SettlementRunCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = self.temporary.name
        self.run_id = os.path.basename(os.path.normpath(self.run_dir))
        self.plan = _plan(self.run_id)
        self.review = _review_raw()
        self._write_inputs()

    def _write_inputs(self):
        facts = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "run_id": self.run_id,
            "facts": copy.deepcopy(FACTS),
            "dropped": [],
        }
        flags = numeric_parity.build_numeric_flags(
            self.plan, FACTS, run_id=self.run_id, plugin_version=PLUGIN_VERSION,
        )
        _write_json(os.path.join(self.run_dir, "02_facts.json"), facts)
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), self.plan)
        _write_json(os.path.join(self.run_dir, "03_flags.json"), flags)
        _write_json(os.path.join(self.run_dir, "04_review.raw.json"), self.review)

    def _run(self):
        self._write_inputs()
        return settle_review.main(["--run-dir", self.run_dir])

    def _read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as handle:
            return json.load(handle)

    def _mark_needs_correction(self, fact_id):
        for item in self.review["fact_reviews"]:
            if item["fact_id"] == fact_id:
                item["result"] = "visible_needs_correction"

    def _assert_no_outputs(self):
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "04_review.json")))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "05_plan.settled.json")))


class TestSuccessfulSettlement(SettlementRunCase):
    def test_noop_review_writes_valid_exact_copy_and_derived_counts(self):
        self.assertEqual(self._run(), 0)
        review = self._read("04_review.json")
        settled = self._read("05_plan.settled.json")
        self.assertEqual(settled, self.plan)
        self.assertEqual(review["verdict"], "pass")
        self.assertEqual(review["counts"], {
            "facts_reviewed": 5,
            "visible_accurate": 4,
            "visible_needs_correction": 0,
            "omission_acceptable": 1,
            "must_include": 0,
            "corrections": 0,
            "numeric_resolutions": 0,
            "dropped_operations": 0,
            "reassemble_facts": 0,
        })
        self.assertEqual(review["dropped_operations"], [])
        self.assertEqual(validate.validate(review, validate.load_schema("review")), [])
        self.assertEqual(validate.validate(settled, validate.load_schema("care_plan")), [])
        log = runlog.read(self.run_dir)
        self.assertEqual(log["stages"]["review"]["status"], "ok")
        self.assertEqual(log["stages"]["settle_review"]["status"], "ok")

    def test_exact_replace_applies_once_and_resolves_numeric_flag(self):
        self.plan["medications"][0]["dosage"] = "50 mg"
        self._mark_needs_correction(2)
        self.review["corrections"] = [{
            "op": "replace",
            "path": "medications[0].dosage",
            "value": "25 mg",
            "source_fact_ids": [2],
        }]
        flags = numeric_parity.build_numeric_flags(
            self.plan, FACTS, run_id=self.run_id, plugin_version=PLUGIN_VERSION,
        )
        flag_id = flags["numeric_parity"][0]["flag_id"]
        self.review["numeric_resolutions"] = [{
            "flag_id": flag_id,
            "resolution": "corrected",
            "correction_path": "medications[0].dosage",
        }]
        self.assertEqual(self._run(), 0)
        settled = self._read("05_plan.settled.json")
        self.assertEqual(settled["medications"][0]["dosage"], "25 mg")
        expected = copy.deepcopy(self.plan)
        expected["medications"][0]["dosage"] = "25 mg"
        self.assertEqual(settled, expected)

    def test_clear_uses_schema_compatible_empty_value(self):
        self.plan["medications"][0]["why"] = "It is usually a heart medicine."
        self._mark_needs_correction(2)
        self.review["corrections"] = [{"op": "clear", "path": "medications[0].why"}]
        self.assertEqual(self._run(), 0)
        self.assertIsNone(self._read("05_plan.settled.json")["medications"][0]["why"])

    def test_array_remove_preserves_survivor_order(self):
        self.plan["questions"] = [
            {"question": "First question?", "source_fact_ids": [3]},
            {"question": "Unsupported middle question?", "source_fact_ids": [3]},
            {"question": "Last question?", "source_fact_ids": [3]},
        ]
        self._mark_needs_correction(3)
        self.review["corrections"] = [{"op": "remove", "path": "questions[1]"}]
        self.assertEqual(self._run(), 0)
        questions = self._read("05_plan.settled.json")["questions"]
        self.assertEqual([item["question"] for item in questions], ["First question?", "Last question?"])

    def test_pii_rewording_requires_an_explicit_exact_operation(self):
        self.plan["summary"] = "Dr Alok Singh reviewed your chest pain plan."
        self.plan["summary_fact_ids"] = [1]
        self._mark_needs_correction(1)
        self.review["corrections"] = [{
            "op": "replace",
            "path": "summary",
            "value": "Your doctor reviewed your chest pain plan.",
            "source_fact_ids": [1],
        }]
        self.assertEqual(self._run(), 0)
        self.assertEqual(
            self._read("05_plan.settled.json")["summary"],
            "Your doctor reviewed your chest pain plan.",
        )


class TestReviewContractFailures(SettlementRunCase):
    def test_requires_exhaustive_reviewed_fact_ids(self):
        self.review["reviewed_fact_ids"].remove(5)
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_requires_exactly_one_fact_review_per_fact(self):
        self.review["fact_reviews"].pop()
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_rejects_duplicate_fact_reviews(self):
        self.review["fact_reviews"].append({"fact_id": 5, "result": "omission_acceptable"})
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_visible_and_omitted_results_must_match_draft_disposition(self):
        self.review["fact_reviews"][0]["result"] = "omission_acceptable"
        self.review["fact_reviews"][4]["result"] = "visible_accurate"
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_visible_needs_correction_requires_an_operation(self):
        self._mark_needs_correction(2)
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_reassembly_request_refuses_settlement(self):
        self.review["fact_reviews"][4]["result"] = "must_include"
        self.review["reassemble_fact_ids"] = [5]
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()
        log = runlog.read(self.run_dir)
        self.assertEqual(log["stages"]["review"]["status"], "ok")
        self.assertEqual(log["stages"]["settle_review"]["status"], "failed")

    def test_must_include_and_reassemble_ids_must_match(self):
        self.review["reassemble_fact_ids"] = [5]
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_unresolved_numeric_flag_fails(self):
        self.plan["medications"][0]["dosage"] = "50 mg"
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()


class TestOperationFailures(SettlementRunCase):
    def _set_operation(self, operation, fact_id=2):
        self._mark_needs_correction(fact_id)
        self.review["corrections"] = [operation]

    def test_rejects_unknown_operation(self):
        self._set_operation({"op": "append", "path": "medications"})
        self.assertEqual(self._run(), 1)

    def test_rejects_unknown_path(self):
        self._set_operation({
            "op": "replace", "path": "medications[9].dosage", "value": "25 mg",
            "source_fact_ids": [2],
        })
        self.assertEqual(self._run(), 1)

    def test_rejects_protected_system_path(self):
        self._set_operation({
            "op": "replace", "path": "meta.run_id", "value": "other-run",
            "source_fact_ids": [2],
        })
        self.assertEqual(self._run(), 1)

    def test_rejects_citation_path_changes(self):
        self._set_operation({"op": "remove", "path": "medications[0].source_fact_ids[0]"})
        self.assertEqual(self._run(), 1)

    def test_rejects_duplicate_path_operations_apply_once(self):
        self._mark_needs_correction(2)
        operation = {
            "op": "replace", "path": "medications[0].dosage", "value": "25 mg",
            "source_fact_ids": [2],
        }
        self.review["corrections"] = [operation, copy.deepcopy(operation)]
        self.assertEqual(self._run(), 1)

    def test_rejects_parent_remove_and_child_replace(self):
        self._mark_needs_correction(3)
        self.review["corrections"] = [
            {"op": "remove", "path": "questions[0]"},
            {"op": "replace", "path": "questions[0].question", "value": "A new question?",
             "source_fact_ids": [3]},
        ]
        self.assertEqual(self._run(), 1)

    def test_rejects_replace_on_non_scalar_container(self):
        self._set_operation({
            "op": "replace", "path": "medications[0]", "value": "replacement",
            "source_fact_ids": [2],
        })
        self.assertEqual(self._run(), 1)

    def test_rejects_remove_on_non_array_item(self):
        self._set_operation({"op": "remove", "path": "summary"}, fact_id=1)
        self.assertEqual(self._run(), 1)

    def test_rejects_noop_replacement(self):
        self._set_operation({
            "op": "replace", "path": "medications[0].dosage", "value": "25 mg",
            "source_fact_ids": [2],
        })
        self.assertEqual(self._run(), 1)

    def test_rejects_replacement_provenance_not_cited_at_path(self):
        self._set_operation({
            "op": "replace", "path": "summary", "value": "Return in 3 months.",
            "source_fact_ids": [3],
        })
        self.assertEqual(self._run(), 1)

    def test_post_settlement_citation_failure_writes_nothing(self):
        self.plan["summary_fact_ids"] = [1]
        self._set_operation({"op": "remove", "path": "medications[0]"})
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()

    def test_failed_rerun_removes_stale_outputs(self):
        self.assertEqual(self._run(), 0)
        self.review["reviewed_fact_ids"].remove(5)
        self.assertEqual(self._run(), 1)
        self._assert_no_outputs()


class TestSettleReviewCli(SettlementRunCase):
    def test_cli_subprocess(self):
        self._write_inputs()
        script = os.path.join(_paths.SCRIPTS_DIR, "settle_review.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settle_review: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
