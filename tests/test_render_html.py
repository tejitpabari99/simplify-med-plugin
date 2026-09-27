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
import runlog  # noqa: E402
from test_plan_view import NOTICE_MARKER, _fixture_plan, _glossary_doc, _minimal_plan  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _write_completed_run(run_dir, run_id="fixture-er-visit"):
    _write_json(
        os.path.join(run_dir, "run.json"),
        {
            "schema_version": "3.0",
            "plugin_version": "0.1.0",
            "run_id": run_id,
            "created_at": "2026-09-26T00:00:00+00:00",
            "level": "standard",
            "inputs": [],
            "stages": {"finalize": {"status": "ok", "attempts": 1, "checks": {}, "artifacts": []}},
            "notices": [],
        },
    )


class TestRenderHtml(unittest.TestCase):
    def test_er_sections_render_in_order(self):
        html = render_html.render(_fixture_plan())
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Your ER visit, simplified</title>", html)
        order = [
            "<h1>Your ER visit, simplified</h1>",
            '<p class="lead">You went to the ER because',
            "<h2>What did they find?</h2>",
            "<p>The important tests were reassuring:</p>",
            "<li><strong>Brain MRI:</strong> Normal. No stroke was seen.</li>",
            "<li><strong>Heart tracing:</strong> It showed a right bundle branch block",
            "<strong>The ER diagnosed you with:</strong>",
            "<li>Acute headache</li>",
            "<li>Tingling in your left arm/hand</li>",
            "<p>They did not find an emergency cause",
            "<h2>What should you do now?</h2>",
            "<li>Schedule a primary-care appointment",
            "<li>You were not prescribed any new medicines.</li>",
            "<h2>When should you go back to the ER?</h2>",
            "<li>Return to the ER if you develop any new or worsening symptoms.</li>",
            "<footer>",
        ]
        positions = [html.index(fragment) for fragment in order]
        self.assertEqual(positions, sorted(positions))

    def test_html_never_embeds_internal_plan_data_or_legacy_rows(self):
        html = render_html.render(_fixture_plan())
        for hidden in (
            NOTICE_MARKER, "Reading level:", "unit_ids", "coverage", "fixture-er-visit",
            "Already done", "type-label", 'type="checkbox"', "localStorage", "Medical terms explained",
            'class="term"',
        ):
            self.assertNotIn(hidden, html)

    def test_text_is_escaped(self):
        plan = _minimal_plan()
        plan["why_you_went"]["text"] = 'You had <script>alert("x")</script> & pain.'
        plan["findings"] = [{"name": "A<b>", "result": "R&D \"ok\"", "unit_ids": [2]}]
        html = render_html.render(plan)
        self.assertNotIn("<script>alert", html)
        self.assertIn("You had &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; pain.", html)
        self.assertIn("<li><strong>A&lt;b&gt;:</strong> R&amp;D &quot;ok&quot;</li>", html)

    def test_other_visit_type_uses_generic_headings(self):
        plan = _minimal_plan("procedure")
        plan["diagnoses"] = [{"name": "Colon polyp", "unit_ids": [2]}]
        plan["return_precautions"] = [{"text": "Call if you see heavy bleeding.", "unit_ids": [3]}]
        html = render_html.render(plan)
        self.assertIn("<h1>Your procedure, simplified</h1>", html)
        self.assertIn("<strong>Diagnosed with:</strong>", html)
        self.assertIn("<h2>When to get help right away</h2>", html)
        self.assertNotIn("go back to the ER", html)

    def test_optional_glossary_enriches_html_without_mutating_inputs(self):
        plan = _fixture_plan()
        glossary = _glossary_doc()
        before_plan = copy.deepcopy(plan)
        before_glossary = copy.deepcopy(glossary)
        html = render_html.render(plan, glossary=glossary)
        self.assertIn("<h2>Medical terms explained</h2>", html)
        self.assertEqual(html.count('class="term"'), 1)
        self.assertIn(
            '<span class="term" tabindex="0" data-def="A delay in the electrical signal along one side of the heart.">'
            "bundle branch block</span>",
            html,
        )
        self.assertEqual(plan, before_plan)
        self.assertEqual(glossary, before_glossary)

    def test_cli_uses_optional_07_glossary_and_preserves_final_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _fixture_plan()
            plan_path = os.path.join(run_dir, "05_plan.final.json")
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
            self.assertIn("render_html: ok | path=", result.stdout)
            with open(plan_path, "rb") as handle:
                self.assertEqual(handle.read(), before)
            with open(os.path.join(run_dir, "report.html"), encoding="utf-8") as handle:
                self.assertIn("Medical terms explained", handle.read())
            stage = runlog.read(run_dir)["stages"]["render_html"]
            self.assertEqual(stage["status"], "ok")
            self.assertEqual(stage["checks"], {"glossary_terms": 1})

    def test_cli_rejects_foreign_glossary(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "05_plan.final.json"), _fixture_plan())
            _write_json(os.path.join(run_dir, "07_glossary.json"), _glossary_doc(run_id="other-run"))
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run([sys.executable, script, "--run-dir", run_dir], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("does not belong", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.html")))

    def test_cli_rejects_non_final_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            draft_path = os.path.join(run_dir, "04_plan.settled.json")
            _write_json(draft_path, _fixture_plan())
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir, "--plan", draft_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.html")))


if __name__ == "__main__":
    unittest.main()
