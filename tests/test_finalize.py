"""FINALIZE stage: scripts/finalize.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import finalize  # noqa: E402
import render_md  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


class FinalizeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = os.path.join(self.temporary.name, "run-final")
        self.run_id = _runfix.make_run_dir(self.run_dir)

    def path(self, name):
        return os.path.join(self.run_dir, name)

    def finalize(self):
        return _runfix.call(finalize.main, "--run-dir", self.run_dir)

    def assert_refused(self, fragment):
        code, out, err = self.finalize()
        self.assertEqual(code, 1, out + err)
        self.assertIn("no clinical report was produced", err)
        self.assertIn(fragment, err)
        for name in ("05_plan.final.json", "report.md"):
            self.assertFalse(os.path.exists(self.path(name)), name)


class TestPublish(FinalizeCase):
    def test_publishes_final_plan_and_report(self):
        runlog.notice(self.run_dir, "One page was read with OCR.")
        code, out, err = self.finalize()
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], self.path("report.md"))
        self.assertRegex(lines[-1], r"^finalize: ok \| round=1 words=\d+ pii_substitutions=0 ")
        plan = _runfix.read_json(self.path("05_plan.final.json"))
        self.assertEqual(validate.validate(plan, validate.load_schema("plan")), [])
        self.assertEqual(plan["schema_version"], SCHEMA_VERSION)
        self.assertEqual(plan["plugin_version"], runlog.plugin_version())
        self.assertEqual(plan["run_id"], self.run_id)
        self.assertEqual(plan["notices"], ["One page was read with OCR."])
        self.assertIsNotNone(plan["score"]["before_grade"])
        self.assertIsNotNone(plan["score"]["after_grade"])
        settled = _runfix.read_json(self.path("04_plan.settled.json"))
        for key, value in settled.items():
            if key not in ("schema_version", "run_id"):
                self.assertEqual(plan[key], value, key)
        with open(self.path("report.md"), encoding="utf-8") as handle:
            report = handle.read()
        self.assertEqual(report, render_md.render(plan))
        self.assertNotIn(_runfix.NOISE_MARKER, report)
        self.assertNotIn(_runfix.PII_NAME, report)
        stage = runlog.read(self.run_dir)["stages"]["finalize"]
        self.assertEqual(stage["status"], "ok")
        self.assertEqual(stage["checks"]["word_count"], plan["word_count"])

    def test_rerun_is_idempotent(self):
        self.assertEqual(self.finalize()[0], 0)
        self.assertEqual(self.finalize()[0], 0)


class TestRefusals(FinalizeCase):
    def test_required_stage_must_be_ok(self):
        runlog.record(self.run_dir, "verify", "failed", run_id=self.run_id)
        self.assert_refused("required stage verify must have status ok")

    def test_missing_artifact(self):
        os.remove(self.path("03_verify.json"))
        self.assert_refused("missing required artifact 03_verify.json")

    def test_tampered_settled_plan(self):
        settled = _runfix.read_json(self.path("04_plan.settled.json"))
        settled["findings"][0]["result"] = "Everything was normal."
        _runfix.write_json(self.path("04_plan.settled.json"), settled)
        self.assert_refused("04_plan.settled.json does not match the verifier's operations")

    def test_tampered_checked_draft(self):
        draft = _runfix.read_json(self.path("02_draft.json"))
        draft["why_you_went"]["text"] = "You went to the ER."
        _runfix.write_json(self.path("02_draft.json"), draft)
        self.assert_refused("02_draft.json does not match 02_draft.raw.json")

    def test_artifact_from_another_run(self):
        check = _runfix.read_json(self.path("02_check.json"))
        check["run_id"] = "stale-run"
        _runfix.write_json(self.path("02_check.json"), check)
        self.assert_refused("02_check.json run_id does not match the current run")

    def test_older_run_log_is_refused(self):
        run_log = _runfix.read_json(self.path("run.json"))
        run_log["schema_version"] = "2.0"
        _runfix.write_json(self.path("run.json"), run_log)
        self.assert_refused("Start a new run from the original documents")

    def test_repair_request_without_round_two_is_refused(self):
        _runfix.write_json(self.path("04_repair.json"), {
            "schema_version": SCHEMA_VERSION, "run_id": self.run_id, "missing": [], "settled_draft": {},
        })
        self.assert_refused("was not completed for the final round 2")

    def test_stale_outputs_are_removed_on_failure(self):
        self.assertEqual(self.finalize()[0], 0)
        os.remove(self.path("04_plan.settled.json"))
        self.assert_refused("04_plan.settled.json")


class TestHelpers(unittest.TestCase):
    def test_pii_sweep_substitutes_bounded_shapes(self):
        swept, count = finalize.pii_sweep({"a": ["See Dr. Alok Singh.", "Jane Smith, MD called."], "b": 3})
        self.assertEqual(swept, {"a": ["See your doctor.", "your doctor called."], "b": 3})
        self.assertEqual(count, 2)

    def test_source_text_skips_boilerplate(self):
        units = {
            1: {"text": "Headache."},
            2: {"text": "https://example.test", "skip": "url"},
            3: {"text": "Discharged."},
        }
        self.assertEqual(finalize.source_text(units), "Headache.\nDischarged.")


if __name__ == "__main__":
    unittest.main()
