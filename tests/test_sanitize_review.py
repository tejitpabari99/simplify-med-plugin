import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import runlog  # noqa: E402
import sanitize_review  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _fact(id_, category, unit_id, quote, text):
    return {
        "id": id_, "category": category, "unit_id": unit_id,
        "quote": quote, "char_start": 0, "char_end": len(quote), "text": text,
    }


def _facts_doc(run_id):
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "facts": [
            _fact(1, "reason_for_visit", 1, "annual checkup", "Annual checkup"),
            _fact(2, "medications", 2, "continue metoprolol 25 mg twice daily", "Continue metoprolol 25mg twice daily"),
            _fact(3, "medications", 3, "start aspirin 81mg daily", "Start aspirin 81mg daily"),
            _fact(4, "tests", 4, "order fasting lipid panel", "Order fasting lipid panel"),
            _fact(5, "warning_signs", 5, "call doctor if chest pain", "Call doctor if chest pain occurs"),
            _fact(6, "tests", 6, "blood pressure checked, normal", "Blood pressure checked, normal"),
        ],
        "dropped": [],
    }


def _plan_draft(run_id):
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "summary": "You had a checkup and are continuing your heart medications.",
        "summary_fact_ids": [1, 2],
        "reason_for_visit": [
            {"reason": "Annual checkup", "description": "You came in for your yearly checkup.", "source_fact_ids": [1]},
        ],
        "diagnosis": {"changed_since_last_visit": "", "changed_since_last_visit_fact_ids": [], "details": []},
        "medications": [
            {
                "title": "Metoprolol", "plain_name": "a heart medicine", "why": "to help your heart",
                "dosage": "25 mg", "frequency": "twice a day", "timing": "", "duration": "",
                "instructions": "Take with food.", "side_effects_to_watch": "", "change": "",
                "status": "to_do", "source_fact_ids": [2],
            },
            {
                "title": "Aspirin", "plain_name": "a blood thinner", "why": "to help prevent clots",
                "dosage": "81 mg", "frequency": "once a day", "timing": "", "duration": "",
                "instructions": "", "side_effects_to_watch": "", "change": "",
                "status": "to_do", "source_fact_ids": [3],
            },
        ],
        "tests": [
            {
                "title": "Lipid panel", "plain_name": "a cholesterol test", "why": "to check your cholesterol",
                "description": "A blood test.", "preparation": "Fast for 12 hours.",
                "status": "to_do", "source_fact_ids": [4],
            },
        ],
        "procedures": [],
        "other": [],
        "follow_up": [],
        "warning_signs": [
            {
                "symptom": "Chest pain", "what_it_might_mean": "A heart problem.",
                "what_to_do": "Call your doctor right away.", "urgency": "call_doctor",
                "related_to": "", "source_fact_ids": [5],
            },
        ],
        "questions": [
            "Should I stop taking aspirin before any procedure?",
            "How long will I need to take metoprolol?",
        ],
        "low_priority": [],
        "terms": {},
    }


class _RunDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = self._tmp.name
        self.run_id = os.path.basename(os.path.normpath(self.run_dir))
        self.addCleanup(self._tmp.cleanup)
        _write_json(os.path.join(self.run_dir, "02_facts.json"), _facts_doc(self.run_id))
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), _plan_draft(self.run_id))

    def _write_review_raw(self, corrections, verdict="needs_correction"):
        _write_json(os.path.join(self.run_dir, "04_review.raw.json"), {
            "verdict": verdict, "corrections": corrections,
        })

    def _write_coverage_raw(self, coverage):
        _write_json(os.path.join(self.run_dir, "04_coverage.raw.json"), {"coverage": coverage})

    def _read_review(self):
        with open(os.path.join(self.run_dir, "04_review.json"), "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_coverage(self):
        with open(os.path.join(self.run_dir, "04_coverage.json"), "r", encoding="utf-8") as f:
            return json.load(f)


class TestReviewSanitize(_RunDirTestCase):
    def test_unresolvable_path_dropped(self):
        self._write_review_raw([
            {"op": "correct", "path": "medications[5].why", "value": "x"},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(doc["corrections"], [])
        self.assertEqual(len(doc["dropped"]), 1)
        self.assertEqual(doc["dropped"][0]["reason"], "unresolvable_path")

    def test_not_stated_on_non_why_path_dropped(self):
        self._write_review_raw([
            {"op": "not_stated", "path": "medications[0].dosage"},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(doc["corrections"], [])
        self.assertEqual(doc["dropped"][0]["reason"], "not_stated_outside_why")

    def test_not_stated_on_why_path_kept(self):
        self._write_review_raw([
            {"op": "not_stated", "path": "medications[0].why"},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(len(doc["corrections"]), 1)
        self.assertEqual(doc["dropped"], [])

    def test_correct_without_value_dropped(self):
        self._write_review_raw([
            {"op": "correct", "path": "medications[0].dosage", "value": ""},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(doc["corrections"], [])
        self.assertEqual(doc["dropped"][0]["reason"], "correct_without_value")

    def test_correct_or_not_stated_on_summary_dropped(self):
        self._write_review_raw([
            {"op": "correct", "path": "summary", "value": "New summary."},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(doc["corrections"], [])
        self.assertEqual(doc["dropped"][0]["reason"], "summary_only_remove")

    def test_remove_on_summary_kept(self):
        self._write_review_raw([{"op": "remove", "path": "summary"}])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(len(doc["corrections"]), 1)

    def test_remove_wins_over_correct_same_item(self):
        self._write_review_raw([
            {"op": "correct", "path": "medications[0].dosage", "value": "50 mg"},
            {"op": "remove", "path": "medications[0]"},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(len(doc["corrections"]), 1)
        self.assertEqual(doc["corrections"][0]["op"], "remove")
        reasons = [d["reason"] for d in doc["dropped"]]
        self.assertIn("removed_item", reasons)

    def test_duplicate_corrections_deduped(self):
        self._write_review_raw([
            {"op": "correct", "path": "medications[0].dosage", "value": "50 mg"},
            {"op": "correct", "path": "medications[0].dosage", "value": "50 mg"},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(len(doc["corrections"]), 1)
        reasons = [d["reason"] for d in doc["dropped"]]
        self.assertIn("duplicate", reasons)

    def test_absent_raw_is_skipped_with_pass_verdict(self):
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        self.assertEqual(doc["verdict"], "pass")
        self.assertEqual(doc["corrections"], [])
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["review_fidelity"]["status"], "skipped")

    def test_schema_invalid_raw_fails(self):
        _write_json(os.path.join(self.run_dir, "04_review.raw.json"), {"verdict": "bogus", "corrections": []})
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 1)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["review_fidelity"]["status"], "failed")

    def test_output_matches_schema(self):
        self._write_review_raw([{"op": "remove", "path": "warning_signs[0]"}])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_review()
        errors = validate.validate(doc, validate.load_schema("review"))
        self.assertEqual(errors, [])


class TestCoverageSanitize(_RunDirTestCase):
    def test_backfill_and_missing(self):
        self._write_coverage_raw([
            {"fact_id": 1, "present": True},
            {"fact_id": 2, "present": True},
            {"fact_id": 3, "present": True},
            {"fact_id": 4, "present": False},
            # 5 and 6 omitted by the agent -- must be backfilled as present=False.
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_coverage()
        self.assertEqual([c["fact_id"] for c in doc["coverage"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(doc["missing"], [4, 5, 6])
        data = runlog.read(self.run_dir)
        checks = data["stages"]["review_coverage"]["checks"]
        self.assertEqual(checks["facts"], 6)
        self.assertEqual(checks["backfilled"], 2)
        self.assertEqual(checks["missing"], 3)

    def test_unknown_fact_id_dropped(self):
        self._write_coverage_raw([
            {"fact_id": 1, "present": True},
            {"fact_id": 999, "present": True},
        ])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_coverage()
        ids = [c["fact_id"] for c in doc["coverage"]]
        self.assertNotIn(999, ids)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["review_coverage"]["checks"]["unknown_dropped"], 1)

    def test_absent_raw_is_skipped_no_invented_misses(self):
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_coverage()
        self.assertEqual(doc["coverage"], [])
        self.assertEqual(doc["missing"], [])
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["review_coverage"]["status"], "skipped")

    def test_schema_invalid_raw_fails(self):
        _write_json(os.path.join(self.run_dir, "04_coverage.raw.json"), {"coverage": [{"fact_id": "not-an-int", "present": True}]})
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 1)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["review_coverage"]["status"], "failed")

    def test_output_matches_schema(self):
        self._write_coverage_raw([{"fact_id": 1, "present": True}])
        rc = sanitize_review.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        doc = self._read_coverage()
        errors = validate.validate(doc, validate.load_schema("coverage"))
        self.assertEqual(errors, [])


class TestOnlyFlag(_RunDirTestCase):
    def test_only_review_skips_coverage(self):
        self._write_review_raw([{"op": "remove", "path": "warning_signs[0]"}])
        self._write_coverage_raw([{"fact_id": 1, "present": True}])
        rc = sanitize_review.main(["--run-dir", self.run_dir, "--only", "review"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "04_review.json")))
        self.assertFalse(os.path.isfile(os.path.join(self.run_dir, "04_coverage.json")))

    def test_only_coverage_skips_review(self):
        self._write_review_raw([{"op": "remove", "path": "warning_signs[0]"}])
        self._write_coverage_raw([{"fact_id": 1, "present": True}])
        rc = sanitize_review.main(["--run-dir", self.run_dir, "--only", "coverage"])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.isfile(os.path.join(self.run_dir, "04_review.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "04_coverage.json")))


class TestCli(_RunDirTestCase):
    def test_cli_subprocess(self):
        self._write_review_raw([{"op": "remove", "path": "warning_signs[0]"}])
        self._write_coverage_raw([{"fact_id": 1, "present": True}])
        script = os.path.join(_paths.SCRIPTS_DIR, "sanitize_review.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "04_review.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "04_coverage.json")))


if __name__ == "__main__":
    unittest.main()
