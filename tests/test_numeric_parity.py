import copy
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
    {"id": 1, "category": "medications", "unit_id": 1,
     "quote": "metoprolol 25 mg twice daily", "char_start": 0, "char_end": 29,
     "text": "Start metoprolol 25 mg twice daily."},
    {"id": 2, "category": "follow_up", "unit_id": 2,
     "quote": "follow up in 3 months", "char_start": 0, "char_end": 21,
     "text": "Follow up in 3 months."},
]


def _plan(dosage: str = "50 mg") -> dict:
    return {
        "summary": "Start metoprolol and follow up in 3 months.",
        "summary_fact_ids": [1, 2],
        "reason_for_visit": [],
        "diagnosis": {"changed_since_last_visit": "",
                      "changed_since_last_visit_fact_ids": [], "details": []},
        "medications": [
            {"title": "Metoprolol", "plain_name": "metoprolol", "why": None,
             "dosage": dosage, "frequency": "twice daily", "timing": "",
             "duration": "", "instructions": "", "side_effects_to_watch": "",
             "change": "Start", "status": "to_do", "source_fact_ids": [1]},
        ],
        "tests": [], "procedures": [], "other": [],
        "follow_up": [
            {"time_frame": "3 months", "description": "Return in 3 months.",
             "status": "to_do", "source_fact_ids": [2]},
        ],
        "warning_signs": [], "questions": [], "omitted_facts": [],
    }


def _flags(plan=None) -> dict:
    return numeric_parity.build_numeric_flags(plan or _plan(), FACTS,
                                               run_id="run-1", plugin_version="0.2.0")


def _flag_id(flags: dict, path: str = "medications[0].dosage") -> int:
    return next(flag["flag_id"] for flag in flags["numeric_parity"] if flag["path"] == path)


class TestNumericFlags(unittest.TestCase):
    def test_assigns_stable_flag_ids(self):
        first = _flags()
        second = _flags(copy.deepcopy(_plan()))
        self.assertEqual(first["numeric_parity"], second["numeric_parity"])
        self.assertIsInstance(first["numeric_parity"][0]["flag_id"], int)

    def test_flag_id_is_stable_when_an_unrelated_earlier_mismatch_is_added(self):
        original = _flags()
        expanded_plan = _plan()
        expanded_plan["reason_for_visit"] = [{
            "reason": "Symptoms for 6 months", "description": "",
            "source_fact_ids": [2],
        }]
        expanded = _flags(expanded_plan)
        self.assertEqual(_flag_id(original), _flag_id(expanded))

    def test_flags_new_numeric_mismatch(self):
        mismatch = _flags()["numeric_parity"][0]
        self.assertEqual(mismatch["path"], "medications[0].dosage")
        self.assertEqual(mismatch["tokens_in_field"], ["50 mg"])
        self.assertEqual(mismatch["tokens_in_facts"], ["25 mg"])

    def test_preserves_numeric_multiplicity(self):
        flags = _flags(_plan("25 mg plus another 25 mg"))
        mismatch = flags["numeric_parity"][0]
        self.assertEqual(mismatch["tokens_in_field"], ["25 mg", "25 mg"])
        self.assertEqual(mismatch["tokens_in_facts"], ["25 mg"])

    def test_includes_cited_questions_in_numeric_parity(self):
        plan = _plan("25 mg")
        plan["questions"] = [{"question": "Should I return in 6 months?", "source_fact_ids": [2]}]
        flags = _flags(plan)
        self.assertEqual(flags["numeric_parity"][0]["path"], "questions[0].question")

    def test_flags_validate_against_schema(self):
        self.assertEqual(validate.validate(_flags(), validate.load_schema("flags")), [])


class TestPostSettlementAssertions(unittest.TestCase):
    def test_accepts_equivalent_resolution_when_content_is_unchanged(self):
        draft = _plan()
        flags = _flags(draft)
        review = {"numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "equivalent"}],
                  "corrections": []}
        numeric_parity.assert_post_settlement_numeric(draft, copy.deepcopy(draft), FACTS, flags, review)

    def test_requires_one_resolution_per_flag(self):
        flags = _flags()
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "unresolved numeric flag"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan(), FACTS, flags,
                                                          {"numeric_resolutions": [], "corrections": []})

    def test_rejects_duplicate_resolution(self):
        flags = _flags()
        flag_id = _flag_id(flags)
        review = {"numeric_resolutions": [
            {"flag_id": flag_id, "resolution": "equivalent"},
            {"flag_id": flag_id, "resolution": "equivalent"},
        ], "corrections": []}
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "resolved more than once"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan(), FACTS, flags, review)

    def test_rejects_unknown_resolution(self):
        review = {"numeric_resolutions": [{"flag_id": 99, "resolution": "equivalent"}],
                  "corrections": []}
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "unknown numeric flag 99"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan(), FACTS, _flags(), review)

    def test_accepts_exact_corrected_operation_linkage(self):
        draft = _plan()
        settled = _plan("25 mg")
        flags = _flags(draft)
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "corrected",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].dosage",
                             "value": "25 mg", "source_fact_ids": [1]}],
        }
        numeric_parity.assert_post_settlement_numeric(draft, settled, FACTS, flags, review)

    def test_rejects_corrected_resolution_without_exact_operation(self):
        flags = _flags()
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "corrected",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].frequency",
                             "value": "twice daily", "source_fact_ids": [1]}],
        }
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "exact replace operation"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan("25 mg"), FACTS,
                                                          flags, review)

    def test_rejects_corrected_resolution_when_settled_value_contradicts_source(self):
        flags = _flags()
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "corrected",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].dosage",
                             "value": "75 mg", "source_fact_ids": [1]}],
        }
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "remains contradictory"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan("75 mg"), FACTS,
                                                          flags, review)

    def test_rejects_correction_provenance_outside_path_citations(self):
        flags = _flags()
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "corrected",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].dosage",
                             "value": "25 mg", "source_fact_ids": [2]}],
        }
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "outside the path citations"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan("25 mg"), FACTS,
                                                          flags, review)

    def test_rejects_corrected_resolution_without_source_supported_number(self):
        flags = _flags()
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "corrected",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].dosage",
                             "value": "see instructions", "source_fact_ids": [1]}],
        }
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "source-supported numeric content"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan("see instructions"), FACTS,
                                                          flags, review)

    def test_accepts_exact_removed_operation_linkage(self):
        draft = _plan()
        settled = _plan("")
        flags = _flags(draft)
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "removed",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "clear", "path": "medications[0].dosage"}],
        }
        numeric_parity.assert_post_settlement_numeric(draft, settled, FACTS, flags, review)

    def test_rejects_removed_resolution_linked_to_replace(self):
        flags = _flags()
        review = {
            "numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "removed",
                                     "correction_path": "medications[0].dosage"}],
            "corrections": [{"op": "replace", "path": "medications[0].dosage",
                             "value": "", "source_fact_ids": [1]}],
        }
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "exact clear or remove operation"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan(""), FACTS, flags, review)

    def test_rejects_equivalent_resolution_when_content_changed(self):
        flags = _flags()
        review = {"numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "equivalent"}],
                  "corrections": []}
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "equivalent flag .* changed"):
            numeric_parity.assert_post_settlement_numeric(_plan(), _plan("75 mg"), FACTS,
                                                          flags, review)

    def test_rejects_newly_introduced_numeric_content(self):
        draft = _plan()
        flags = _flags()
        settled = copy.deepcopy(draft)
        settled["follow_up"][0]["description"] = "Return in 6 months."
        review = {"numeric_resolutions": [{"flag_id": _flag_id(flags), "resolution": "equivalent"}],
                  "corrections": []}
        with self.assertRaisesRegex(numeric_parity.NumericParityError, "new numeric content"):
            numeric_parity.assert_post_settlement_numeric(draft, settled, FACTS, flags, review)


class TestNumericParityCli(unittest.TestCase):
    def test_preserves_flags_json_cli_output(self):
        with tempfile.TemporaryDirectory() as run_dir:
            facts = {"schema_version": "2.0", "plugin_version": "0.2.0",
                     "run_id": os.path.basename(run_dir), "facts": FACTS, "dropped": []}
            with open(os.path.join(run_dir, "02_facts.json"), "w", encoding="utf-8") as handle:
                json.dump(facts, handle)
            with open(os.path.join(run_dir, "03_plan.draft.json"), "w", encoding="utf-8") as handle:
                json.dump(_plan(), handle)
            script = os.path.join(_paths.SCRIPTS_DIR, "numeric_parity.py")
            result = subprocess.run([sys.executable, script, "--run-dir", run_dir],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            with open(os.path.join(run_dir, "03_flags.json"), encoding="utf-8") as handle:
                flags = json.load(handle)
            self.assertIsInstance(flags["numeric_parity"][0]["flag_id"], int)

    def test_failed_rerun_removes_stale_flags_and_records_failure(self):
        with tempfile.TemporaryDirectory() as run_dir:
            facts = {"schema_version": "2.0", "plugin_version": "0.2.0",
                     "run_id": os.path.basename(run_dir), "facts": FACTS, "dropped": []}
            with open(os.path.join(run_dir, "02_facts.json"), "w", encoding="utf-8") as handle:
                json.dump(facts, handle)
            draft_path = os.path.join(run_dir, "03_plan.draft.json")
            with open(draft_path, "w", encoding="utf-8") as handle:
                json.dump(_plan(), handle)
            self.assertEqual(numeric_parity._run(run_dir), 0)
            with open(draft_path, "w", encoding="utf-8") as handle:
                handle.write("not json")
            self.assertEqual(numeric_parity._run(run_dir), 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "03_flags.json")))
            with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as handle:
                run_log = json.load(handle)
            self.assertEqual(run_log["stages"]["numeric_parity"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
