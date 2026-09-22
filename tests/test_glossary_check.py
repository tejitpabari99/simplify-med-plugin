import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import glossary_check  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _units_doc(run_id, texts):
    units = [
        {"id": i + 1, "file": "a.txt", "page": 1, "line": i + 1, "text": t, "extraction_method": "native"}
        for i, t in enumerate(texts)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "units": units,
        "chunks": [{"k": 1, "first_id": 1, "last_id": len(units)}] if units else [],
    }


class TestGlossaryCheck(unittest.TestCase):
    def test_missing_raw_file_yields_empty_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            _write_json(os.path.join(d, "01_units.json"), _units_doc(run_id, ["Metoprolol prescribed."]))

            rc = glossary_check.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            with open(os.path.join(d, "02_glossary.json"), "r", encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["terms"], [])

            data = runlog.read(d)
            self.assertEqual(data["stages"]["glossary"]["status"], "skipped")

    def test_drops_term_not_in_source(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            _write_json(os.path.join(d, "01_units.json"), _units_doc(run_id, ["Patient has calcified plaque."]))
            raw = {"terms": [
                {"term": "calcified", "matched_term": "calcified", "definition": "Hardened by calcium buildup.", "source": "llm_proposed"},
                {"term": "stenosis", "matched_term": "stenosis", "definition": "A narrowing of a blood vessel.", "source": "llm_proposed"},
            ]}
            _write_json(os.path.join(d, "02_glossary.raw.json"), raw)

            rc = glossary_check.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            with open(os.path.join(d, "02_glossary.json"), "r", encoding="utf-8") as f:
                doc = json.load(f)
            matched = {t["matched_term"] for t in doc["terms"]}
            self.assertEqual(matched, {"calcified"})

            data = runlog.read(d)
            self.assertEqual(data["stages"]["glossary"]["checks"]["dropped_not_in_source"], 1)
            self.assertEqual(data["stages"]["glossary"]["status"], "degraded")

    def test_caps_at_25_keeping_file_order(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            texts = [f"term{i} appears here" for i in range(30)]
            _write_json(os.path.join(d, "01_units.json"), _units_doc(run_id, texts))
            raw = {"terms": [
                {"term": f"term{i}", "matched_term": f"term{i}", "definition": f"Definition {i}.", "source": "llm_proposed"}
                for i in range(30)
            ]}
            _write_json(os.path.join(d, "02_glossary.raw.json"), raw)

            rc = glossary_check.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            with open(os.path.join(d, "02_glossary.json"), "r", encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(len(doc["terms"]), 25)
            self.assertEqual([t["matched_term"] for t in doc["terms"]], [f"term{i}" for i in range(25)])

            data = runlog.read(d)
            self.assertEqual(data["stages"]["glossary"]["checks"]["dropped_cap"], 5)

    def test_schema_invalid_raw_prints_errors_and_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            _write_json(os.path.join(d, "01_units.json"), _units_doc(run_id, ["Some text."]))
            _write_json(os.path.join(d, "02_glossary.raw.json"), {"terms": [{"term": "x"}]})  # missing fields

            rc = glossary_check.main(["--run-dir", d])
            self.assertEqual(rc, 1)

    def test_force_source_and_dedupe_and_empty_definition(self):
        with tempfile.TemporaryDirectory() as d:
            run_id = os.path.basename(d)
            _write_json(os.path.join(d, "01_units.json"), _units_doc(run_id, ["Patient has calcified plaque."]))
            raw = {"terms": [
                {"term": "calcified", "matched_term": "calcified", "definition": "Hardened by calcium.", "source": "llm_proposed"},
                {"term": "calcified", "matched_term": "CALCIFIED", "definition": "Duplicate entry.", "source": "llm_proposed"},
                {"term": "plaque", "matched_term": "plaque", "definition": "", "source": "llm_proposed"},
            ]}
            _write_json(os.path.join(d, "02_glossary.raw.json"), raw)

            rc = glossary_check.main(["--run-dir", d])
            self.assertEqual(rc, 0)

            with open(os.path.join(d, "02_glossary.json"), "r", encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(len(doc["terms"]), 1)
            self.assertEqual(doc["terms"][0]["source"], "llm_proposed")

            errors = validate.validate(doc, validate.load_schema("glossary"))
            self.assertEqual(errors, [])

            data = runlog.read(d)
            self.assertEqual(data["stages"]["glossary"]["checks"]["dropped_duplicate"], 1)


if __name__ == "__main__":
    unittest.main()
