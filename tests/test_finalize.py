import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import finalize  # noqa: E402
import numeric_parity  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


PII_NAME = "Doctor Jane Smith"
REQUIRED_STAGES = (
    "unitize", "ground", "assemble", "plan_check", "numeric_parity",
    "review", "settle_review",
)


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _fact(fact_id, category, text):
    return {
        "id": fact_id,
        "category": category,
        "unit_id": fact_id,
        "quote": text,
        "char_start": 0,
        "char_end": len(text),
        "text": text,
    }


def _plan(run_id, plugin_version):
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "meta": {
            "run_id": run_id,
            "plugin_version": plugin_version,
            "schema_version": SCHEMA_VERSION,
            "level": "standard",
            "created_at": "2026-09-26T00:00:00+00:00",
        },
        "summary": "You came in for chest pain and can follow up soon.",
        "summary_fact_ids": [1, 2],
        "reason_for_visit": [{
            "reason": "Chest pain",
            "description": "You came in for chest pain.",
            "source_fact_ids": [1],
        }],
        "diagnosis": {
            "changed_since_last_visit": "",
            "changed_since_last_visit_fact_ids": [],
            "details": [],
        },
        "medications": [],
        "tests": [],
        "procedures": [],
        "other": [],
        "follow_up": [{
            "time_frame": "soon",
            "description": f"Follow up with {PII_NAME} soon.",
            "status": "to_do",
            "source_fact_ids": [2],
        }],
        "warning_signs": [],
        "questions": [],
        "omitted_facts": [{
            "fact_id": 3,
            "reason": "generic_not_patient_specific",
        }],
    }


class FinalizeRunCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = self.temporary.name
        self.run_id = "current-run-id"
        self.plugin_version = runlog.plugin_version()
        self.facts = [
            _fact(1, "reason_for_visit", "You came in for chest pain."),
            _fact(2, "follow_up", f"Follow up with {PII_NAME} soon."),
            _fact(3, "other", "All adults should exercise regularly. This is general education."),
        ]
        self.plan = _plan(self.run_id, self.plugin_version)
        self._write_complete_run()

    def _write_complete_run(self):
        os.makedirs(os.path.join(self.run_dir, "00_input"), exist_ok=True)
        with open(os.path.join(self.run_dir, "00_input", "visit.txt"), "w", encoding="utf-8") as handle:
            handle.write("You came in for chest pain. Follow up with your doctor soon.\n")

        units = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": self.plugin_version,
            "run_id": self.run_id,
            "units": [
                {
                    "id": fact["unit_id"], "file": "visit.txt", "page": 1,
                    "line": fact["id"], "text": fact["quote"],
                    "extraction_method": "native",
                }
                for fact in self.facts
            ],
            "chunks": [{"k": 1, "first_id": 1, "last_id": len(self.facts)}],
        }
        facts = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": self.plugin_version,
            "run_id": self.run_id,
            "facts": copy.deepcopy(self.facts),
            "dropped": [],
        }
        raw_facts = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": self.plugin_version,
            "facts": [
                {key: fact[key] for key in ("category", "unit_id", "quote", "text")}
                for fact in self.facts
            ],
        }
        raw_plan = copy.deepcopy(self.plan)
        for key in ("schema_version", "plugin_version", "meta"):
            raw_plan.pop(key)
        flags = numeric_parity.build_numeric_flags(
            self.plan, facts, run_id=self.run_id, plugin_version=self.plugin_version,
        )
        raw_review = {
            "reviewed_fact_ids": [1, 2, 3],
            "fact_reviews": [
                {"fact_id": 1, "result": "visible_accurate"},
                {"fact_id": 2, "result": "visible_accurate"},
                {"fact_id": 3, "result": "omission_acceptable"},
            ],
            "corrections": [],
            "numeric_resolutions": [],
            "reassemble_fact_ids": [],
        }
        review = {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": self.plugin_version,
            "run_id": self.run_id,
            **copy.deepcopy(raw_review),
            "dropped_operations": [],
            "counts": {
                "facts_reviewed": 3,
                "visible_accurate": 2,
                "visible_needs_correction": 0,
                "omission_acceptable": 1,
                "must_include": 0,
                "corrections": 0,
                "numeric_resolutions": 0,
                "dropped_operations": 0,
                "reassemble_facts": 0,
            },
            "verdict": "pass",
        }

        _write_json(os.path.join(self.run_dir, "01_units.json"), units)
        with open(os.path.join(self.run_dir, "01_units.1.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(fact["quote"] for fact in self.facts))
        _write_json(os.path.join(self.run_dir, "02_facts.1.raw.json"), raw_facts)
        _write_json(os.path.join(self.run_dir, "02_facts.json"), facts)
        _write_json(os.path.join(self.run_dir, "03_plan.raw.json"), raw_plan)
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), self.plan)
        _write_json(os.path.join(self.run_dir, "03_flags.json"), flags)
        _write_json(os.path.join(self.run_dir, "04_review.raw.json"), raw_review)
        _write_json(os.path.join(self.run_dir, "04_review.json"), review)
        _write_json(os.path.join(self.run_dir, "05_plan.settled.json"), self.plan)

        runlog.initialize(self.run_dir, self.run_id, [])
        stage_artifacts = {
            "unitize": ["01_units.json", "01_units.1.txt"],
            "ground": ["02_facts.1.raw.json", "02_facts.json"],
            "assemble": ["03_plan.raw.json"],
            "plan_check": ["03_plan.draft.json"],
            "numeric_parity": ["03_flags.json"],
            "review": ["04_review.raw.json", "04_review.json"],
            "settle_review": ["05_plan.settled.json"],
        }
        for stage in REQUIRED_STAGES:
            runlog.record(
                self.run_dir, stage, "ok", artifacts=stage_artifacts[stage],
                run_id=self.run_id,
            )

    def _run(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = finalize._run(self.run_dir)
        return result, stderr.getvalue()

    def _assert_no_outputs(self):
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "06_plan.final.json")))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "report.md")))

    def _mutate_json(self, name, mutate):
        path = os.path.join(self.run_dir, name)
        document = _read_json(path)
        mutate(document)
        _write_json(path, document)


class TestFinalizeSuccess(FinalizeRunCase):
    def test_writes_only_current_run_final_artifacts(self):
        result, stderr = self._run()
        self.assertEqual(result, 0, stderr)
        final = _read_json(os.path.join(self.run_dir, "06_plan.final.json"))
        self.assertEqual(final["schema_version"], SCHEMA_VERSION)
        self.assertEqual(final["plugin_version"], self.plugin_version)
        self.assertEqual(final["meta"]["run_id"], self.run_id)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "report.md")))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "report.html")))
        stage = runlog.read(self.run_dir)["stages"]["finalize"]
        self.assertEqual(stage["status"], "ok")
        self.assertEqual(
            stage["artifacts"],
            [{"path": "06_plan.final.json"}, {"path": "report.md"}],
        )

    def test_loads_only_settled_plan_and_ignores_legacy_additions(self):
        draft = copy.deepcopy(self.plan)
        draft["summary"] = "DRAFT CONTENT MUST NOT BE PUBLISHED."
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), draft)
        _write_json(os.path.join(self.run_dir, "05_additions.json"), {"marker": "MUST NOT MERGE"})
        result, stderr = self._run()
        self.assertEqual(result, 0, stderr)
        final = _read_json(os.path.join(self.run_dir, "06_plan.final.json"))
        self.assertEqual(final["summary"], self.plan["summary"])
        self.assertNotIn("MUST NOT MERGE", json.dumps(final))

    def test_preserves_only_bounded_pii_substitution_and_readability(self):
        result, stderr = self._run()
        self.assertEqual(result, 0, stderr)
        final = _read_json(os.path.join(self.run_dir, "06_plan.final.json"))
        self.assertNotIn(PII_NAME, json.dumps(final))
        self.assertIn("your doctor", json.dumps(final))
        self.assertIn("score", final)
        self.assertIn("before_grade", final["score"])
        self.assertIn("after_grade", final["score"])
        self.assertEqual(final.get("notices", []), [])
        self.assertEqual(validate.validate(final, validate.load_schema("care_plan")), [])


class TestFinalizeGates(FinalizeRunCase):
    def test_missing_required_stage_fails_closed(self):
        self._mutate_json("run.json", lambda document: document["stages"].pop("review"))
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("missing required stage", stderr)
        self._assert_no_outputs()

    def test_non_ok_required_statuses_fail_closed(self):
        for status in ("failed", "degraded", "skipped"):
            with self.subTest(status=status):
                self._write_complete_run()
                self._mutate_json(
                    "run.json",
                    lambda document, value=status: document["stages"]["review"].update(status=value),
                )
                result, stderr = self._run()
                self.assertEqual(result, 1)
                self.assertIn("must have status ok", stderr)
                self._assert_no_outputs()

    def test_missing_required_artifact_record_fails_closed(self):
        self._mutate_json(
            "run.json",
            lambda document: document["stages"]["review"]["artifacts"].remove(
                {"path": "04_review.json"}
            ),
        )
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("missing artifact record", stderr)
        self._assert_no_outputs()

    def test_missing_required_artifact_file_fails_closed(self):
        os.remove(os.path.join(self.run_dir, "03_flags.json"))
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("missing required artifact", stderr)
        self._assert_no_outputs()

    def test_no_draft_fallback(self):
        os.remove(os.path.join(self.run_dir, "05_plan.settled.json"))
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("05_plan.settled.json", stderr)
        self._assert_no_outputs()


class TestFinalizeAssertions(FinalizeRunCase):
    def test_rejects_stale_run_identity(self):
        self._mutate_json(
            "05_plan.settled.json",
            lambda document: document["meta"].update(run_id="stale-run"),
        )
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("run_id", stderr)
        self._assert_no_outputs()

    def test_rejects_stale_schema_or_plugin_versions(self):
        mutations = (
            ("03_flags.json", lambda document: document.update(schema_version="1.0")),
            ("04_review.json", lambda document: document.update(plugin_version="9.9.9")),
        )
        for name, mutation in mutations:
            with self.subTest(name=name):
                self._write_complete_run()
                self._mutate_json(name, mutation)
                result, stderr = self._run()
                self.assertEqual(result, 1)
                self.assertIn("version", stderr)
                self._assert_no_outputs()

    def test_rejects_uncited_content_without_silent_dropping(self):
        def mutate(document):
            document["follow_up"][0]["source_fact_ids"] = [999]

        self._mutate_json("05_plan.settled.json", mutate)
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("citation/disposition", stderr)
        self._assert_no_outputs()

    def test_rejects_unresolved_numeric_flag(self):
        def add_numeric_mismatch(document):
            document["other"] = [{
                "title": "Medicine instruction",
                "why": None,
                "steps": ["Take 50 mg."],
                "description": "Take 50 mg.",
                "frequency": "",
                "duration": "",
                "status": "to_do",
                "source_fact_ids": [1],
            }]

        add_numeric_mismatch(self.plan)
        _write_json(os.path.join(self.run_dir, "03_plan.draft.json"), self.plan)
        _write_json(os.path.join(self.run_dir, "05_plan.settled.json"), self.plan)
        flags = numeric_parity.build_numeric_flags(
            self.plan, self.facts, run_id=self.run_id, plugin_version=self.plugin_version,
        )
        _write_json(os.path.join(self.run_dir, "03_flags.json"), flags)
        result, stderr = self._run()
        self.assertEqual(result, 1)
        self.assertIn("numeric", stderr)
        self._assert_no_outputs()


class TestFinalizeV1Migration(unittest.TestCase):
    def test_partial_v1_run_returns_migration_error_without_rewriting(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "run.json"), {
                "schema_version": "1.0", "plugin_version": "0.1.0",
                "run_id": os.path.basename(run_dir), "stages": {},
            })
            _write_json(os.path.join(run_dir, "03_plan.draft.json"), {
                "schema_version": "1.0", "plugin_version": "0.1.0",
                "summary": "Clinical content must not be returned.",
            })
            before = {
                name: _read_bytes(os.path.join(run_dir, name))
                for name in os.listdir(run_dir)
            }
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = finalize._run(run_dir)
            after = {
                name: _read_bytes(os.path.join(run_dir, name))
                for name in os.listdir(run_dir)
            }
            self.assertEqual(result, 1)
            self.assertIn("schema-v1 partial run", stderr.getvalue())
            self.assertIn("start a new schema-v2 run", stderr.getvalue())
            self.assertEqual(after, before)
            self.assertNotIn("Clinical content", stderr.getvalue())


class TestFinalizeCLI(FinalizeRunCase):
    def test_cli_success_end_to_end(self):
        script = os.path.join(_paths.SCRIPTS_DIR, "finalize.py")
        result = subprocess.run(
            [sys.executable, script, "--run-dir", self.run_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("report.md", result.stdout)
        self.assertIn("finalize: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
