"""Kill test 1, fix #6: the harder two-document fixture set for kill test
2 -- a multi-page discharge summary plus a standalone lab report for the
same synthetic patient. This module only asserts the structural claims
the fixtures are supposed to satisfy (parse, chunk count, continuous
cross-file ids); it does not run the LLM stages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

DOCS_DIR = os.path.join(_paths.TESTS_DIR, "fixtures", "documents")
DISCHARGE = os.path.join(DOCS_DIR, "synthetic-discharge-summary.txt")
LAB_REPORT = os.path.join(DOCS_DIR, "synthetic-lab-report.txt")


def _unitize_script() -> str:
    return os.path.join(_paths.SCRIPTS_DIR, "unitize.py")


def _run_unitize(run_dir: str, *inputs: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, _unitize_script(), "--run-dir", run_dir]
    for inp in inputs:
        cmd += ["--input", inp]
    return subprocess.run(cmd, capture_output=True, text=True)


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestFixturesExistAndParse(unittest.TestCase):
    def test_discharge_summary_file_exists_and_is_synthetic(self):
        self.assertTrue(os.path.isfile(DISCHARGE))
        with open(DISCHARGE, "r", encoding="utf-8") as f:
            first_line = f.readline()
        self.assertTrue(first_line.startswith("#"), "first line must be a comment")
        self.assertIn("SYNTHETIC", first_line)

    def test_lab_report_file_exists_and_is_synthetic(self):
        self.assertTrue(os.path.isfile(LAB_REPORT))
        with open(LAB_REPORT, "r", encoding="utf-8") as f:
            first_line = f.readline()
        self.assertTrue(first_line.startswith("#"), "first line must be a comment")
        self.assertIn("SYNTHETIC", first_line)

    def test_discharge_summary_has_at_least_170_non_blank_lines(self):
        with open(DISCHARGE, "r", encoding="utf-8") as f:
            text = f.read()
        non_blank = sum(1 for line in text.split("\n") if line.strip())
        self.assertGreaterEqual(non_blank, 170)

    def test_discharge_summary_has_two_form_feed_page_breaks(self):
        with open(DISCHARGE, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("\f"), 2)

    def test_lab_report_is_a_single_page(self):
        with open(LAB_REPORT, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("\f"), 0)

    def test_both_fixtures_parse_via_unitize(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-discharge")
            result = _run_unitize(run_dir, f"{DISCHARGE}:native")
            self.assertEqual(result.returncode, 0, result.stderr)

            run_dir2 = os.path.join(d, "run-lab")
            result2 = _run_unitize(run_dir2, f"{LAB_REPORT}:native")
            self.assertEqual(result2.returncode, 0, result2.stderr)


class TestDischargeSummaryChunking(unittest.TestCase):
    """The discharge summary alone must yield exactly 2 chunks at the
    default chunk size (150)."""

    def test_discharge_summary_yields_exactly_two_chunks(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            result = _run_unitize(run_dir, f"{DISCHARGE}:native")
            self.assertEqual(result.returncode, 0, result.stderr)

            units_doc = _read_json(os.path.join(run_dir, "01_units.json"))
            self.assertEqual(len(units_doc["chunks"]), 2)


class TestTwoFileRunContinuousIds(unittest.TestCase):
    """Unitizing both fixtures together in one run must produce unit ids
    that are continuous across files (the lab report's first id picks up
    right after the discharge summary's last id, with no gap or reset)."""

    def test_two_file_run_yields_continuous_ids_across_files(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            result = _run_unitize(
                run_dir, f"{DISCHARGE}:native", f"{LAB_REPORT}:native",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            units_doc = _read_json(os.path.join(run_dir, "01_units.json"))
            units = units_doc["units"]
            ids = [u["id"] for u in units]
            self.assertEqual(ids, list(range(1, len(units) + 1)))

            files_in_order = []
            for u in units:
                if not files_in_order or files_in_order[-1] != u["file"]:
                    files_in_order.append(u["file"])
            self.assertEqual(
                files_in_order,
                ["synthetic-discharge-summary.txt", "synthetic-lab-report.txt"],
            )


if __name__ == "__main__":
    unittest.main()
