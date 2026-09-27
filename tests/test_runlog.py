import json
import os
import threading
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import runlog  # noqa: E402
import validate  # noqa: E402


class TestRunlog(unittest.TestCase):
    def test_record_creates_run_json(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-001")
            os.makedirs(run_dir)
            runlog.record(run_dir, "unitize", "ok")

            path = os.path.join(run_dir, "run.json")
            self.assertTrue(os.path.isfile(path))
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertEqual(data["run_id"], "run-001")
            self.assertEqual(data["schema_version"], "3.0")
            self.assertEqual(data["level"], "standard")
            self.assertIn("unitize", data["stages"])
            self.assertEqual(data["stages"]["unitize"]["status"], "ok")
            self.assertIsNotNone(data["stages"]["unitize"]["started_at"])
            self.assertIsNotNone(data["stages"]["unitize"]["finished_at"])
            self.assertEqual(data["stages"]["unitize"]["attempts"], 1)
            self.assertEqual(data["stages"]["unitize"]["artifacts"], [])

    def test_rejects_unknown_stage_and_invalid_core_status(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "run"))
            with self.assertRaises(ValueError):
                runlog.record(os.path.join(d, "run"), "review_fidelity", "ok")
            for retired in ("ground", "assemble", "plan_check", "numeric_parity", "review", "settle_review"):
                with self.assertRaises(ValueError):
                    runlog.record(os.path.join(d, "run"), retired, "ok")
            with self.assertRaises(ValueError):
                runlog.record(os.path.join(d, "run"), "write", "degraded")

    def test_only_settle_may_request_repair(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            runlog.initialize(run_dir, "run", [])
            runlog.record(run_dir, "settle", "repair_requested", checks={"round": 1}, run_id="run")
            for stage in ("unitize", "write", "check", "verify", "finalize", "glossary"):
                with self.assertRaises(ValueError):
                    runlog.record(run_dir, stage, "repair_requested")
            runlog.record(run_dir, "settle", "ok", checks={"round": 2}, run_id="run")
            data = runlog.read(run_dir)
            self.assertEqual(data["stages"]["settle"]["status"], "ok")
            self.assertEqual(data["stages"]["settle"]["attempts"], 2)
            self.assertEqual(validate.validate(data, validate.load_schema("run")), [])

    def test_core_stage_names(self):
        self.assertEqual(
            runlog._CORE_STAGES, {"unitize", "write", "check", "verify", "settle", "finalize"},
        )

    def test_upsert_merges_checks(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-002")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok", checks={"a": 1})
            runlog.record(run_dir, "write", "ok", checks={"b": 2})

            data = runlog.read(run_dir)
            checks = data["stages"]["write"]["checks"]
            self.assertEqual(checks, {"a": 1, "b": 2})

    def test_started_at_set_once(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-003")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok", started=True, finished=False)
            first = runlog.read(run_dir)["stages"]["write"]["started_at"]
            runlog.record(run_dir, "write", "ok", started=True, finished=False)
            second = runlog.read(run_dir)["stages"]["write"]["started_at"]
            self.assertEqual(first, second)
            self.assertEqual(runlog.read(run_dir)["stages"]["write"]["attempts"], 2)

    def test_finishing_an_open_attempt_does_not_increment_it(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok", started=True, finished=False)
            runlog.record(run_dir, "write", "ok", finished=True)
            self.assertEqual(runlog.read(run_dir)["stages"]["write"]["attempts"], 1)

    def test_notice_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-004")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok")
            runlog.notice(run_dir, "duplicate")
            runlog.notice(run_dir, "duplicate")
            runlog.notice(run_dir, "other")

            data = runlog.read(run_dir)
            self.assertEqual(data["notices"].count("duplicate"), 1)
            self.assertIn("other", data["notices"])

    def test_atomic_write_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-005")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok")
            runlog.notice(run_dir, "hello")

            entries = os.listdir(run_dir)
            self.assertEqual(entries, ["run.json"])
            for entry in entries:
                self.assertFalse(entry.endswith(".tmp"))

    def test_set_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-006")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok")
            runlog.set_inputs(run_dir, [{"file": "a.txt", "extraction_method": "native", "pages": 1, "sha256": "abc"}])
            data = runlog.read(run_dir)
            self.assertEqual(len(data["inputs"]), 1)
            self.assertEqual(data["inputs"][0]["file"], "a.txt")

    def test_result_validates_against_run_schema(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-007")
            os.makedirs(run_dir)
            runlog.record(run_dir, "write", "ok", checks={"a": 1}, attempts=1, artifacts=["02_draft.raw.json"])
            runlog.record(run_dir, "render_html", "skipped", skip_reason="not requested")
            runlog.notice(run_dir, "a notice")
            runlog.set_inputs(run_dir, [{"file": "a.txt", "extraction_method": "native", "pages": 1, "sha256": "abc"}])

            data = runlog.read(run_dir)
            schema = validate.load_schema("run")
            errors = validate.validate(data, schema)
            self.assertEqual(errors, [])

    def test_artifacts_skip_reasons_and_current_run_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            os.makedirs(run_dir)
            runlog.initialize(run_dir, "fresh-run", [])
            runlog.record(run_dir, "write", "ok", artifacts=["02_draft.raw.json"], run_id="fresh-run")
            runlog.record(run_dir, "glossary", "skipped", skip_reason="not requested", run_id="fresh-run")

            data = runlog.read(run_dir)
            self.assertEqual(data["stages"]["write"]["artifacts"], [{"path": "02_draft.raw.json"}])
            self.assertEqual(data["stages"]["glossary"]["skip_reason"], "not requested")
            with self.assertRaises(ValueError):
                runlog.record(run_dir, "check", "ok", run_id="stale-run")

    def test_parallel_updates_do_not_lose_checks(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            os.makedirs(run_dir)
            runlog.initialize(run_dir, "parallel-run", [])

            threads = [
                threading.Thread(
                    target=runlog.record,
                    args=(run_dir, "write", "ok"),
                    kwargs={"checks": {f"check_{index}": index}, "run_id": "parallel-run"},
                )
                for index in range(12)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            checks = runlog.read(run_dir)["stages"]["write"]["checks"]
            self.assertEqual(checks, {f"check_{index}": index for index in range(12)})

    def test_plugin_version_reads_portable_manifest(self):
        version = runlog.plugin_version()
        with open(os.path.join(_paths.REPO_ROOT, "plugin.json"), "r", encoding="utf-8") as f:
            self.assertEqual(version, json.load(f)["version"])

    def test_read_missing_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-008")
            os.makedirs(run_dir)
            self.assertEqual(runlog.read(run_dir), {})


if __name__ == "__main__":
    unittest.main()
