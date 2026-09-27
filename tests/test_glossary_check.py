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
from test_plan_view import _fixture_plan  # noqa: E402


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _prepare_finalized_run(run_dir, plan=None):
    run_id = os.path.basename(run_dir)
    plan = plan or _fixture_plan()
    plan["run_id"] = run_id
    _write_json(os.path.join(run_dir, "05_plan.final.json"), plan)
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
                    "artifacts": [{"path": "05_plan.final.json"}, {"path": "report.md"}],
                },
            },
        },
    )
    return plan


def _term(matched, definition=None):
    return {
        "term": matched,
        "matched_term": matched,
        "definition": f"Definition of {matched}." if definition is None else definition,
        "source": "llm_proposed",
    }


def _glossary(run_dir):
    with open(os.path.join(run_dir, "07_glossary.json"), encoding="utf-8") as handle:
        return json.load(handle)


class TestGlossaryCheck(unittest.TestCase):
    def test_keeps_only_terms_visible_in_the_final_report(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _prepare_finalized_run(run_dir)
            raw = {
                "terms": [
                    _term("bundle branch block"),
                    _term("First-degree AV block"),
                    _term("paresthesias"),  # source wording, not in the report
                    _term("STEMI"),  # source wording, not in the report
                ],
            }
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), raw)
            before = copy.deepcopy(plan)
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            glossary = _glossary(run_dir)
            self.assertEqual(
                [item["matched_term"] for item in glossary["terms"]],
                ["bundle branch block", "First-degree AV block"],
            )
            self.assertEqual(glossary["schema_version"], "3.0")
            self.assertEqual(glossary["run_id"], os.path.basename(run_dir))
            self.assertEqual(validate.validate(glossary, validate.load_schema("glossary")), [])
            with open(os.path.join(run_dir, "05_plan.final.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), before)
            stage = runlog.read(run_dir)["stages"]["glossary"]
            self.assertEqual(stage["status"], "degraded")
            self.assertEqual(stage["checks"]["dropped_not_visible"], 2)

    def test_matches_diagnosis_plain_name_only_when_it_is_shown(self):
        plan = _fixture_plan()
        plan["diagnoses"][0]["plain_name"] = "ACUTE HEADACHE"
        plan["diagnoses"][1]["plain_name"] = "paresthesias"
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir, plan)
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), {"terms": [_term("paresthesias")]})
            self.assertEqual(glossary_check.main(["--run-dir", run_dir]), 0)
            self.assertEqual([item["matched_term"] for item in _glossary(run_dir)["terms"]], ["paresthesias"])
            self.assertEqual(runlog.read(run_dir)["stages"]["glossary"]["status"], "ok")

    def test_drops_duplicates_and_empty_definitions(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir)
            raw = {"terms": [_term("aneurysm"), _term("Aneurysm"), _term("angiogram", definition="  ")]}
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), raw)
            self.assertEqual(glossary_check.main(["--run-dir", run_dir]), 0)
            self.assertEqual([item["matched_term"] for item in _glossary(run_dir)["terms"]], ["aneurysm"])
            checks = runlog.read(run_dir)["stages"]["glossary"]["checks"]
            self.assertEqual(checks["dropped_duplicate"], 1)
            self.assertEqual(checks["dropped_empty_definition"], 1)

    def test_missing_raw_file_writes_empty_optional_artifact_and_skip_reason(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir)
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            self.assertEqual(_glossary(run_dir)["terms"], [])
            stage = runlog.read(run_dir)["stages"]["glossary"]
            self.assertEqual(stage["status"], "skipped")
            self.assertEqual(stage["skip_reason"], "no glossary proposals were requested")
            self.assertEqual(stage["artifacts"], [{"path": "07_glossary.json"}])

    def test_requires_successful_finalization(self):
        with tempfile.TemporaryDirectory() as run_dir:
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir)
            _write_json(
                os.path.join(run_dir, "run.json"),
                {"run_id": os.path.basename(run_dir), "stages": {"settle": {"status": "ok"}}},
            )
            self.assertEqual(glossary_check.main(["--run-dir", run_dir]), 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))

    def test_rejects_old_schema_or_foreign_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _fixture_plan()
            plan["schema_version"] = "2.0"
            _prepare_finalized_run(run_dir, plan)
            self.assertEqual(glossary_check.main(["--run-dir", run_dir]), 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))
        with tempfile.TemporaryDirectory() as run_dir:
            plan = _prepare_finalized_run(run_dir)
            plan["run_id"] = "other-run"
            _write_json(os.path.join(run_dir, "05_plan.final.json"), plan)
            self.assertEqual(glossary_check.main(["--run-dir", run_dir]), 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))

    def test_rejects_more_proposals_than_the_optional_schema_allows(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _prepare_finalized_run(run_dir)
            raw_terms = [
                _term(term)
                for term in ("MRI", "mri", "CT", "angiogram", "aneurysm", "artery", "bundle branch block")
            ]
            _write_json(os.path.join(run_dir, "07_glossary.raw.json"), {"terms": raw_terms})
            rc = glossary_check.main(["--run-dir", run_dir])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "07_glossary.json")))


if __name__ == "__main__":
    unittest.main()
