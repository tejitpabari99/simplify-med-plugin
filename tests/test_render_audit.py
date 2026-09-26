import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_audit  # noqa: E402
from test_plan_view import OMITTED_MARKER, _base_plan  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _v2_documents():
    plan = _base_plan()
    facts = {
        "schema_version": "2.0",
        "plugin_version": "0.1.0",
        "run_id": "run-1",
        "facts": [
            {
                "id": fact_id,
                "category": "other" if fact_id == 6 else "diagnosis",
                "unit_id": fact_id,
                "quote": "Check numb feet every day." if fact_id == 6 else f"Source quote {fact_id}.",
                "char_start": 0,
                "char_end": 20,
                "text": "Check numb feet every day." if fact_id == 6 else f"Source quote {fact_id}.",
            }
            for fact_id in range(1, 8)
        ],
        "dropped": [],
    }
    units = {
        "schema_version": "2.0",
        "plugin_version": "0.1.0",
        "run_id": "run-1",
        "units": [
            {
                "id": fact_id,
                "file": "discharge.pdf",
                "page": 2,
                "line": 10 + fact_id,
                "text": "Check numb feet every day." if fact_id == 6 else f"Source quote {fact_id}.",
                "extraction_method": "ocr" if fact_id == 6 else "native",
            }
            for fact_id in range(1, 8)
        ],
        "chunks": [{"k": 1, "first_id": 1, "last_id": 7}],
    }
    review = {
        "schema_version": "2.0",
        "plugin_version": "0.1.0",
        "run_id": "run-1",
        "reviewed_fact_ids": list(range(1, 8)),
        "fact_reviews": [
            {"fact_id": fact_id, "result": "omission_acceptable" if fact_id == 6 else "visible_accurate"}
            for fact_id in range(1, 8)
        ],
        "corrections": [],
        "numeric_resolutions": [],
        "reassemble_fact_ids": [],
        "dropped_operations": [],
        "counts": {},
        "verdict": "pass",
    }
    run_log = {
        "run_id": "run-1",
        "stages": {
            "unitize": {"status": "ok", "attempts": 1, "checks": {}},
            "review": {"status": "ok", "attempts": 1, "checks": {"facts_reviewed": 7}},
            "finalize": {"status": "ok", "attempts": 1, "checks": {}},
        },
    }
    return plan, facts, units, review, run_log


class TestRenderAudit(unittest.TestCase):
    def test_v2_omission_includes_source_reason_and_review_result(self):
        plan, facts, units, review, run_log = _v2_documents()
        text = render_audit.render(plan, facts, units, run_log, review_doc=review)
        self.assertIn("## Omitted facts", text)
        self.assertIn("fact 6", text)
        self.assertIn("discharge.pdf:2:16", text)
        self.assertIn("extraction=ocr", text)
        self.assertIn('"Check numb feet every day."', text)
        self.assertIn("reason=generic_not_patient_specific", text)
        self.assertIn("review=omission_acceptable", text)

    def test_v2_visible_items_and_questions_show_source_traceability(self):
        plan, facts, units, review, run_log = _v2_documents()
        text = render_audit.render(plan, facts, units, run_log, review_doc=review)
        self.assertIn("1. Do I need another heart tracing?", text)
        self.assertIn("fact 7 · discharge.pdf:2:17 · extraction=native", text)

    def test_v1_coverage_compatibility(self):
        plan = _base_plan("1.0")
        facts = {
            "facts": [{"id": 8, "unit_id": 1, "quote": "Legacy missing fact."}],
            "dropped": [],
        }
        units = {"units": [{"id": 1, "file": "note.txt", "page": 1, "line": 4, "text": "Legacy missing fact.", "extraction_method": "native"}]}
        coverage = {"missing": [8]}
        text = render_audit.render(
            plan,
            facts,
            units,
            {"stages": {"finalize": {"status": "ok", "attempts": 1, "checks": {}}}},
            coverage_doc=coverage,
        )
        self.assertIn("## Low priority (not shown to the patient)", text)
        self.assertIn(OMITTED_MARKER, text)
        self.assertIn("## Facts not present in the plan", text)
        self.assertIn("fact 8", text)

    def test_cli_writes_v2_audit_without_mutating_inputs(self):
        plan, facts, units, review, run_log = _v2_documents()
        with tempfile.TemporaryDirectory() as run_dir:
            for name, document in (
                ("06_plan.final.json", plan),
                ("02_facts.json", facts),
                ("01_units.json", units),
                ("04_review.json", review),
                ("run.json", run_log),
            ):
                _write_json(os.path.join(run_dir, name), document)
            before = copy.deepcopy(plan)
            rc = render_audit.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            with open(os.path.join(run_dir, "06_plan.final.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), before)
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "report.audit.md")))

    def test_cli_rejects_partial_v1(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "06_plan.final.json"), _base_plan("1.0"))
            _write_json(os.path.join(run_dir, "02_facts.json"), {"facts": [], "dropped": []})
            _write_json(os.path.join(run_dir, "01_units.json"), {"units": []})
            _write_json(os.path.join(run_dir, "run.json"), {"stages": {"assemble": {"status": "ok"}}})
            script = os.path.join(_paths.SCRIPTS_DIR, "render_audit.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed schema-v1 final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.audit.md")))


if __name__ == "__main__":
    unittest.main()
