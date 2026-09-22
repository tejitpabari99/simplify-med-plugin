import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_md  # noqa: E402
from test_plan_view import _base_plan  # noqa: E402


class TestRenderMd(unittest.TestCase):
    def setUp(self):
        self.plan = _base_plan()
        self.text = render_md.render(self.plan)

    def test_title_heading(self):
        self.assertTrue(self.text.startswith("# Your visit, explained"))

    def test_notice_blockquote(self):
        self.assertIn("> A notice.", self.text)

    def test_score_line_italic(self):
        self.assertIn("_Reading level: grade 9.0 before, grade 6.0 after._", self.text)

    def test_section_headings(self):
        for heading in (
            "## What you need to know",
            "## Why you were seen",
            "## What the doctor found",
            "## Your next steps",
            "## What to watch for",
            "## Questions to ask your doctor",
            "## Medical terms explained",
        ):
            self.assertIn(heading, self.text)

    def test_todo_done_headings_and_checkboxes(self):
        self.assertIn("### To do", self.text)
        self.assertIn("### Already done", self.text)
        self.assertIn("- [ ] **Med A**", self.text)
        self.assertIn("- [x] **Med B (medb)**", self.text)

    def test_no_html_tags(self):
        self.assertNotIn("<", self.text)
        self.assertNotIn(">", self.text.replace("> A notice.", ""))

    def test_low_priority_absent(self):
        self.assertNotIn("Billing code noted.", self.text)

    def test_fact_ids_absent(self):
        self.assertNotIn("source_fact_ids", self.text)

    def test_glossary_list_format(self):
        self.assertIn("- **cbc** — A blood test.", self.text)
        self.assertIn("- **hypertension** — High blood pressure.", self.text)

    def test_questions_numbered(self):
        self.assertIn("1. Will I need surgery?", self.text)

    def test_cli_writes_file(self):
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(self.plan, f)
            out_path = os.path.join(d, "out.md")
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", d, "--plan", plan_path, "--out", out_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.startswith("# Your visit, explained"))


if __name__ == "__main__":
    unittest.main()
