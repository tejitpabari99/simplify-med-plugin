import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_md  # noqa: E402
from test_plan_view import NOTICE_MARKER, OMITTED_MARKER, _base_plan  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def _write_completed_run(run_dir, run_id="run-1"):
    _write_json(os.path.join(run_dir, "run.json"), {"run_id": run_id, "stages": {"finalize": {"status": "ok"}}})


class TestRenderMd(unittest.TestCase):
    def test_v2_report_is_concise_and_patient_safe(self):
        text = render_md.render(_base_plan())
        self.assertTrue(text.startswith("# Your visit, explained"))
        self.assertIn("1. Do I need another heart tracing?", text)
        self.assertNotIn("Medical terms explained", text)
        for hidden in (NOTICE_MARKER, OMITTED_MARKER, "Reading level:", "omitted_facts", "source_fact_ids"):
            self.assertNotIn(hidden, text)

    def test_v1_final_report_remains_renderable(self):
        text = render_md.render(_base_plan("1.0"))
        self.assertIn("1. Do I need another heart tracing?", text)
        self.assertNotIn(OMITTED_MARKER, text)
        self.assertNotIn("Medical terms explained", text)

    def test_cli_writes_only_default_markdown_for_v2(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "06_plan.final.json"), _base_plan())
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(os.listdir(run_dir)), ["06_plan.final.json", "report.md", "run.json"])

    def test_cli_allows_completed_v1_final_report(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "06_plan.final.json"), _base_plan("1.0"))
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "report.md")))

    def test_cli_rejects_partial_v1_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan_path = os.path.join(run_dir, "03_plan.draft.json")
            _write_json(plan_path, _base_plan("1.0"))
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir, "--plan", plan_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed schema-v1 final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.md")))


if __name__ == "__main__":
    unittest.main()
