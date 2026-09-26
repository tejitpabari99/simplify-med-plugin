"""Status output coverage for the deterministic pipeline scripts."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

STATUS_LINE_RE = re.compile(r"^[a-z_]+: (ok|degraded|failed|skipped) \|")


def _run(name: str, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, os.path.join(_paths.SCRIPTS_DIR, name), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"{name} {' '.join(args)} exited {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


class TestStatusLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = cls.temporary.name
        source = os.path.join(root, "note.txt")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(_runfix.NOTE_TEXT)
        unitize = _run("unitize.py", "--runs-dir", os.path.join(root, "runs"), "--input", f"{source}:native")
        cls.lines = {"unitize": unitize.stdout.strip().splitlines()}
        cls.run_dir = cls.lines["unitize"][-1]

        _runfix.write_draft(cls.run_dir, _runfix.draft_raw())
        cls.lines["check"] = _run("check_draft.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()
        draft, check = _runfix.checked(cls.run_dir)
        _runfix.write_verify(cls.run_dir, _runfix.verify_raw_for(draft, check))
        cls.lines["settle"] = _run("settle.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()
        cls.lines["finalize"] = _run("finalize.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()
        cls.lines["glossary"] = _run("glossary_check.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()
        cls.lines["render_md"] = _run(
            "render_md.py", "--run-dir", cls.run_dir,
            "--out", os.path.join(cls.run_dir, "report.rerendered.md"),
        ).stdout.strip().splitlines()
        cls.lines["render_html"] = _run("render_html.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()
        cls.lines["render_audit"] = _run("render_audit.py", "--run-dir", cls.run_dir).stdout.strip().splitlines()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _assert_status(self, label: str, index: int = -1) -> None:
        self.assertTrue(self.lines[label], label)
        self.assertRegex(self.lines[label][index], STATUS_LINE_RE, self.lines[label])

    def test_unitize_status_precedes_run_directory(self):
        self._assert_status("unitize", -2)
        self.assertTrue(os.path.isdir(self.lines["unitize"][-1]))

    def test_current_stage_status_lines(self):
        for label in ("check", "settle", "finalize", "glossary", "render_html", "render_audit"):
            with self.subTest(label=label):
                self._assert_status(label)

    def test_markdown_renderer_reports_written_path(self):
        self.assertRegex(self.lines["render_md"][-1], r"^OK wrote .+report\.rerendered\.md$")

    def test_failure_status_lines(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run")
            _runfix.make_source(run_dir)
            bad = _runfix.draft_raw()
            bad["findings"][0]["unit_ids"] = [99]
            _runfix.write_draft(run_dir, bad)
            result = _run("check_draft.py", "--run-dir", run_dir, expect=1)
            self.assertRegex(result.stdout.strip().splitlines()[-1], STATUS_LINE_RE)
            self.assertIn("findings[0] cites unknown unit 99", result.stderr)

    def test_repair_request_line(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run")
            _runfix.make_source(run_dir)
            _runfix.write_draft(run_dir, _runfix.draft_raw())
            _run("check_draft.py", "--run-dir", run_dir)
            draft, check = _runfix.checked(run_dir)
            _runfix.write_verify(run_dir, _runfix.verify_raw_for(draft, check, protected_result="missing"))
            result = _run("settle.py", "--run-dir", run_dir, expect=3)
            self.assertEqual(result.stdout.strip().splitlines()[-1], "settle: repair requested | round=1 missing=1")

    def test_retired_scripts_are_absent(self):
        for name in (
            "sanitize_review.py", "diff_guard.py", "anchor_check.py", "merge_facts.py",
            "cite_check.py", "numeric_parity.py", "settle_review.py",
        ):
            self.assertFalse(os.path.exists(os.path.join(_paths.SCRIPTS_DIR, name)), name)


if __name__ == "__main__":
    unittest.main()
