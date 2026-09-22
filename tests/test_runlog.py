import json
import os
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
            self.assertEqual(data["schema_version"], "1.0")
            self.assertEqual(data["level"], "standard")
            self.assertIn("unitize", data["stages"])
            self.assertEqual(data["stages"]["unitize"]["status"], "ok")
            self.assertIsNotNone(data["stages"]["unitize"]["started_at"])
            self.assertIsNotNone(data["stages"]["unitize"]["finished_at"])

    def test_upsert_merges_checks(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-002")
            os.makedirs(run_dir)
            runlog.record(run_dir, "ground", "ok", checks={"a": 1})
            runlog.record(run_dir, "ground", "ok", checks={"b": 2})

            data = runlog.read(run_dir)
            checks = data["stages"]["ground"]["checks"]
            self.assertEqual(checks, {"a": 1, "b": 2})

    def test_started_at_set_once(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-003")
            os.makedirs(run_dir)
            runlog.record(run_dir, "ground", "ok", started=True)
            first = runlog.read(run_dir)["stages"]["ground"]["started_at"]
            runlog.record(run_dir, "ground", "ok", started=True)
            second = runlog.read(run_dir)["stages"]["ground"]["started_at"]
            self.assertEqual(first, second)

    def test_notice_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-004")
            os.makedirs(run_dir)
            runlog.record(run_dir, "ground", "ok")
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
            runlog.record(run_dir, "ground", "ok")
            runlog.notice(run_dir, "hello")

            entries = os.listdir(run_dir)
            self.assertEqual(entries, ["run.json"])
            for entry in entries:
                self.assertFalse(entry.endswith(".tmp"))

    def test_set_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-006")
            os.makedirs(run_dir)
            runlog.record(run_dir, "ground", "ok")
            runlog.set_inputs(run_dir, [{"file": "a.txt", "extraction_method": "native", "pages": 1}])
            data = runlog.read(run_dir)
            self.assertEqual(len(data["inputs"]), 1)
            self.assertEqual(data["inputs"][0]["file"], "a.txt")

    def test_result_validates_against_run_schema(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-007")
            os.makedirs(run_dir)
            runlog.record(run_dir, "ground", "ok", checks={"a": 1}, attempts=1)
            runlog.record(run_dir, "assemble", "degraded", checks={"b": 2}, attempts=2)
            runlog.notice(run_dir, "a notice")
            runlog.set_inputs(run_dir, [{"file": "a.txt", "extraction_method": "native", "pages": 1}])

            data = runlog.read(run_dir)
            schema = validate.load_schema("run")
            errors = validate.validate(data, schema)
            self.assertEqual(errors, [])

    def test_plugin_version_reads_meta(self):
        version = runlog.plugin_version()
        self.assertEqual(version, "0.1.0")

    def test_read_missing_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-008")
            os.makedirs(run_dir)
            self.assertEqual(runlog.read(run_dir), {})


if __name__ == "__main__":
    unittest.main()
