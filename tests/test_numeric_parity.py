import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import numeric_parity  # noqa: E402
import validate  # noqa: E402


FACTS = [
    {"id": 1, "category": "reason_for_visit", "unit_id": 1,
     "quote": "chest pain for two weeks", "char_start": 0, "char_end": 25,
     "text": "Patient presents with chest pain for two weeks."},
    {"id": 2, "category": "medications", "unit_id": 2,
     "quote": "metoprolol 25mg twice daily", "char_start": 0, "char_end": 28,
     "text": "Start metoprolol 25mg twice daily."},
    {"id": 3, "category": "diagnosis", "unit_id": 3,
     "quote": "hypertension, stage 2", "char_start": 0, "char_end": 22,
     "text": "Diagnosis: hypertension, stage 2."},
    {"id": 4, "category": "follow_up", "unit_id": 4,
     "quote": "follow up in 3 months", "char_start": 0, "char_end": 22,
     "text": "Patient to follow up in 3 months."},
    {"id": 5, "category": "tests", "unit_id": 5,
     "quote": "order CBC and BMP", "char_start": 0, "char_end": 18,
     "text": "Order CBC and BMP today because A1c was elevated."},
    {"id": 6, "category": "warning_signs", "unit_id": 6,
     "quote": "call 911 if chest pain worsens", "char_start": 0, "char_end": 31,
     "text": "Call 911 if chest pain worsens."},
]


def _base_draft() -> dict:
    return {
        "schema_version": "1.0", "plugin_version": "0.1.0",
        "summary": "", "summary_fact_ids": [],
        "reason_for_visit": [],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [],
        },
        "medications": [], "tests": [], "procedures": [], "other": [],
        "follow_up": [], "warning_signs": [], "questions": [], "low_priority": [],
        "meta": {"run_id": "r", "plugin_version": "0.1.0", "schema_version": "1.0",
                  "level": "standard", "created_at": "2026-09-22T00:00:00+00:00"},
        "notices": [], "terms": {},
    }


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_facts(run_dir: str) -> None:
    data = {
        "schema_version": "1.0", "plugin_version": "0.1.0",
        "run_id": os.path.basename(run_dir),
        "facts": FACTS, "dropped": [],
    }
    _write_json(os.path.join(run_dir, "02_facts.json"), data)


class TestNumericParity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = self._tmp.name
        _write_facts(self.run_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_draft(self, draft: dict) -> None:
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), draft)

    def _run(self) -> dict:
        rc = numeric_parity._run(self.run_dir)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.run_dir, "03_flags.json"), encoding="utf-8") as f:
            return json.load(f)

    def _mismatch_paths(self, flags: dict) -> set:
        return {m["path"] for m in flags["numeric_parity"]}

    # --- changed dose -----------------------------------------------------

    def test_detects_changed_dose(self):
        draft = _base_draft()
        draft["medications"] = [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "50 mg", "frequency": "", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [2]},
        ]
        self._write_draft(draft)
        flags = self._run()
        self.assertIn("medications[0].dosage", self._mismatch_paths(flags))

    # --- unit change --------------------------------------------------------

    def test_detects_unit_change(self):
        draft = _base_draft()
        draft["medications"] = [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "25 mcg", "frequency": "", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [2]},
        ]
        self._write_draft(draft)
        flags = self._run()
        self.assertIn("medications[0].dosage", self._mismatch_paths(flags))

    # --- dates and times are ignored ----------------------------------------

    def test_ignores_dates_and_times(self):
        draft = _base_draft()
        draft["follow_up"] = [
            {"time_frame": "soon", "description": "Come back on 5/6 at 9:00 AM.",
             "status": "to_do", "source_fact_ids": [4]},
        ]
        self._write_draft(draft)
        flags = self._run()
        self.assertNotIn("follow_up[0].description", self._mismatch_paths(flags))
        self.assertEqual(flags["numeric_parity"], [])

    # --- spacing tolerance ---------------------------------------------------

    def test_tolerates_spacing_variant(self):
        draft = _base_draft()
        draft["medications"] = [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             # backing fact 2 has "25mg" (no space); field uses "25 mg" (spaced)
             "dosage": "25 mg", "frequency": "", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [2]},
        ]
        self._write_draft(draft)
        flags = self._run()
        self.assertNotIn("medications[0].dosage", self._mismatch_paths(flags))

    # --- thin why -------------------------------------------------------------

    def test_flags_thin_why(self):
        draft = _base_draft()
        draft["tests"] = [
            {"title": "Blood tests", "plain_name": "", "why": "It helps.",
             "description": "CBC and BMP were ordered.", "preparation": "",
             "status": "to_do", "source_fact_ids": [5]},
        ]
        self._write_draft(draft)
        flags = self._run()
        thin_paths = {t["path"] for t in flags["thin_fields"]}
        self.assertIn("tests[0].why", thin_paths)

    def test_informative_why_not_flagged(self):
        draft = _base_draft()
        draft["tests"] = [
            {"title": "Blood tests", "plain_name": "", "why": "ordered because A1c was elevated",
             "description": "CBC and BMP were ordered today.", "preparation": "",
             "status": "to_do", "source_fact_ids": [5]},
        ]
        self._write_draft(draft)
        flags = self._run()
        thin_paths = {t["path"] for t in flags["thin_fields"]}
        self.assertNotIn("tests[0].why", thin_paths)

    # --- flags.json validates ---------------------------------------------------

    def test_flags_validate_against_schema(self):
        draft = _base_draft()
        draft["medications"] = [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "50 mg", "frequency": "", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [2]},
        ]
        self._write_draft(draft)
        flags = self._run()
        schema = validate.load_schema("flags")
        errors = validate.validate(flags, schema)
        self.assertEqual(errors, [])

    # --- runlog ----------------------------------------------------------------

    def test_records_ok_status(self):
        draft = _base_draft()
        self._write_draft(draft)
        self._run()
        with open(os.path.join(self.run_dir, "run.json"), encoding="utf-8") as f:
            run_log = json.load(f)
        self.assertEqual(run_log["stages"]["numeric_parity"]["status"], "ok")

    # --- CLI ----------------------------------------------------------------

    def test_cli_runs_via_subprocess(self):
        draft = _base_draft()
        draft["medications"] = [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": "50 mg", "frequency": "", "timing": "", "duration": "",
             "instructions": "", "side_effects_to_watch": "", "change": "",
             "status": "to_do", "source_fact_ids": [2]},
        ]
        self._write_draft(draft)

        script = os.path.join(_paths.SCRIPTS_DIR, "numeric_parity.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "03_flags.json")))


if __name__ == "__main__":
    unittest.main()
