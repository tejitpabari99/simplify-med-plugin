"""Status output coverage for the schema-v2 deterministic pipeline."""

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

import runlog  # noqa: E402

STATUS_LINE_RE = re.compile(r"^[a-z_]+: (ok|degraded|failed|skipped) \|")


def _run(name: str, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, os.path.join(_paths.SCRIPTS_DIR, name), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
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
        unitize = _run(
            "unitize.py", "--runs-dir", os.path.join(root, "runs"),
            "--input", f"{source}:native",
        )
        cls.lines = {"unitize": unitize.stdout.strip().splitlines()}
        cls.run_dir = cls.lines["unitize"][-1]
        cls.run_id = runlog.read(cls.run_dir)["run_id"]

        units_document = _runfix.read_json(os.path.join(cls.run_dir, "01_units.json"))
        _runfix.write_json(
            os.path.join(cls.run_dir, "02_facts.1.raw.json"),
            _runfix.facts_raw_for_units(units_document["units"]),
        )
        for label, script, args in (
            ("anchor_check", "anchor_check.py", ("--run-dir", cls.run_dir, "--chunk", "1")),
            ("merge_facts", "merge_facts.py", ("--run-dir", cls.run_dir)),
        ):
            cls.lines[label] = _run(script, *args).stdout.strip().splitlines()

        facts = _runfix.read_json(os.path.join(cls.run_dir, "02_facts.json"))["facts"]
        _runfix.write_json(os.path.join(cls.run_dir, "03_plan.raw.json"), _runfix.plan_raw(facts))
        runlog.record(
            cls.run_dir, "assemble", "ok", attempts=1,
            artifacts=["03_plan.raw.json"], run_id=cls.run_id,
        )
        cls.lines["plan_check"] = _run(
            "cite_check.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        runlog.record(
            cls.run_dir, "plan_check", "ok", attempts=1,
            artifacts=["03_plan.draft.json"], run_id=cls.run_id,
        )
        cls.lines["numeric_parity"] = _run(
            "numeric_parity.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        runlog.record(
            cls.run_dir, "numeric_parity", "ok", attempts=1,
            artifacts=["03_flags.json"], run_id=cls.run_id,
        )

        draft = _runfix.read_json(os.path.join(cls.run_dir, "03_plan.draft.json"))
        flags = _runfix.read_json(os.path.join(cls.run_dir, "03_flags.json"))
        _runfix.write_json(
            os.path.join(cls.run_dir, "04_review.raw.json"),
            _runfix.review_raw(draft, facts, flags),
        )
        runlog.record(
            cls.run_dir, "review", "ok", attempts=1, started=True, finished=False,
            artifacts=["04_review.raw.json"], run_id=cls.run_id,
        )
        cls.lines["settle_review"] = _run(
            "settle_review.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        cls.lines["finalize"] = _run(
            "finalize.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        cls.lines["glossary"] = _run(
            "glossary_check.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        cls.lines["render_md"] = _run(
            "render_md.py", "--run-dir", cls.run_dir,
            "--out", os.path.join(cls.run_dir, "report.rerendered.md"),
        ).stdout.strip().splitlines()
        cls.lines["render_html"] = _run(
            "render_html.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()
        cls.lines["render_audit"] = _run(
            "render_audit.py", "--run-dir", cls.run_dir,
        ).stdout.strip().splitlines()

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
        for label in (
            "anchor_check", "merge_facts", "plan_check", "numeric_parity",
            "settle_review", "finalize", "glossary", "render_html", "render_audit",
        ):
            with self.subTest(label=label):
                self._assert_status(label)

    def test_markdown_renderer_reports_written_path(self):
        self.assertRegex(self.lines["render_md"][-1], r"^OK wrote .+report\.rerendered\.md$")

    def test_deleted_v1_status_sources_are_absent(self):
        for name in ("sanitize_review.py", "diff_guard.py"):
            self.assertFalse(os.path.exists(os.path.join(_paths.SCRIPTS_DIR, name)))


if __name__ == "__main__":
    unittest.main()
