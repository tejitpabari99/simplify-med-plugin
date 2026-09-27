"""End-to-end run on the synthetic ER fixture with hand-authored model outputs.

unitize -> WRITE (hand-authored) -> check_draft -> VERIFY (hand-authored)
-> settle -> finalize, plus the repair round and a terminal failure path.
The hand-authored draft follows the PRD section 3 target report.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import plan_paths  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402

ER_FIXTURE = os.path.join(_paths.FIXTURE_DOCUMENTS_DIR, "synthetic-er-visit.txt")
NOISE = (
    "Iopamidol",
    "Sodium",
    "155/99",
    "ordering provider",
    "No current outpatient medications",
)
_WORD_RE = re.compile(r"[A-Za-z0-9]")


def _script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, os.path.join(_paths.SCRIPTS_DIR, name), *args],
        capture_output=True, text=True,
    )


class ERRun:
    """One run directory for the ER fixture, with unit lookup by source text."""

    def __init__(self, root: str):
        result = _script("unitize.py", "--runs-dir", root, "--input", f"{ER_FIXTURE}:native")
        if result.returncode != 0:
            raise AssertionError(f"unitize failed:\n{result.stdout}{result.stderr}")
        self.run_dir = result.stdout.strip().splitlines()[-1]
        with open(os.path.join(self.run_dir, "01_source.txt"), encoding="utf-8") as handle:
            self.source = {
                int(match.group(1)): match.group(2)
                for match in (re.match(r"^\[(\d+)\] (.*)$", line.rstrip("\n")) for line in handle)
                if match
            }
        self.model_calls: list[str] = []

    def uid(self, prefix: str) -> int:
        """The id of the one source unit whose text starts with `prefix`."""
        matches = [unit_id for unit_id, text in self.source.items() if text.startswith(prefix)]
        if len(matches) != 1:
            raise AssertionError(f"expected one unit starting with {prefix!r}, found {matches}")
        return matches[0]

    def path(self, name: str) -> str:
        return os.path.join(self.run_dir, name)

    def write(self, draft: dict, round_no: int = 1) -> subprocess.CompletedProcess:
        self.model_calls.append(f"write-r{round_no}")
        _runfix.write_draft(self.run_dir, draft, round_no)
        return _script("check_draft.py", "--run-dir", self.run_dir, "--round", str(round_no))

    def verify(self, build, round_no: int = 1) -> subprocess.CompletedProcess:
        """`build(draft, check) -> verify_raw`, written as the VERIFY output."""
        self.model_calls.append(f"verify-r{round_no}")
        draft, check = _runfix.checked(self.run_dir, round_no)
        _runfix.write_verify(self.run_dir, build(draft, check), round_no)
        return _script("settle.py", "--run-dir", self.run_dir, "--round", str(round_no))

    def finalize(self) -> subprocess.CompletedProcess:
        return _script("finalize.py", "--run-dir", self.run_dir)


def target_draft(run: ERRun) -> dict:
    """The PRD section 3 target report, citing the fixture's units."""
    u = run.uid
    return {
        "visit_type": "er_visit",
        "why_you_went": {
            "text": "You went to the ER because you had a headache for several days, neck pain, "
                    "tingling in your left hand, and an abnormal heart tracing at urgent care.",
            "unit_ids": [u("Patient was sent from urgent care"), u("Reports headache and neck pain"),
                         u("Headaches have been waxing")],
        },
        "findings_lead": {
            "text": "The important tests were reassuring:",
            "unit_ids": [u("No emergent cause of symptoms"), u("Labs unremarkable")],
        },
        "findings": [
            {"name": "Brain MRI", "result": "Normal. No stroke was seen.",
             "unit_ids": [u("IMPRESSION: Normal noncontrast brain MRI")]},
            {"name": "CT and CT angiogram of your head and neck",
             "result": "Normal. No blocked blood vessels, aneurysm, or artery tear was found.",
             "unit_ids": [u("IMPRESSION: Normal CT angiogram")]},
            {"name": "Neurologic exam",
             "result": "Normal except for slightly different sensation in your left palm.",
             "unit_ids": [u("Neuro: Slightly altered")]},
            {"name": "Blood tests", "result": "The ER doctor described them as unremarkable.",
             "unit_ids": [u("Labs unremarkable")]},
            {"name": "Heart tracing",
             "result": "It showed a right bundle branch block and first-degree AV block, but the ER "
                       "doctor did not think it showed a heart attack or other acute loss of blood "
                       "flow to the heart.",
             "unit_ids": [u("ECG reviewed")]},
        ],
        "diagnoses": [
            {"name": "Acute headache", "unit_ids": [u("Clinical Impression")]},
            {"name": "Left upper extremity paresthesias", "plain_name": "Tingling in your left arm/hand",
             "unit_ids": [u("Clinical Impression")]},
        ],
        "disposition": {
            "text": "They did not find an emergency cause for your symptoms, and you were discharged "
                    "in stable condition.",
            "unit_ids": [u("No emergent cause of symptoms"), u("Disposition:")],
        },
        "next_steps": [
            {"text": "Schedule a primary-care appointment to follow up on the headache, hand "
                     "tingling, and abnormal heart tracing.",
             "unit_ids": [u("Follow-up:")]},
        ],
        "medicines": {
            "items": [],
            "none_statement": {"text": "You were not prescribed any new medicines.",
                               "unit_ids": [u("No new medications prescribed")]},
        },
        "return_precautions": [
            {"text": "Return to the ER if you develop any new or worsening symptoms.",
             "unit_ids": [u("Return to the emergency department")]},
        ],
        "questions": [],
        "coverage": {
            "medication_changes": {"status": "shown", "unit_ids": [u("No new medications prescribed")]},
            "follow_up": {"status": "shown", "unit_ids": [u("Follow-up:")]},
            "return_precautions": {"status": "shown", "unit_ids": [u("Return to the emergency department")]},
            "diagnoses": {"status": "shown", "unit_ids": [u("Clinical Impression")]},
            "disposition": {"status": "shown", "unit_ids": [u("Disposition:")]},
            "abnormal_or_pending_results": {
                "status": "shown", "unit_ids": [u("Patient was sent from urgent care"), u("ECG reviewed")],
            },
        },
    }


def resolve_protected(run: ERRun, check: dict, *, missing: tuple[int, ...] = ()) -> list[dict]:
    """The verifier's decision for each uncited protected candidate."""
    u = run.uid
    covered = {u("Chief Complaint"), u("Sodium 142")}
    out = []
    for entry in check["uncited_protected"]:
        unit_id = entry["unit_id"]
        if unit_id in missing:
            out.append({"unit_id": unit_id, "result": "missing", "category": entry["categories"][0]})
        elif unit_id in covered:
            out.append({"unit_id": unit_id, "result": "covered"})
        else:
            out.append({"unit_id": unit_id, "result": "not_needed", "reason": "false_positive"})
    return out


def clean_verify(run: ERRun, *, missing: tuple[int, ...] = ()):
    def build(draft: dict, check: dict) -> dict:
        return {
            "claims": [{"path": path, "result": "supported"} for path, _item in plan_paths.visible_items(draft)],
            "operations": [],
            "numeric_resolutions": [
                {"flag_id": flag["flag_id"], "resolution": "equivalent"} for flag in check["numeric_flags"]
            ],
            "protected_units": resolve_protected(run, check, missing=missing),
        }
    return build


def report_words(text: str) -> int:
    return sum(1 for token in text.split() if _WORD_RE.search(token))


class TestERVisitCleanPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.er = ERRun(cls.temporary.name)
        cls.check_result = cls.er.write(target_draft(cls.er))
        cls.settle_result = cls.er.verify(clean_verify(cls.er))
        cls.finalize_result = cls.er.finalize()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def report(self) -> str:
        with open(self.er.path("report.md"), encoding="utf-8") as handle:
            return handle.read()

    def test_each_script_succeeds(self):
        for name, result in (
            ("check_draft", self.check_result), ("settle", self.settle_result), ("finalize", self.finalize_result),
        ):
            with self.subTest(name=name):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clean_path_uses_two_model_calls_and_the_expected_artifacts(self):
        self.assertEqual(self.er.model_calls, ["write-r1", "verify-r1"])
        expected = {
            "run.json", "00_input", "01_units.json", "01_source.txt", "01_protected.json",
            "02_draft.raw.json", "02_draft.json", "02_check.json", "03_verify.raw.json",
            "03_verify.json", "04_plan.settled.json", "05_plan.final.json", "report.md",
        }
        self.assertEqual(set(os.listdir(self.er.run_dir)), expected)

    def test_check_found_nothing_to_flag_but_the_uncited_candidates(self):
        _draft, check = _runfix.checked(self.er.run_dir)
        self.assertEqual(check["numeric_flags"], [])
        self.assertFalse(check["over_budget"])
        self.assertLessEqual(check["word_count"], 300)
        uncited = {entry["unit_id"] for entry in check["uncited_protected"]}
        self.assertIn(self.er.uid("Sodium 142"), uncited)

    def test_report_is_short_and_has_the_target_sections(self):
        report = self.report()
        self.assertLessEqual(report_words(report), 300, report)
        for text in (
            "# Your ER visit, simplified",
            "What did they find?",
            "What should you do now?",
            "When should you go back to the ER?",
            "The ER diagnosed you with:",
            "**Brain MRI:** Normal. No stroke was seen.",
            "You were not prescribed any new medicines.",
            "Return to the ER if you develop any new or worsening symptoms.",
        ):
            with self.subTest(text=text):
                self.assertIn(text, report)

    def test_report_excludes_noise(self):
        report = self.report()
        for text in NOISE:
            with self.subTest(text=text):
                self.assertNotIn(text, report)
        for text in ("Already done", "more details", "unit_ids", "coverage"):
            with self.subTest(text=text):
                self.assertNotIn(text, report)

    def test_final_plan_and_run_log(self):
        plan = _runfix.read_json(self.er.path("05_plan.final.json"))
        self.assertEqual(validate.validate(plan, validate.load_schema("plan")), [])
        self.assertLessEqual(plan["word_count"], 300)
        run_log = runlog.read(self.er.run_dir)
        self.assertEqual(validate.validate(run_log, validate.load_schema("run")), [])
        for stage in ("unitize", "write", "check", "verify", "settle", "finalize"):
            with self.subTest(stage=stage):
                self.assertEqual(run_log["stages"][stage]["status"], "ok")
                self.assertEqual(run_log["stages"][stage]["attempts"], 1)


class TestERVisitRepairRound(unittest.TestCase):
    def test_missing_return_precautions_trigger_one_repair_round(self):
        with tempfile.TemporaryDirectory() as root:
            run = ERRun(root)
            first = target_draft(run)
            first["return_precautions"] = []
            first["coverage"]["return_precautions"] = {"status": "none_in_source", "unit_ids": []}
            self.assertEqual(run.write(first).returncode, 0)
            return_unit = run.uid("Return to the emergency department")
            result = run.verify(clean_verify(run, missing=(return_unit,)))
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            repair = _runfix.read_json(run.path("04_repair.json"))
            self.assertEqual(repair["missing"], [{"unit_id": return_unit, "category": "return_precautions"}])
            self.assertFalse(os.path.exists(run.path("report.md")))

            second = copy.deepcopy(repair["settled_draft"])
            for key in ("schema_version", "run_id"):
                del second[key]
            second["return_precautions"] = target_draft(run)["return_precautions"]
            second["coverage"]["return_precautions"] = {"status": "shown", "unit_ids": [return_unit]}
            result = run.write(second, round_no=2)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run.verify(clean_verify(run), round_no=2)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run.finalize()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(run.model_calls, ["write-r1", "verify-r1", "write-r2", "verify-r2"])
            with open(run.path("report.md"), encoding="utf-8") as handle:
                self.assertIn("When should you go back to the ER?", handle.read())


class TestERVisitFailurePath(unittest.TestCase):
    def test_write_fails_twice_and_no_report_is_produced(self):
        with tempfile.TemporaryDirectory() as root:
            run = ERRun(root)
            bad = target_draft(run)
            bad["findings"][0]["unit_ids"] = [run.uid("Technique:") + 1000]
            first = run.write(bad)
            self.assertEqual(first.returncode, 1)
            self.assertIn("retry=allowed", first.stdout)
            second = run.write(bad)
            self.assertEqual(second.returncode, 1)
            self.assertIn("retry=exhausted", second.stdout)
            self.assertEqual(run.finalize().returncode, 1)
            self.assertFalse(os.path.exists(run.path("report.md")))
            self.assertFalse(os.path.exists(run.path("05_plan.final.json")))


if __name__ == "__main__":
    unittest.main()
