"""Structural checks for the synthetic schema-v2 document fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

DOCS_DIR = _paths.FIXTURE_DOCUMENTS_DIR
DISCHARGE = os.path.join(DOCS_DIR, "synthetic-discharge-summary.txt")
LAB_REPORT = os.path.join(DOCS_DIR, "synthetic-lab-report.txt")
VISIT_NOTE = os.path.join(DOCS_DIR, "synthetic-visit-note.txt")


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
    def test_every_document_is_explicitly_synthetic(self):
        for path in (DISCHARGE, LAB_REPORT, VISIT_NOTE):
            with self.subTest(path=path):
                self.assertTrue(os.path.isfile(path))
                with open(path, "r", encoding="utf-8") as f:
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

            for current in (run_dir, run_dir2):
                units = _read_json(os.path.join(current, "01_units.json"))
                run_log = _read_json(os.path.join(current, "run.json"))
                self.assertEqual(units["schema_version"], "2.0")
                self.assertEqual(run_log["schema_version"], "2.0")
                self.assertEqual(units["run_id"], run_log["run_id"])
                self.assertEqual(units["plugin_version"], run_log["plugin_version"])
                self.assertFalse(os.path.exists(os.path.join(current, "00_input", "manifest.json")))
                self.assertEqual(run_log["stages"]["unitize"]["status"], "ok")


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
            self.assertEqual(
                [chunk["k"] for chunk in units_doc["chunks"]],
                [1, 2],
            )
            for chunk in units_doc["chunks"]:
                self.assertTrue(os.path.isfile(os.path.join(run_dir, f"01_units.{chunk['k']}.txt")))


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
            run_log = _read_json(os.path.join(run_dir, "run.json"))
            self.assertEqual(
                [item["file"] for item in run_log["inputs"]],
                files_in_order,
            )

    def test_fixture_readme_forbids_model_output_and_fail_open_routes(self):
        with open(os.path.join(_paths.FIXTURES_DIR, "README.md"), encoding="utf-8") as handle:
            text = handle.read().lower()
        self.assertIn("schema-v2", text)
        self.assertIn("no fixture can preserve a direct-summary", text)
        self.assertIn("fail-open publication route", text)


if __name__ == "__main__":
    unittest.main()
