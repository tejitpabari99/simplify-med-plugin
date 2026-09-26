import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import finalize  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402


class TestFinalizePreconditions(unittest.TestCase):
    def test_missing_stage_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-precond")
            os.makedirs(run_dir)
            _runfix.make_run_dir(run_dir)
            # Wipe run.json so no stages are recorded.
            os.remove(os.path.join(run_dir, "run.json"))

            rc = finalize._run(run_dir)
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.isfile(os.path.join(run_dir, "06_plan.final.json")))

    def test_failed_stage_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-precond-2")
            os.makedirs(run_dir)
            _runfix.make_run_dir(run_dir)
            runlog.record(run_dir, "ground", "failed")

            rc = finalize._run(run_dir)
            self.assertEqual(rc, 1)

    def test_cli_precondition_failure_prints_to_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-precond-3")
            os.makedirs(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "finalize.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unitize", result.stderr)


class TestFinalizeEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = os.path.join(self._tmp.name, "run-e2e")
        os.makedirs(self.run_dir)
        self.run_id = _runfix.make_run_dir(self.run_dir)
        self.rc = finalize._run(self.run_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_success_exit_code(self):
        self.assertEqual(self.rc, 0)

    def test_final_and_report_files_written(self):
        for name in ("06_plan.final.json", "report.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.run_dir, name)), name)

    def test_html_report_not_written(self):
        # report.html is an on-request follow-up (render_html.py), not part
        # of the default finalize output.
        self.assertFalse(os.path.isfile(os.path.join(self.run_dir, "report.html")))

    def _final_plan(self):
        with open(os.path.join(self.run_dir, "06_plan.final.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_addition_merged(self):
        plan = self._final_plan()
        titles = [m["title"] for m in plan["medications"]]
        self.assertIn("Aspirin", titles)

        run_log = runlog.read(self.run_dir)
        self.assertEqual(run_log["stages"]["finalize"]["checks"]["additions_merged"], 1)

    def test_absent_glossary_term_dropped(self):
        plan = self._final_plan()
        self.assertNotIn(_runfix.ABSENT_GLOSSARY_TERM, plan["terms"])
        self.assertEqual(len(plan["terms"]), 2)

        run_log = runlog.read(self.run_dir)
        checks = run_log["stages"]["finalize"]["checks"]
        self.assertEqual(checks["glossary_terms_in"], 3)
        self.assertEqual(checks["glossary_terms_kept"], 2)

    def test_pii_name_replaced_and_counted(self):
        plan = self._final_plan()
        blob = json.dumps(plan)
        self.assertNotIn(_runfix.PII_NAME, blob)
        self.assertIn("your doctor", blob)

        run_log = runlog.read(self.run_dir)
        self.assertGreaterEqual(run_log["stages"]["finalize"]["checks"]["pii_substitutions"], 1)

    def test_notice_added_when_using_draft_fallback(self):
        # The fixture has no 05_plan.corrected.json, so finalize falls back
        # to the draft and must add the "not every check" notice.
        plan = self._final_plan()
        self.assertIn("We could not run every check on this summary.", plan["notices"])

        run_log = runlog.read(self.run_dir)
        self.assertEqual(run_log["stages"]["finalize"]["status"], "degraded")

    def test_final_plan_validates_against_schema(self):
        plan = self._final_plan()
        schema = validate.load_schema("care_plan")
        errors = validate.validate(plan, schema)
        self.assertEqual(errors, [])

    def test_run_json_has_finalize_stage(self):
        run_log = runlog.read(self.run_dir)
        self.assertIn("finalize", run_log["stages"])
        self.assertIn("checks", run_log["stages"]["finalize"])
        checks = run_log["stages"]["finalize"]["checks"]
        for key in (
            "plan_source", "additions_merged", "items_dropped_uncited",
            "glossary_terms_in", "glossary_terms_kept", "pii_substitutions",
            "before_grade", "after_grade", "notices",
        ):
            self.assertIn(key, checks)

    def test_low_priority_marker_absent_from_reports(self):
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertNotIn(_runfix.LOW_PRIORITY_MARKER, md)

    def test_readability_scores_computed(self):
        plan = self._final_plan()
        self.assertIsNotNone(plan["score"]["before_grade"])
        self.assertIsNotNone(plan["score"]["after_grade"])


class TestFinalizeCorrectedPreferred(unittest.TestCase):
    def test_prefers_corrected_over_draft(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-corrected")
            os.makedirs(run_dir)
            _runfix.make_run_dir(run_dir)

            with open(os.path.join(run_dir, "03_plan.draft.json"), encoding="utf-8") as f:
                plan = json.load(f)
            plan["summary"] = "Corrected summary text goes here for the visit."
            with open(os.path.join(run_dir, "05_plan.corrected.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f)
            runlog.record(run_dir, "correct", "ok")

            rc = finalize._run(run_dir)
            self.assertEqual(rc, 0)

            with open(os.path.join(run_dir, "06_plan.final.json"), encoding="utf-8") as f:
                final_plan = json.load(f)
            self.assertEqual(final_plan["summary"], "Corrected summary text goes here for the visit.")
            # No fallback notice, since a corrected plan was used.
            self.assertNotIn("We could not run every check on this summary.", final_plan["notices"])


class TestFinalizeCLI(unittest.TestCase):
    def test_cli_success_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-cli")
            os.makedirs(run_dir)
            _runfix.make_run_dir(run_dir)

            script = os.path.join(_paths.SCRIPTS_DIR, "finalize.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("report.md", result.stdout)
            self.assertNotIn("report.html", result.stdout)
            self.assertIn("Reading level", result.stdout)
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "06_plan.final.json")))


if __name__ == "__main__":
    unittest.main()
