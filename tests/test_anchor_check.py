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
}


class TestCheckFact(unittest.TestCase):
    def test_ok(self):
        fact = {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol 25mg"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertEqual(UNITS_BY_ID[1]["text"][start:end], "metoprolol 25 mg")

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
        fact = {"category": "not_a_real_category", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, UNITS_BY_ID)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_category")

    def test_offsets_located_via_normalized_match(self):
        units = {1: {"id": 1, "text": "Continue   METOPROLOL 25mg   twice daily"}}
        fact = {"category": "medications", "unit_id": 1, "quote": "metoprolol 25mg", "text": "x"}
        ok, reason, start, end = anchor_check.check_fact(fact, units)
        self.assertTrue(ok)
        self.assertEqual(units[1]["text"][start:end], "METOPROLOL 25mg")


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
                    {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol 25mg"},
                    {"category": "medications", "unit_id": 1, "quote": "nonexistent phrase", "text": "bad"},
                ]}, f)

            result = subprocess.run(
                [sys.executable, ANCHOR_CHECK_PY, "--run-dir", run_dir, "--chunk", "1"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ok", result.stdout)
            self.assertIn("drop (quote_not_in_unit)", result.stdout)


if __name__ == "__main__":
    unittest.main()
