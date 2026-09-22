"""Kill test 1, fix #2: every deterministic script must print a uniform
one-line status as its last stdout line on exit 0 (second-to-last for
unitize, whose true last line stays `<run>`).

Drives a reduced version of the full pipeline chain described in
SKILL.md -- unitize, ground (anchor_check/merge_facts), glossary
(glossary_check), assemble (cite_check/numeric_parity), review
(sanitize_review, both sides), correct (diff_guard, skip path),
assemble-missing (cite_check --additions, skip path), finalize,
render_audit -- against the real synthetic fixture document, mirroring
tests/test_pipeline_e2e.py's setup, and asserts the status-line shape on
each script's stdout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

FIXTURE = os.path.join(_paths.TESTS_DIR, "fixtures", "documents", "synthetic-visit-note.txt")

STATUS_LINE_RE = re.compile(r"^[a-z_]+: (ok|degraded|failed|skipped) \|")


def _script(name: str) -> str:
    return os.path.join(_paths.SCRIPTS_DIR, name)


def _run_ok(name: str, *args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, _script(name), *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{name} {' '.join(args)} exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestStatusLines(unittest.TestCase):
    """One representative exit-0 invocation per script named in kill test
    1's fix #2; each is asserted to end (unitize: second-to-last) with a
    line matching `^[a-z_]+: (ok|degraded|failed|skipped) \\|`."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        runs_dir = os.path.join(cls._tmp.name, "simplify-runs")
        cls.lines: dict[str, list[str]] = {}

        # --- Stage 0: unitize -------------------------------------------
        result = _run_ok("unitize.py", "--runs-dir", runs_dir, "--input", f"{FIXTURE}:native")
        cls.lines["unitize"] = result.stdout.strip().splitlines()
        cls.run_dir = cls.lines["unitize"][-1]
        assert os.path.isdir(cls.run_dir)

        # --- Stage 1: ground (anchor_check + merge_facts) + glossary ----
        # Real, verbatim substrings of the fixture's chunk-1 unit texts
        # (same anchors test_pipeline_e2e.py uses, known-good).
        facts_raw = {"facts": [
            {"category": "reason_for_visit", "unit_id": 8,
             "quote": "chest tightness and shortness of breath (SOB) on exertion",
             "text": "Patient has intermittent chest tightness and shortness of "
                      "breath on exertion, present for about three weeks."},
            {"category": "medications", "unit_id": 21,
             "quote": "metoprolol 25mg BID for rate control and angina management",
             "text": "Start metoprolol 25 mg twice daily for rate control and "
                      "angina management."},
        ]}
        _write_json(os.path.join(cls.run_dir, "02_facts.1.raw.json"), facts_raw)

        glossary_raw = {"terms": [
            {"term": "Angina", "matched_term": "angina",
             "definition": "Chest pain caused by reduced blood flow to the heart.",
             "source": "llm_proposed"},
        ]}
        _write_json(os.path.join(cls.run_dir, "02_glossary.raw.json"), glossary_raw)

        result = _run_ok("anchor_check.py", "--run-dir", cls.run_dir, "--chunk", "1")
        cls.lines["anchor_check"] = result.stdout.strip().splitlines()

        result = _run_ok("glossary_check.py", "--run-dir", cls.run_dir)
        cls.lines["glossary_check"] = result.stdout.strip().splitlines()

        result = _run_ok("merge_facts.py", "--run-dir", cls.run_dir)
        cls.lines["merge_facts"] = result.stdout.strip().splitlines()

        facts_doc = _read_json(os.path.join(cls.run_dir, "02_facts.json"))
        fid_reason = facts_doc["facts"][0]["id"]
        fid_med = facts_doc["facts"][1]["id"]

        # --- Stage 2: assemble (cite_check) + numeric_parity ------------
        plan_raw = {
            "summary": "You have chest tightness and need medication adjustment.",
            "summary_fact_ids": [fid_reason],
            "reason_for_visit": [
                {"reason": "Chest tightness",
                 "description": "You've had chest tightness with activity.",
                 "source_fact_ids": [fid_reason]},
            ],
            "diagnosis": {"changed_since_last_visit": "",
                          "changed_since_last_visit_fact_ids": [], "details": []},
            "medications": [
                {"title": "Metoprolol", "plain_name": "metoprolol",
                 "why": "To manage chest pain.",
                 "dosage": "25 mg", "frequency": "twice a day", "timing": "",
                 "duration": "", "instructions": "", "side_effects_to_watch": "",
                 "change": "", "status": "to_do", "source_fact_ids": [fid_med]},
            ],
            "tests": [], "procedures": [], "other": [], "follow_up": [],
            "warning_signs": [], "questions": [], "low_priority": [],
        }
        _write_json(os.path.join(cls.run_dir, "03_plan.raw.json"), plan_raw)

        result = _run_ok("cite_check.py", "--run-dir", cls.run_dir)
        cls.lines["cite_check_assemble"] = result.stdout.strip().splitlines()

        result = _run_ok("numeric_parity.py", "--run-dir", cls.run_dir)
        cls.lines["numeric_parity"] = result.stdout.strip().splitlines()

        # --- Stage 3: review (sanitize_review, both sides) --------------
        _write_json(os.path.join(cls.run_dir, "04_review.raw.json"),
                    {"verdict": "pass", "corrections": []})
        _write_json(os.path.join(cls.run_dir, "04_coverage.raw.json"),
                    {"coverage": [{"fact_id": fid_reason, "present": True},
                                   {"fact_id": fid_med, "present": True}]})

        result = _run_ok("sanitize_review.py", "--run-dir", cls.run_dir, "--only", "review")
        cls.lines["sanitize_review_review"] = result.stdout.strip().splitlines()

        result = _run_ok("sanitize_review.py", "--run-dir", cls.run_dir, "--only", "coverage")
        cls.lines["sanitize_review_coverage"] = result.stdout.strip().splitlines()

        # --- Stage 4: correct (diff_guard, skip path -- corrections=0) --
        result = _run_ok("diff_guard.py", "--run-dir", cls.run_dir)
        cls.lines["diff_guard_skip"] = result.stdout.strip().splitlines()

        # --- Stage 4: assemble-missing (cite_check --additions, skip path) --
        result = _run_ok("cite_check.py", "--run-dir", cls.run_dir, "--additions")
        cls.lines["cite_check_additions"] = result.stdout.strip().splitlines()

        # --- Stage 5: finalize + audit -----------------------------------
        result = _run_ok("finalize.py", "--run-dir", cls.run_dir)
        cls.lines["finalize"] = result.stdout.strip().splitlines()

        result = _run_ok("render_audit.py", "--run-dir", cls.run_dir)
        cls.lines["render_audit"] = result.stdout.strip().splitlines()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _assert_status_line(self, label: str, index: int = -1) -> None:
        lines = self.lines[label]
        self.assertTrue(lines, f"{label} produced no stdout")
        self.assertRegex(lines[index], STATUS_LINE_RE, f"{label} lines: {lines}")

    # unitize is the documented exception: status line is second-to-last,
    # `<run>` stays last.
    def test_unitize_status_line_is_second_to_last(self):
        self._assert_status_line("unitize", index=-2)
        self.assertTrue(os.path.isdir(self.lines["unitize"][-1]))

    def test_anchor_check_status_line(self):
        self._assert_status_line("anchor_check")

    def test_glossary_check_status_line(self):
        self._assert_status_line("glossary_check")

    def test_merge_facts_status_line(self):
        self._assert_status_line("merge_facts")

    def test_cite_check_assemble_status_line(self):
        self._assert_status_line("cite_check_assemble")

    def test_numeric_parity_status_line(self):
        self._assert_status_line("numeric_parity")

    def test_sanitize_review_review_status_line(self):
        self._assert_status_line("sanitize_review_review")

    def test_sanitize_review_coverage_status_line(self):
        self._assert_status_line("sanitize_review_coverage")

    def test_diff_guard_skip_status_line(self):
        self._assert_status_line("diff_guard_skip")

    def test_cite_check_additions_status_line(self):
        self._assert_status_line("cite_check_additions")

    def test_finalize_status_line(self):
        self._assert_status_line("finalize")

    def test_render_audit_status_line(self):
        self._assert_status_line("render_audit")


if __name__ == "__main__":
    unittest.main()
