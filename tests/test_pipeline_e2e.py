"""Schema-v2 integration tests for the fail-closed K+2 workflow."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


def _script(name: str) -> str:
    return os.path.join(_paths.SCRIPTS_DIR, name)


def _run(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, _script(name), *args], capture_output=True, text=True,
    )


def _run_ok(name: str, *args: str) -> subprocess.CompletedProcess:
    result = _run(name, *args)
    if result.returncode != 0:
        raise AssertionError(
            f"{name} {' '.join(args)} exited {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _root_files(run_dir: str) -> set[str]:
    return {
        name for name in os.listdir(run_dir)
        if os.path.isfile(os.path.join(run_dir, name))
    }


def _visible_fact_ids(plan: dict) -> set[int]:
    visible = set(plan["summary_fact_ids"])
    visible.update(plan["diagnosis"]["changed_since_last_visit_fact_ids"])
    for item in plan["diagnosis"]["details"]:
        visible.update(item["source_fact_ids"])
    for key in (
        "reason_for_visit", "medications", "tests", "procedures", "other",
        "follow_up", "warning_signs", "questions",
    ):
        for item in plan[key]:
            visible.update(item["source_fact_ids"])
    return visible


class PipelineHarness:
    def __init__(
        self,
        root: str,
        *,
        chunk_size: int = 150,
        support_text: str = _runfix.OMITTED_MARKER,
        omission_reason: str = "generic_not_patient_specific",
    ):
        self.root = root
        runs_dir = os.path.join(root, "runs")
        self.source = os.path.join(root, "source.txt")
        self.lines = list(_runfix.NOTE_LINES[:-1]) + [support_text]
        self.omission_reason = omission_reason
        self.assembly_calls = 0
        self.reassembly_payload: dict | None = None
        with open(self.source, "w", encoding="utf-8") as handle:
            handle.write("\n".join(self.lines) + "\n")
        result = _run_ok(
            "unitize.py", "--runs-dir", runs_dir,
            "--input", f"{self.source}:native", "--chunk-size", str(chunk_size),
        )
        self.run_dir = result.stdout.strip().splitlines()[-1]
        self.model_calls: list[str] = []

    @property
    def run_id(self) -> str:
        return os.path.basename(self.run_dir)

    def ground(self, *, retry_first_chunk: bool = False) -> dict:
        units_document = _runfix.read_json(os.path.join(self.run_dir, "01_units.json"))
        for chunk in units_document["chunks"]:
            units = [
                unit for unit in units_document["units"]
                if chunk["first_id"] <= unit["id"] <= chunk["last_id"]
            ]
            raw_path = os.path.join(self.run_dir, f"02_facts.{chunk['k']}.raw.json")
            if retry_first_chunk and chunk["k"] == 1:
                invalid = _runfix.facts_raw_for_units(units)
                invalid["facts"][0]["quote"] = "fabricated quote"
                _runfix.write_json(raw_path, invalid)
                self.model_calls.append(f"ground[{chunk['k']}]-attempt1")
                failed = _run("anchor_check.py", "--run-dir", self.run_dir, "--chunk", str(chunk["k"]))
                if failed.returncode == 0:
                    raise AssertionError("invalid grounding attempt unexpectedly passed")
                shutil.copy2(raw_path, raw_path.replace(".raw.json", ".attempt1.raw.json"))
            _runfix.write_json(raw_path, _runfix.facts_raw_for_units(units))
            self.model_calls.append(f"ground[{chunk['k']}]")
            _run_ok("anchor_check.py", "--run-dir", self.run_dir, "--chunk", str(chunk["k"]))
        _run_ok("merge_facts.py", "--run-dir", self.run_dir)
        if retry_first_chunk:
            runlog.record(
                self.run_dir, "ground", "ok", attempts=2,
                artifacts=["02_facts.1.attempt1.raw.json"], run_id=self.run_id,
            )
        return _runfix.read_json(os.path.join(self.run_dir, "02_facts.json"))

    def assemble(
        self,
        *,
        include_supporting: bool = False,
        relevant_fact_ids: list[int] | None = None,
        retry: bool = False,
    ) -> dict:
        self.assembly_calls += 1
        facts_document = _runfix.read_json(os.path.join(self.run_dir, "02_facts.json"))
        if relevant_fact_ids is None:
            raw = _runfix.plan_raw(
                facts_document["facts"], include_supporting=include_supporting,
                omission_reason=self.omission_reason,
            )
        else:
            accepted = _runfix.read_json(os.path.join(self.run_dir, "03_plan.draft.json"))
            relevant = [
                fact for fact in facts_document["facts"]
                if fact["id"] in set(relevant_fact_ids)
            ]
            self.reassembly_payload = {
                "accepted_draft": copy.deepcopy(accepted),
                "facts": copy.deepcopy(relevant),
                "required_fact_ids": list(relevant_fact_ids),
            }
            raw = copy.deepcopy(accepted)
            for key in ("schema_version", "plugin_version", "meta", "score", "notices"):
                raw.pop(key, None)
            raw["omitted_facts"] = [
                item for item in raw["omitted_facts"]
                if item["fact_id"] not in set(relevant_fact_ids)
            ]
            raw["other"].extend({
                "title": "Additional information",
                "why": None,
                "steps": [],
                "description": fact["text"],
                "frequency": "",
                "duration": "",
                "status": "to_do",
                "source_fact_ids": [fact["id"]],
            } for fact in relevant)
        raw_path = os.path.join(self.run_dir, "03_plan.raw.json")
        if retry:
            invalid = copy.deepcopy(raw)
            invalid.pop("omitted_facts")
            _runfix.write_json(raw_path, invalid)
            self.model_calls.append("assemble-attempt1")
            failed = _run("cite_check.py", "--run-dir", self.run_dir)
            if failed.returncode == 0:
                raise AssertionError("invalid assembly attempt unexpectedly passed")
            shutil.copy2(raw_path, os.path.join(self.run_dir, "03_plan.attempt1.raw.json"))
        _runfix.write_json(raw_path, raw)
        self.model_calls.append("assemble")
        runlog.record(
            self.run_dir, "assemble", "ok",
            attempts=self.assembly_calls + (1 if retry else 0),
            artifacts=["03_plan.raw.json"] + (["03_plan.attempt1.raw.json"] if retry else []),
            run_id=self.run_id,
        )
        _run_ok("cite_check.py", "--run-dir", self.run_dir)
        plan_attempts = runlog.read(self.run_dir)["stages"]["plan_check"]["attempts"]
        runlog.record(
            self.run_dir, "plan_check", "ok", attempts=plan_attempts,
            artifacts=["03_plan.draft.json"], run_id=self.run_id,
        )
        _run_ok("numeric_parity.py", "--run-dir", self.run_dir)
        numeric_attempts = runlog.read(self.run_dir)["stages"]["numeric_parity"]["attempts"]
        runlog.record(
            self.run_dir, "numeric_parity", "ok", attempts=numeric_attempts,
            artifacts=["03_flags.json"], run_id=self.run_id,
        )
        return _runfix.read_json(os.path.join(self.run_dir, "03_plan.draft.json"))

    def review(self, *, reassemble_ids=(), retry: bool = False) -> subprocess.CompletedProcess:
        draft = _runfix.read_json(os.path.join(self.run_dir, "03_plan.draft.json"))
        facts = _runfix.read_json(os.path.join(self.run_dir, "02_facts.json"))["facts"]
        flags = _runfix.read_json(os.path.join(self.run_dir, "03_flags.json"))
        raw = _runfix.review_raw(draft, facts, flags, reassemble_ids=reassemble_ids)
        raw_path = os.path.join(self.run_dir, "04_review.raw.json")
        if retry:
            invalid = copy.deepcopy(raw)
            invalid["reviewed_fact_ids"] = invalid["reviewed_fact_ids"][:-1]
            _runfix.write_json(raw_path, invalid)
            self.model_calls.append("review-attempt1")
            failed = _run("settle_review.py", "--run-dir", self.run_dir)
            if failed.returncode == 0:
                raise AssertionError("invalid review attempt unexpectedly passed")
            shutil.copy2(raw_path, os.path.join(self.run_dir, "04_review.attempt1.raw.json"))
        _runfix.write_json(raw_path, raw)
        self.model_calls.append("review")
        runlog.record(
            self.run_dir, "review", "ok", attempts=2 if retry else None,
            started=True, finished=False,
            artifacts=["04_review.raw.json"] + (["04_review.attempt1.raw.json"] if retry else []),
            run_id=self.run_id,
        )
        return _run("settle_review.py", "--run-dir", self.run_dir)

    def finalize(self) -> subprocess.CompletedProcess:
        return _run("finalize.py", "--run-dir", self.run_dir)


class TestCleanPipeline(unittest.TestCase):
    def test_plan_and_numeric_checks_record_their_required_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(root)
            facts = pipeline.ground()["facts"]
            _runfix.write_json(
                os.path.join(pipeline.run_dir, "03_plan.raw.json"),
                _runfix.plan_raw(facts),
            )
            runlog.record(
                pipeline.run_dir, "assemble", "ok", attempts=1,
                artifacts=["03_plan.raw.json"], run_id=pipeline.run_id,
            )
            _run_ok("cite_check.py", "--run-dir", pipeline.run_dir)
            _run_ok("numeric_parity.py", "--run-dir", pipeline.run_dir)
            stages = runlog.read(pipeline.run_dir)["stages"]
            artifacts = {
                stage: {item["path"] for item in stages[stage]["artifacts"]}
                for stage in ("plan_check", "numeric_parity")
            }
            missing = {
                stage: expected
                for stage, expected in (
                    ("plan_check", "03_plan.draft.json"),
                    ("numeric_parity", "03_flags.json"),
                )
                if expected not in artifacts[stage]
            }
            self.assertEqual(missing, {})

    def test_one_chunk_is_three_model_calls_and_exact_core_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(root)
            facts = pipeline.ground()
            draft = pipeline.assemble()
            review_result = pipeline.review()
            self.assertEqual(review_result.returncode, 0, review_result.stdout + review_result.stderr)
            final_result = pipeline.finalize()
            self.assertEqual(final_result.returncode, 0, final_result.stdout + final_result.stderr)

            self.assertEqual(pipeline.model_calls, ["ground[1]", "assemble", "review"])
            self.assertEqual(_root_files(pipeline.run_dir), set(_runfix.CORE_ARTIFACTS_ONE_CHUNK))
            run_log = _runfix.read_json(os.path.join(pipeline.run_dir, "run.json"))
            for stage in (*_runfix.REQUIRED_CORE_STAGES, "finalize"):
                self.assertEqual(run_log["stages"][stage]["status"], "ok", stage)
                self.assertTrue(run_log["stages"][stage]["artifacts"], stage)
            self.assertEqual(run_log["stages"]["ground"]["checks"]["chunks_expected"], 1)
            self.assertEqual(run_log["stages"]["ground"]["checks"]["chunks_found"], 1)
            self.assertEqual(run_log["stages"]["ground"]["checks"]["missing_chunks"], [])

            omitted = {entry["fact_id"] for entry in draft["omitted_facts"]}
            visible = _visible_fact_ids(draft)
            all_ids = {fact["id"] for fact in facts["facts"]}
            self.assertFalse(visible & omitted)
            self.assertEqual(visible | omitted, all_ids)

            flags = _runfix.read_json(os.path.join(pipeline.run_dir, "03_flags.json"))
            review = _runfix.read_json(os.path.join(pipeline.run_dir, "04_review.json"))
            self.assertEqual(set(review["reviewed_fact_ids"]), all_ids)
            self.assertEqual(
                {item["flag_id"] for item in review["numeric_resolutions"]},
                {item["flag_id"] for item in flags["numeric_parity"]},
            )
            self.assertEqual(review["verdict"], "pass")
            self.assertEqual(
                _runfix.read_json(os.path.join(pipeline.run_dir, "05_plan.settled.json")),
                draft,
            )
            final_plan = _runfix.read_json(os.path.join(pipeline.run_dir, "06_plan.final.json"))
            self.assertEqual(final_plan["schema_version"], SCHEMA_VERSION)
            self.assertEqual(final_plan["meta"]["run_id"], pipeline.run_id)
            self.assertNotIn(_runfix.PII_NAME, json.dumps(final_plan))

    def test_settlement_applies_only_the_named_exact_operation(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(root)
            facts = pipeline.ground()["facts"]
            draft = pipeline.assemble()
            flags = _runfix.read_json(os.path.join(pipeline.run_dir, "03_flags.json"))
            raw_review = _runfix.review_raw(draft, facts, flags)
            medication_id = draft["medications"][0]["source_fact_ids"][0]
            for fact_review in raw_review["fact_reviews"]:
                if fact_review["fact_id"] == medication_id:
                    fact_review["result"] = "visible_needs_correction"
            raw_review["corrections"] = [{"op": "clear", "path": "medications[0].why"}]
            _runfix.write_json(os.path.join(pipeline.run_dir, "04_review.raw.json"), raw_review)
            runlog.record(
                pipeline.run_dir, "review", "ok", attempts=1, started=True, finished=False,
                artifacts=["04_review.raw.json"], run_id=pipeline.run_id,
            )
            result = _run("settle_review.py", "--run-dir", pipeline.run_dir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            settled = _runfix.read_json(os.path.join(pipeline.run_dir, "05_plan.settled.json"))
            expected = copy.deepcopy(draft)
            expected["medications"][0]["why"] = None
            self.assertEqual(settled, expected)
            review = _runfix.read_json(os.path.join(pipeline.run_dir, "04_review.json"))
            self.assertEqual(review["corrections"], raw_review["corrections"])
            self.assertEqual(review["counts"]["corrections"], 1)

    def test_k_chunks_use_k_plus_two_model_calls(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(root, chunk_size=2)
            units = _runfix.read_json(os.path.join(pipeline.run_dir, "01_units.json"))
            chunk_count = len(units["chunks"])
            pipeline.ground()
            pipeline.assemble()
            result = pipeline.review()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(pipeline.model_calls), chunk_count + 2)
            self.assertEqual(
                pipeline.model_calls,
                [f"ground[{index}]" for index in range(1, chunk_count + 1)] + ["assemble", "review"],
            )
            run_log = _runfix.read_json(os.path.join(pipeline.run_dir, "run.json"))
            self.assertEqual(run_log["stages"]["ground"]["checks"]["chunks_expected"], chunk_count)
            self.assertEqual(run_log["stages"]["ground"]["checks"]["chunks_found"], chunk_count)
            self.assertEqual(run_log["stages"]["ground"]["checks"]["missing_chunks"], [])


class TestRetryAndReassembly(unittest.TestCase):
    def test_each_model_stage_allows_one_retry_and_retains_failed_raw_output(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(root)
            pipeline.ground(retry_first_chunk=True)
            pipeline.assemble(retry=True)
            result = pipeline.review(retry=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run_log = _runfix.read_json(os.path.join(pipeline.run_dir, "run.json"))
            for stage in ("ground", "assemble", "plan_check", "review"):
                self.assertEqual(run_log["stages"][stage]["attempts"], 2, stage)
            for name in (
                "02_facts.1.attempt1.raw.json",
                "03_plan.attempt1.raw.json",
                "04_review.attempt1.raw.json",
            ):
                self.assertTrue(os.path.isfile(os.path.join(pipeline.run_dir, name)), name)
            self.assertNotIn("attempt3", " ".join(_root_files(pipeline.run_dir)))

    def test_reassembly_runs_checks_again_and_requires_a_fresh_review(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(
                root,
                support_text="Routine administrative coding was completed.",
                omission_reason="routine_non_actionable",
            )
            facts = pipeline.ground()["facts"]
            support_id = next(fact["id"] for fact in facts if fact["category"] == "other")
            pipeline.assemble()
            first = pipeline.review(reassemble_ids=[support_id])
            self.assertNotEqual(first.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(pipeline.run_dir, "05_plan.settled.json")))
            shutil.copy2(
                os.path.join(pipeline.run_dir, "04_review.raw.json"),
                os.path.join(pipeline.run_dir, "04_review.attempt1.raw.json"),
            )

            pipeline.assemble(include_supporting=True, relevant_fact_ids=[support_id])
            second = pipeline.review()
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            final = pipeline.finalize()
            self.assertEqual(final.returncode, 0, final.stdout + final.stderr)
            run_log = _runfix.read_json(os.path.join(pipeline.run_dir, "run.json"))
            self.assertEqual(run_log["stages"]["assemble"]["attempts"], 2)
            self.assertEqual(run_log["stages"]["plan_check"]["attempts"], 2)
            self.assertEqual(run_log["stages"]["numeric_parity"]["attempts"], 2)
            self.assertEqual(run_log["stages"]["review"]["attempts"], 2)
            self.assertEqual(run_log["stages"]["settle_review"]["attempts"], 2)
            review = _runfix.read_json(os.path.join(pipeline.run_dir, "04_review.json"))
            result_by_id = {item["fact_id"]: item["result"] for item in review["fact_reviews"]}
            self.assertEqual(result_by_id[support_id], "visible_accurate")
            self.assertEqual(pipeline.reassembly_payload["required_fact_ids"], [support_id])
            self.assertEqual(
                [fact["id"] for fact in pipeline.reassembly_payload["facts"]],
                [support_id],
            )
            settled = _runfix.read_json(os.path.join(pipeline.run_dir, "05_plan.settled.json"))
            self.assertIn(support_id, _visible_fact_ids(settled))
            self.assertEqual(len(pipeline.model_calls), 5)

    def test_second_review_reassembly_request_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PipelineHarness(
                root,
                support_text="Routine administrative coding was completed.",
                omission_reason="routine_non_actionable",
            )
            facts = pipeline.ground()["facts"]
            support_id = next(fact["id"] for fact in facts if fact["category"] == "other")
            pipeline.assemble()
            self.assertNotEqual(pipeline.review(reassemble_ids=[support_id]).returncode, 0)
            pipeline.assemble()
            self.assertNotEqual(pipeline.review(reassemble_ids=[support_id]).returncode, 0)
            final = pipeline.finalize()
            self.assertNotEqual(final.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(pipeline.run_dir, "06_plan.final.json")))
            self.assertFalse(os.path.exists(os.path.join(pipeline.run_dir, "report.md")))


class TestFailClosedPublication(unittest.TestCase):
    def test_prepublication_failures_never_create_clinical_outputs(self):
        for failure in ("ground", "assemble", "review"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                pipeline = PipelineHarness(root)
                if failure == "ground":
                    units = _runfix.read_json(os.path.join(pipeline.run_dir, "01_units.json"))["units"]
                    raw = _runfix.facts_raw_for_units(units)
                    raw["facts"][0]["quote"] = "fabricated quote"
                    _runfix.write_json(os.path.join(pipeline.run_dir, "02_facts.1.raw.json"), raw)
                    result = _run("merge_facts.py", "--run-dir", pipeline.run_dir)
                else:
                    facts = pipeline.ground()["facts"]
                    if failure == "assemble":
                        raw = _runfix.plan_raw(facts)
                        raw.pop("omitted_facts")
                        _runfix.write_json(os.path.join(pipeline.run_dir, "03_plan.raw.json"), raw)
                        result = _run("cite_check.py", "--run-dir", pipeline.run_dir)
                    else:
                        draft = pipeline.assemble()
                        flags = _runfix.read_json(os.path.join(pipeline.run_dir, "03_flags.json"))
                        raw_review = _runfix.review_raw(draft, facts, flags)
                        raw_review["reviewed_fact_ids"] = raw_review["reviewed_fact_ids"][:-1]
                        _runfix.write_json(os.path.join(pipeline.run_dir, "04_review.raw.json"), raw_review)
                        result = _run("settle_review.py", "--run-dir", pipeline.run_dir)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(os.path.exists(os.path.join(pipeline.run_dir, "06_plan.final.json")))
                self.assertFalse(os.path.exists(os.path.join(pipeline.run_dir, "report.md")))

    def test_every_core_gate_failure_removes_publication(self):
        cases = (
            "missing_stage",
            "failed_stage",
            "degraded_stage",
            "skipped_stage",
            "missing_artifact",
            "stale_identity",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                run_dir = os.path.join(root, "run")
                _runfix.make_run_dir(run_dir)
                run_log_path = os.path.join(run_dir, "run.json")
                run_log = _runfix.read_json(run_log_path)
                if case == "missing_stage":
                    del run_log["stages"]["review"]
                elif case in {"failed_stage", "degraded_stage", "skipped_stage"}:
                    run_log["stages"]["review"]["status"] = case.removesuffix("_stage")
                elif case == "missing_artifact":
                    os.remove(os.path.join(run_dir, "04_review.json"))
                elif case == "stale_identity":
                    settled = _runfix.read_json(os.path.join(run_dir, "05_plan.settled.json"))
                    settled["meta"]["run_id"] = "stale-run"
                    _runfix.write_json(os.path.join(run_dir, "05_plan.settled.json"), settled)
                if case in {"missing_stage", "failed_stage", "degraded_stage", "skipped_stage"}:
                    _runfix.write_json(run_log_path, run_log)
                _runfix.write_json(os.path.join(run_dir, "06_plan.final.json"), {"stale": True})
                with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as handle:
                    handle.write("stale clinical content")
                result = _run("finalize.py", "--run-dir", run_dir)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("no clinical report was produced", result.stderr)
                self.assertFalse(os.path.exists(os.path.join(run_dir, "06_plan.final.json")))
                self.assertFalse(os.path.exists(os.path.join(run_dir, "report.md")))

    def test_all_current_artifacts_validate_against_schema_v2(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run")
            _runfix.make_run_dir(run_dir)
            _run_ok("finalize.py", "--run-dir", run_dir)
            schema_by_artifact = {
                "run.json": "run",
                "01_units.json": "units",
                "02_facts.json": "facts",
                "03_plan.raw.json": "care_plan_agent",
                "03_plan.draft.json": "care_plan",
                "03_flags.json": "flags",
                "04_review.raw.json": "review_raw",
                "04_review.json": "review",
                "05_plan.settled.json": "care_plan",
                "06_plan.final.json": "care_plan",
            }
            for artifact, schema in schema_by_artifact.items():
                document = _runfix.read_json(os.path.join(run_dir, artifact))
                self.assertEqual(validate.validate(document, validate.load_schema(schema)), [], artifact)
                if "schema_version" in document:
                    self.assertEqual(document["schema_version"], SCHEMA_VERSION, artifact)


if __name__ == "__main__":
    unittest.main()
