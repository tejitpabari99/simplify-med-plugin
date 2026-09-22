import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import diff_guard  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _plan_draft():
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "summary": "You had a checkup and are continuing your heart medications, seen by Doctor Alok Singh.",
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
        self.addCleanup(self._tmp.cleanup)
        self.draft = _plan_draft()
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), self.draft)

    def _write_review(self, corrections):
        _write_json(os.path.join(self.run_dir, "04_review.json"), {
            "schema_version": SCHEMA_VERSION, "plugin_version": PLUGIN_VERSION,
            "run_id": os.path.basename(self.run_dir), "verdict": "needs_correction",
            "corrections": corrections, "dropped": [],
        })

    def _write_corrected_raw(self, doc):
        _write_json(os.path.join(self.run_dir, "05_plan.corrected.raw.json"), doc)

    def _out(self):
        return _read_json(os.path.join(self.run_dir, "05_plan.corrected.json"))


class TestSkipped(_RunDirTestCase):
    def test_skipped_when_no_corrections(self):
        self._write_review([])
        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        self.assertEqual(self._out(), self.draft)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["status"], "skipped")

    def test_skipped_when_raw_corrected_absent(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        self.assertEqual(self._out(), self.draft)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["status"], "skipped")

    def test_skipped_when_no_review_file(self):
        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        self.assertEqual(self._out(), self.draft)


class TestFaithfulApplication(_RunDirTestCase):
    def test_correct_applied(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["dosage"] = "50 mg"
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        self.assertEqual(out["medications"][0]["dosage"], "50 mg")

        data = runlog.read(self.run_dir)
        checks = data["stages"]["correct"]["checks"]
        self.assertEqual(checks["corrections"], 1)
        self.assertEqual(checks["applied"], 1)
        self.assertEqual(checks["unapplied"], 0)

    def test_not_stated_applied_sets_null(self):
        self._write_review([{"op": "not_stated", "path": "medications[0].why"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["why"] = None
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        self.assertIsNone(out["medications"][0]["why"])
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["checks"]["applied"], 1)

    def test_remove_shifts_indices_correctly(self):
        self._write_review([{"op": "remove", "path": "medications[0]"}])
        corrected = copy.deepcopy(self.draft)
        del corrected["medications"][0]
        # Also drop the removed item's source_fact_ids from summary_fact_ids? Not required --
        # only the removed item's own ids disappear with it; summary_fact_ids cites fact 2
        # (the removed item's fact) which is allowed to remain untouched here since the
        # correction only names the array item, not summary_fact_ids.
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        self.assertEqual(len(out["medications"]), 1)
        self.assertEqual(out["medications"][0]["title"], "Aspirin")
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["status"], "ok")

    def test_pii_substitution_within_token_delta_passes(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["dosage"] = "50 mg"
        # Bounded PII swap on an eligible field ("summary") not named by any correction.
        corrected["summary"] = corrected["summary"].replace("Doctor Alok Singh", "your doctor")
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        self.assertIn("your doctor", out["summary"])
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["checks"]["pii_substitutions"], 1)


class TestViolations(_RunDirTestCase):
    def test_unnamed_field_change_is_violation_non_strict_degrades(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["dosage"] = "50 mg"
        # Unnamed, non-PII-eligible-field change: frequency was not corrected.
        corrected["medications"][0]["frequency"] = "three times a day"
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        self.assertEqual(out, self.draft)  # fell back to the draft
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["status"], "degraded")
        self.assertTrue(any("frequency" in v for v in data["stages"]["correct"]["checks"]["violations"]))
        self.assertTrue(any("safely apply every correction" in n for n in data["notices"]))

    def test_unnamed_field_change_is_violation_strict_exits_1(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["dosage"] = "50 mg"
        corrected["medications"][0]["frequency"] = "three times a day"
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir, "--strict"])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.isfile(os.path.join(self.run_dir, "05_plan.corrected.json")))

    def test_length_change_without_remove_is_violation(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["dosage"] = "50 mg"
        del corrected["medications"][1]  # dropped an item with no "remove" correction naming it
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir, "--strict"])
        self.assertEqual(rc, 1)

    def test_schema_invalid_raw_always_exits_1(self):
        self._write_review([{"op": "correct", "path": "medications[0].dosage", "value": "50 mg"}])
        corrected = copy.deepcopy(self.draft)
        corrected["medications"][0]["status"] = "not_a_valid_status"
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 1)
        data = runlog.read(self.run_dir)
        self.assertEqual(data["stages"]["correct"]["status"], "failed")


class TestOutputSchema(_RunDirTestCase):
    def test_output_validates_against_care_plan_schema(self):
        self._write_review([{"op": "remove", "path": "warning_signs[0]"}])
        corrected = copy.deepcopy(self.draft)
        del corrected["warning_signs"][0]
        self._write_corrected_raw(corrected)

        rc = diff_guard.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out = self._out()
        errors = validate.validate(out, validate.load_schema("care_plan"))
        self.assertEqual(errors, [])


class TestCli(_RunDirTestCase):
    def test_cli_subprocess(self):
        self._write_review([])
        script = os.path.join(_paths.SCRIPTS_DIR, "diff_guard.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "05_plan.corrected.json")))


if __name__ == "__main__":
    unittest.main()
