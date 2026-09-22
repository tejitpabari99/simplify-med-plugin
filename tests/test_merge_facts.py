import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import merge_facts  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _make_units_doc(run_id, units, chunks):
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "units": units,
        "chunks": chunks,
    }


def _unit(id_, text):
    return {"id": id_, "file": "a.txt", "page": 1, "line": id_, "text": text, "extraction_method": "native"}


class TestMergeFacts(unittest.TestCase):
    def _base_units(self, run_dir, run_id):
        units = [
            _unit(1, "Continue metoprolol 25 mg twice daily"),
            _unit(2, "Order fasting lipid panel"),
            _unit(3, "Start aspirin 81mg daily"),
            _unit(4, "ok"),
        ]
        chunks = [{"k": 1, "first_id": 1, "last_id": 2}, {"k": 2, "first_id": 3, "last_id": 4}]
        _write_json(os.path.join(run_dir, "01_units.json"), _make_units_doc(run_id, units, chunks))
        return units, chunks

    def test_renumbering_dedup_and_facts_txt(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            self._base_units(d, run_id)

            chunk1 = {"facts": [
                {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol 25mg twice daily"},
                {"category": "tests", "unit_id": 2, "quote": "fasting lipid panel", "text": "fasting lipid panel ordered"},
            ]}
            chunk2 = {"facts": [
                {"category": "medications", "unit_id": 3, "quote": "aspirin 81mg", "text": "aspirin 81mg daily"},
                # duplicate of chunk1's first fact (case-different quote, same normalized form).
                {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 MG", "text": "dup"},
                # anchor-check failure: quote fails informativeness floor.
                {"category": "medications", "unit_id": 4, "quote": "ok", "text": "bad"},
            ]}
            _write_json(os.path.join(d, "02_facts.1.raw.json"), chunk1)
            _write_json(os.path.join(d, "02_facts.2.raw.json"), chunk2)

            rc = merge_facts.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            with open(os.path.join(d, "02_facts.json"), "r", encoding="utf-8") as f:
                facts_doc = json.load(f)

            ids = [f["id"] for f in facts_doc["facts"]]
            self.assertEqual(ids, [1, 2, 3])  # 4th (duplicate) and 5th (uninformative) dropped

            errors = validate.validate(facts_doc, validate.load_schema("facts"))
            self.assertEqual(errors, [])

            with open(os.path.join(d, "02_facts.txt"), "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[0], "[1] (medications) metoprolol 25mg twice daily")
            self.assertEqual(lines[1], "[2] (tests) fasting lipid panel ordered")
            self.assertEqual(lines[2], "[3] (medications) aspirin 81mg daily")

            data = runlog.read(d)
            checks = data["stages"]["ground"]["checks"]
            self.assertEqual(checks["facts_in"], 5)
            self.assertEqual(checks["facts_kept"], 3)
            self.assertEqual(checks["duplicates_removed"], 1)
            self.assertEqual(checks["dropped_by_reason"].get("uninformative_quote"), 1)
            self.assertEqual(data["stages"]["ground"]["status"], "degraded")

    def test_missing_chunk_is_degraded_not_failed(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            units = [_unit(1, "Continue metoprolol 25 mg twice daily")]
            chunks = [{"k": 1, "first_id": 1, "last_id": 1}, {"k": 2, "first_id": 2, "last_id": 2}]
            _write_json(os.path.join(d, "01_units.json"), _make_units_doc(run_id, units, chunks))

            chunk1 = {"facts": [
                {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol"},
            ]}
            _write_json(os.path.join(d, "02_facts.1.raw.json"), chunk1)
            # chunk 2's raw file is deliberately never written.

            rc = merge_facts.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            data = runlog.read(d)
            checks = data["stages"]["ground"]["checks"]
            self.assertEqual(checks["missing_chunks"], [2])
            self.assertEqual(checks["chunks_expected"], 2)
            self.assertEqual(checks["chunks_found"], 1)
            self.assertEqual(data["stages"]["ground"]["status"], "degraded")

    def test_zero_surviving_facts_is_failed(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            units = [_unit(1, "ok")]
            chunks = [{"k": 1, "first_id": 1, "last_id": 1}]
            _write_json(os.path.join(d, "01_units.json"), _make_units_doc(run_id, units, chunks))

            chunk1 = {"facts": [
                {"category": "medications", "unit_id": 1, "quote": "ok", "text": "bad"},
            ]}
            _write_json(os.path.join(d, "02_facts.1.raw.json"), chunk1)

            rc = merge_facts.main(["--run-dir", d])
            self.assertEqual(rc, 1)

            data = runlog.read(d)
            self.assertEqual(data["stages"]["ground"]["status"], "failed")

    def test_nothing_dropped_is_ok_status(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            units = [_unit(1, "Continue metoprolol 25 mg twice daily")]
            chunks = [{"k": 1, "first_id": 1, "last_id": 1}]
            _write_json(os.path.join(d, "01_units.json"), _make_units_doc(run_id, units, chunks))

            chunk1 = {"facts": [
                {"category": "medications", "unit_id": 1, "quote": "metoprolol 25 mg", "text": "metoprolol"},
            ]}
            _write_json(os.path.join(d, "02_facts.1.raw.json"), chunk1)

            rc = merge_facts.main(["--run-dir", d])
            self.assertEqual(rc, 0)
            data = runlog.read(d)
            self.assertEqual(data["stages"]["ground"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
