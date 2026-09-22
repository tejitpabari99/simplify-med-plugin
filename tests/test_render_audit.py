import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import finalize  # noqa: E402
import render_audit  # noqa: E402


class TestRenderAudit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = os.path.join(self._tmp.name, "run-audit")
        os.makedirs(self.run_dir)
        self.run_id = _runfix.make_run_dir(self.run_dir)
        rc = finalize._run(self.run_dir)
        self.assertEqual(rc, 0)

    def tearDown(self):
        self._tmp.cleanup()

    def test_module_render_writes_expected_sections(self):
        rc = render_audit.main(["--run-dir", self.run_dir])
        self.assertEqual(rc, 0)
        out_path = os.path.join(self.run_dir, "report.audit.md")
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, encoding="utf-8") as f:
            text = f.read()

        self.assertIn(f"# Audit view — {self.run_id}", text)
        self.assertIn("## Stages", text)
        self.assertIn("| unitize | ok", text)
        self.assertIn("## Low priority (not shown to the patient)", text)
        self.assertIn(_runfix.LOW_PRIORITY_MARKER, text)
        self.assertIn("## Facts not present in the plan", text)
        self.assertIn("## Facts dropped at grounding", text)

    def test_fact_line_has_note_txt_location(self):
        render_audit.main(["--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.audit.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("note.txt:1:", text)

    def test_missing_fact_section_lists_fact_8(self):
        render_audit.main(["--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.audit.md"), encoding="utf-8") as f:
            text = f.read()
        missing_section = text.split("## Facts not present in the plan")[1]
        missing_section = missing_section.split("## Facts dropped at grounding")[0]
        self.assertIn("fact 8", missing_section)

    def test_custom_out_path(self):
        out_path = os.path.join(self.run_dir, "custom.audit.md")
        rc = render_audit.main(["--run-dir", self.run_dir, "--out", out_path])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(out_path))

    def test_cli_subprocess(self):
        script = os.path.join(_paths.SCRIPTS_DIR, "render_audit.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "report.audit.md")))


if __name__ == "__main__":
    unittest.main()
