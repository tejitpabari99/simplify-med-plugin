import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import anchor_check  # noqa: E402

ANCHOR_CHECK_PY = os.path.join(_paths.SCRIPTS_DIR, "anchor_check.py")
UNITIZE_PY = os.path.join(_paths.SCRIPTS_DIR, "unitize.py")


UNITS_BY_ID = {
    1: {"id": 1, "file": "a.txt", "page": 1, "line": 1,
        "text": "Continue metoprolol 25 mg twice daily", "extraction_method": "native"},
    2: {"id": 2, "file": "a.txt", "page": 1, "line": 2,
        "text": "ok", "extraction_method": "native"},
    3: {"id": 3, "file": "a.txt", "page": 1, "line": 3,
        "text": "No evidence of acute stroke", "extraction_method": "native"},
    4: {"id": 4, "file": "a.txt", "page": 1, "line": 4,
        "text": "Possible small infarct remains uncertain", "extraction_method": "native"},
    5: {"id": 5, "file": "a.txt", "page": 1, "line": 5,
        "text": "Take acetaminophen 500 mg every 6 hours if pain returns", "extraction_method": "native"},
    6: {"id": 6, "file": "a.txt", "page": 1, "line": 6,
        "text": "Left-hand tingling persisted for 2 days and is now improving", "extraction_method": "native"},
}


class TestCheckFact(unittest.TestCase):
    def test_ok(self):
        fact = {"category": "medications", "unit_id": 1, "quote": "Continue metoprolol 25 mg twice daily", "text": "metoprolol 25mg"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertEqual(UNITS_BY_ID[1]["text"][start:end], "Continue metoprolol 25 mg twice daily")

    def test_rejects_insufficient_clinical_clause(self):
        fact = {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol 25mg"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "incomplete_clause")

    def test_rejects_quote_that_omits_negation(self):
        fact = {"category": "tests", "unit_id": 3, "quote": "evidence of acute stroke", "text": "stroke found"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "incomplete_clause")

    def test_rejects_quote_that_omits_uncertainty(self):
        fact = {"category": "diagnosis", "unit_id": 4, "quote": "small infarct", "text": "small infarct"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "incomplete_clause")

    def test_rejects_quote_that_omits_condition(self):
        fact = {"category": "medications", "unit_id": 5, "quote": "Take acetaminophen 500 mg every 6 hours", "text": "take acetaminophen"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "incomplete_clause")

    def test_rejects_quote_that_omits_numeric_evidence(self):
        fact = {"category": "medications", "unit_id": 5, "quote": "Take acetaminophen if pain returns", "text": "take acetaminophen"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "quote_not_in_unit")

    def test_rejects_quote_that_omits_body_site_timing_and_status(self):
        fact = {"category": "other", "unit_id": 6, "quote": "tingling persisted", "text": "tingling continued"}
        self.assertEqual(anchor_check.check_fact(fact, UNITS_BY_ID)[1], "incomplete_clause")

    def test_unknown_unit(self):
        fact = {"category": "medications", "unit_id": 999, "quote": "metoprolol", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_unit")

    def test_empty_quote(self):
        fact = {"category": "medications", "unit_id": 1, "quote": "", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "empty_quote")

    def test_quote_not_in_unit(self):
        fact = {"category": "medications", "unit_id": 1, "quote": "atorvastatin 40 mg", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "quote_not_in_unit")

    def test_uninformative_quote(self):
        fact = {"category": "medications", "unit_id": 2, "quote": "ok", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "uninformative_quote")

    def test_bad_category(self):
        fact = {"category": "not_a_real_category", "unit_id": 1, "quote": "Continue metoprolol 25 mg twice daily", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_category")

    def test_offsets_located_via_normalized_match(self):
        units = {1: {"id": 1, "text": "Continue   METOPROLOL 25mg   twice daily"}}
        fact = {"category": "medications", "unit_id": 1, "quote": "Continue metoprolol 25mg twice daily", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, units)
        self.assertTrue(ok)
        self.assertEqual(units[1]["text"][start:end], "Continue   METOPROLOL 25mg   twice daily")


class TestAnchorCheckCLI(unittest.TestCase):
    def _make_run_with_units(self, tmp_dir, unit_texts):
        a = os.path.join(tmp_dir, "a.txt")
        with open(a, "w", encoding="utf-8") as f:
            f.write("\n".join(unit_texts) + "\n")
        run_dir = os.path.join(tmp_dir, "run")
        result = subprocess.run(
            [sys.executable, UNITIZE_PY, "--run-dir", run_dir, "--input", a],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return run_dir

    def test_invalid_schema_prints_errors_and_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = self._make_run_with_units(d, ["Continue metoprolol 25 mg twice daily"])
            raw_path = os.path.join(run_dir, "02_facts.1.raw.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump({"facts": [{"category": "medications", "unit_id": 1}]}, f)  # missing quote/text

            result = subprocess.run(
                [sys.executable, ANCHOR_CHECK_PY, "--run-dir", run_dir, "--chunk", "1"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertTrue(len(result.stdout.strip()) > 0)

    def test_valid_facts_prints_table_and_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = self._make_run_with_units(d, ["Continue metoprolol 25 mg twice daily"])
            raw_path = os.path.join(run_dir, "02_facts.1.raw.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump({"facts": [
                    {"category": "medications", "unit_id": 1, "quote": "Continue metoprolol 25 mg twice daily", "text": "metoprolol 25mg"},
                    {"category": "medications", "unit_id": 1, "quote": "nonexistent phrase", "text": "bad"},
                ]}, f)

            result = subprocess.run(
                [sys.executable, ANCHOR_CHECK_PY, "--run-dir", run_dir, "--chunk", "1"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("ok", result.stdout)
            self.assertIn("drop (quote_not_in_unit)", result.stdout)
            self.assertIn("anchor_check: failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
