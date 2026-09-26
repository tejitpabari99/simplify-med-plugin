import copy
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
from test_plan_view import _base_plan  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _prepare_finalized_run(run_dir):
    run_id = os.path.basename(run_dir)
    plan = _base_plan()
    plan["meta"]["run_id"] = run_id
    _write_json(os.path.join(run_dir, "06_plan.final.json"), plan)
    _write_json(
        os.path.join(run_dir, "run.json"),
        {
            "run_id": run_id,
            "stages": {
                "finalize": {
                    "status": "ok",
                    "attempts": 1,
                    "started_at": "2026-09-26T00:00:00+00:00",
                    "finished_at": "2026-09-26T00:00:01+00:00",
                    "checks": {},
                    "artifacts": [{"path": "06_plan.final.json"}, {"path": "report.md"}],
                },
            },
        },
    )
    return plan


class TestGlossaryCheck(unittest.TestCase):
    def test_matches_only_visible_finalized_content_and_uses_07_artifacts(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _prepare_finalized_run(run_dir)
            raw = {
                "terms": [
                    {"term": "MRI", "matched_term": "MRI", "definition": "A scan that uses magnets.", "source": "llm_proposed"},
                    {"term": "Numb feet", "matched_term": "numb feet", "definition": "Reduced feeling in the feet.", "source": "llm_proposed"},
                ],
            }
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), raw)
            before = copy.deepcopy(plan)
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "02_glossary.json")))
            with open(os.path.join(run_dir, "07_glossary.json"), encoding="utf-8") as handle:
                glossary = json.load(handle)
            self.assertEqual([item["matched_term"] for item in glossary["terms"]], ["MRI"])
            self.assertEqual(validate.validate(glossary, validate.load_schema("glossary")), [])
            with open(os.path.join(run_dir, "06_plan.final.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), before)

    def test_missing_raw_file_writes_empty_optional_artifact_and_skip_reason(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir)
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            with open(os.path.join(run_dir, "07_glossary.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["terms"], [])
            stage = runlog.read(run_dir)["stages"]["glossary"]
            self.assertEqual(stage["status"], "skipped")
            self.assertEqual(stage["skip_reason"], "no glossary proposals were requested")
            self.assertEqual(stage["artifacts"], [{"path": "07_glossary.json"}])

    def test_requires_successful_finalization(self):
        with tempfile.TemporaryDirectory() as run_dir:
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))

    def test_rejects_partial_or_schema_v1_run(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _base_plan("1.0")
            plan["meta"]["run_id"] = os.path.basename(run_dir)
            _write_json(os.path.join(run_dir, "06_plan.final.json"), plan)
            _write_json(os.path.join(run_dir, "run.json"), {"run_id": os.path.basename(run_dir), "stages": {"finalize": {"status": "ok"}}})
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))

    def test_rejects_more_proposals_than_the_optional_schema_allows(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _prepare_finalized_run(run_dir)
            plan["summary"] = "alpha beta gamma delta epsilon zeta"
            _write_json(os.path.join(run_dir, "06_plan.final.json"), plan)
            raw_terms = [
                {"term": term, "matched_term": term, "definition": f"Definition {term}.", "source": "llm_proposed"}
                for term in ("alpha", "ALPHA", "beta", "gamma", "delta", "epsilon", "zeta")
            ]
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), {"terms": raw_terms})
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))


if __name__ == "__main__":
    unittest.main()
