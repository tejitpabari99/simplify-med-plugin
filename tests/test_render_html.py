import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_html  # noqa: E402
from test_plan_view import _base_plan  # noqa: E402


def _body_only(html_text: str) -> str:
    """The rendered body, excluding the embedded plan-JSON <script> blob
    (which legitimately carries the full plan, low_priority and all, for
    the audit trail)."""
    start = html_text.index('<script type="application/json"')
    end = html_text.index("</script>", start)
    return html_text[:start] + html_text[end + len("</script>"):]


class TestRenderHtml(unittest.TestCase):
    def setUp(self):
        self.plan = _base_plan()
        self.html = render_html.render(self.plan)

    def test_single_self_contained_file(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Your visit, explained</title>", self.html)

    def test_no_external_assets(self):
        self.assertNotIn('src="http', self.html)
        self.assertNotIn('href="http', self.html)
        self.assertNotIn("src='http", self.html)
        self.assertNotIn("href='http", self.html)

    def test_embedded_json_contains_run_id(self):
        self.assertIn('id="simplify-med-plan"', self.html)
        start = self.html.index('id="simplify-med-plan">') + len('id="simplify-med-plan">')
        end = self.html.index("</script>", start)
        blob = self.html[start:end]
        embedded = json.loads(blob)
        self.assertEqual(embedded["meta"]["run_id"], "run-1")

    def test_data_key_count_matches_next_step_rows(self):
        n_rows = (
            len(self.plan["medications"]) + len(self.plan["tests"])
            + len(self.plan["procedures"]) + len(self.plan["follow_up"])
            + len(self.plan["other"])
        )
        data_keys = re.findall(r'data-key="', self.html)
        self.assertEqual(len(data_keys), n_rows)

    def test_low_priority_marker_absent_from_rendered_body(self):
        body = _body_only(self.html)
        self.assertNotIn("Billing code noted.", body)

    def test_low_priority_present_in_embedded_json_audit_trail(self):
        self.assertIn("Billing code noted.", self.html)

    def test_glossary_details_closed_others_open(self):
        m = re.search(r'<details( open)?><summary>Medical terms explained</summary>', self.html)
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(1))
        m2 = re.search(r'<details( open)?><summary>What you need to know</summary>', self.html)
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group(1), " open")

    def test_term_span_present_for_appearing_term(self):
        self.assertIn('class="term"', self.html)
        self.assertIn('data-def="High blood pressure."', self.html)

    def test_all_text_escaped(self):
        plan = _base_plan()
        plan["summary"] = "Watch for <b>bold</b> & 'quotes' issues."
        html_text = render_html.render(plan)
        self.assertNotIn("<b>bold</b>", html_text)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html_text)
        self.assertIn("&amp;", html_text)

    def test_notice_box_present_once(self):
        self.assertEqual(self.html.count('<div class="notice">'), 1)
        self.assertIn("A notice.", self.html)

    def test_footer_present(self):
        self.assertIn("reading aid, not medical advice", self.html)

    def test_checked_attribute_on_done_row(self):
        self.assertIn('data-key="medications-1" checked', self.html)
        self.assertNotIn('data-key="medications-0" checked', self.html)

    def test_print_style_hides_checkbox_shows_empty_box(self):
        self.assertIn("@media print", self.html)
        self.assertIn("print-empty-box", self.html)
        self.assertIn("☐", self.html)

    def test_beforeprint_handler_present(self):
        self.assertIn("beforeprint", self.html)

    def test_localstorage_try_except_guard(self):
        self.assertIn("try {", self.html)
        self.assertIn("catch (e)", self.html)

    def test_dark_mode_media_query(self):
        self.assertIn("prefers-color-scheme: dark", self.html)

    def test_cli_writes_file(self):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(self.plan, f)
            out_path = os.path.join(d, "out.html")
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", d, "--plan", plan_path, "--out", out_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.startswith("<!DOCTYPE html>"))

    def test_cli_default_run_dir_paths_and_status_line(self):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "06_plan.final.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(self.plan, f)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", d],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            out_path = os.path.join(d, "report.html")
            self.assertTrue(os.path.isfile(out_path))
            self.assertIn(f"render_html: ok | path={out_path}", result.stdout)
            self.assertEqual(result.stdout.strip().splitlines()[-1], f"render_html: ok | path={out_path}")

    def test_cli_exit_1_when_plan_missing(self):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(_paths.SCRIPTS_DIR, "render_html.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", d],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("06_plan.final.json", result.stderr)
            self.assertFalse(os.path.isfile(os.path.join(d, "report.html")))


if __name__ == "__main__":
    unittest.main()
