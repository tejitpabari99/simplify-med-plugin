import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_html  # noqa: E402
from test_plan_view import NOTICE_MARKER, OMITTED_MARKER, _base_plan, _glossary_doc  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _write_completed_run(run_dir, run_id="run-1"):
    _write_json(os.path.join(run_dir, "run.json"), {"run_id": run_id, "stages": {"finalize": {"status": "ok"}}})


class TestRenderHtml(unittest.TestCase):
    def test_v2_html_never_embeds_internal_plan_data(self):
        html = render_html.render(_base_plan())
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("Do I need another heart tracing?", html)
        self.assertNotIn('id="simplify-med-plan"', html)
        for hidden in (NOTICE_MARKER, OMITTED_MARKER, "Reading level:", "omitted_facts", "source_fact_ids"):
            self.assertNotIn(hidden, html)

    def test_optional_glossary_enriches_html_without_mutating_inputs(self):
        plan = _base_plan()
        glossary = _glossary_doc()
        before_plan = copy.deepcopy(plan)
        before_glossary = copy.deepcopy(glossary)
        html = render_html.render(plan, glossary=glossary)
        self.assertIn("Medical terms explained", html)
        self.assertIn('class="term"', html)
        self.assertIn('data-def="A scan that uses magnets."', html)
        self.assertEqual(plan, before_plan)
        self.assertEqual(glossary, before_glossary)

    def test_default_html_has_no_glossary(self):
        html = render_html.render(_base_plan())
        self.assertNotIn("Medical terms explained", html)
        self.assertNotIn('class="term"', html)

    def test_v1_report_and_legacy_terms_remain_renderable(self):
        html = render_html.render(_base_plan("1.0"), legacy_glossary=True)
        self.assertIn("Do I need another heart tracing?", html)
        self.assertIn("Medical terms explained", html)
        self.assertNotIn(OMITTED_MARKER, html)

    def test_cli_uses_optional_07_glossary_and_preserves_final_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _base_plan()
            plan_path = os.path.join(run_dir, "06_plan.final.json")
            _write_json(plan_path, plan)
            _write_json(os.path.join(run_dir, "07_glossary.json"), _glossary_doc())
            _write_completed_run(run_dir)
            with open(plan_path, "rb") as handle:
                before = handle.read()
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(plan_path, "rb") as handle:
                after = handle.read()
            self.assertEqual(after, before)
            with open(os.path.join(run_dir, "report.html"), encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn("Medical terms explained", html)

    def test_cli_allows_completed_v1_and_rejects_partial_v1(self):
        script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "06_plan.final.json"), _base_plan("1.0"))
            _write_completed_run(run_dir)
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as run_dir:
            draft_path = os.path.join(run_dir, "03_plan.draft.json")
            _write_json(draft_path, _base_plan("1.0"))
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir, "--plan", draft_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed schema-v1 final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.html")))


if __name__ == "__main__":
    unittest.main()
