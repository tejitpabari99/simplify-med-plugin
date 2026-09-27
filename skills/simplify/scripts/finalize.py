#!/usr/bin/env python3
"""FINALIZE: publish a fully settled Simplify run.

CLI: python3 finalize.py --run-dir D

Finalization is assertion-only for clinical content. It requires the current
run's `unitize`, `write`, `check`, `verify`, and `settle` stages to be ok for
the final round (round 2 when `04_repair.json` exists), every artifact to be
schema-valid and owned by the current run, and the settlement to reproduce
exactly: rerunning the checks and the verifier's operations on the checked
draft must yield `04_plan.settled.json`. It then applies the bounded
clinician-name substitution, computes the readability score, and writes
`05_plan.final.json` (schema `plan`) and `report.md` (`render_md.render`)
atomically. Any failure removes both outputs and prints a workflow error.

Stdlib only. Importable as `finalize`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_draft  # noqa: E402
import plan_view  # noqa: E402
import readability  # noqa: E402
import render_md  # noqa: E402
import runlog  # noqa: E402
import settle  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402

FINAL_PLAN_NAME = "05_plan.final.json"
REPORT_NAME = "report.md"
_FINAL_NAMES = (FINAL_PLAN_NAME, REPORT_NAME)
_IDENTITY_KEYS = ("schema_version", "run_id")


class FinalizationError(check_draft.CheckError):
    """Any reason the run cannot be published."""


def _remove_outputs(run_dir: str) -> None:
    for name in _FINAL_NAMES:
        check_draft.remove_quietly(os.path.join(run_dir, name))


def final_round(run_dir: str) -> int:
    """2 when a repair round was requested, else 1."""
    return 2 if os.path.exists(os.path.join(run_dir, check_draft.REPAIR_NAME)) else 1


def _artifact_paths(stage: dict) -> set[str]:
    return {
        artifact["path"] for artifact in stage.get("artifacts", [])
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
    }


def _required_stage_artifacts(round_no: int) -> dict[str, tuple[str, ...]]:
    names = check_draft.artifact_names(round_no)
    required = {
        "unitize": ("01_units.json", "01_source.txt", "01_protected.json"),
        "write": (names["draft_raw"],),
        "check": (names["draft"], names["check"]),
        "verify": (names["verify_raw"], names["verify"]),
        "settle": (check_draft.SETTLED_NAME,),
    }
    if round_no == 2:
        required["settle"] += (check_draft.REPAIR_NAME,)
    return required


def _assert_run_log(run_log: dict, plugin_version: str) -> str:
    errors = check_draft.schema_errors(run_log, "run", "run.json")
    if run_log.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"run.json has schema version {run_log.get('schema_version')!r}; this run was started by an "
            "older version of the skill. Start a new run from the original documents."
        )
    if run_log.get("plugin_version") != plugin_version:
        errors.append(f"run.json plugin version must be {plugin_version}")
    if errors:
        raise FinalizationError(errors)
    return run_log["run_id"]


def _require_stage_gates(run_dir: str, run_log: dict, round_no: int) -> None:
    errors: list[str] = check_draft.terminal_errors(run_log)
    stages = run_log.get("stages") or {}
    for stage_name, artifacts in _required_stage_artifacts(round_no).items():
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            errors.append(f"missing required stage {stage_name}")
            continue
        if stage.get("status") != "ok":
            errors.append(f"required stage {stage_name} must have status ok (is {stage.get('status')!r})")
        if stage_name != "unitize" and (stage.get("checks") or {}).get("round") != round_no:
            errors.append(f"stage {stage_name} was not completed for the final round {round_no}")
        recorded = _artifact_paths(stage)
        for artifact in artifacts:
            if artifact not in recorded:
                errors.append(f"stage {stage_name} is missing artifact record {artifact}")
            if not os.path.isfile(os.path.join(run_dir, artifact)):
                errors.append(f"missing required artifact {artifact}")
    if errors:
        raise FinalizationError(errors)


def _load(run_dir: str, name: str, schema_name: str, run_id: str | None):
    try:
        document = check_draft.read_json(os.path.join(run_dir, name))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizationError(f"cannot read required artifact {name}: {error}") from error
    errors = check_draft.schema_errors(document, schema_name, name)
    if run_id is not None and isinstance(document, dict) and document.get("run_id") != run_id:
        errors.append(f"{name} run_id does not match the current run")
    if errors:
        raise FinalizationError(errors)
    return document


def _assert_units_identity(run_dir: str, plugin_version: str) -> None:
    units = check_draft.read_json(os.path.join(run_dir, "01_units.json"))
    if units.get("plugin_version") != plugin_version:
        raise FinalizationError(f"01_units.json plugin version must be {plugin_version}")


def _assert_round_one_record(run_dir: str, run_id: str) -> None:
    record = _load(run_dir, check_draft.artifact_names(1)["verify"], "verify", run_id)
    if record["outcome"] != "repair_requested":
        raise FinalizationError("round 2 requires the round-1 verification record to request a repair")


def _assert_settlement(run_dir: str, run_id: str, round_no: int, units_by_id: dict, protected_categories: dict) -> dict:
    """Reproduce CHECK and SETTLE for the final round; return the settled plan."""
    names = check_draft.artifact_names(round_no)
    raw_draft = _load(run_dir, names["draft_raw"], "draft", None)
    draft = _load(run_dir, names["draft"], "draft_checked", run_id)
    check = _load(run_dir, names["check"], "check", run_id)
    raw_verify = _load(run_dir, names["verify_raw"], "verify_raw", None)
    record = _load(run_dir, names["verify"], "verify", run_id)
    settled = _load(run_dir, check_draft.SETTLED_NAME, "draft_checked", run_id)

    errors: list[str] = []
    if draft != check_draft.checked_draft(raw_draft, run_id):
        errors.append(f"{names['draft']} does not match {names['draft_raw']}")
    if check.get("round") != round_no or record.get("round") != round_no:
        errors.append(f"check and verification records must both be for round {round_no}")
    expected_check = check_draft.build_check(
        draft, units_by_id, protected_categories, run_id=run_id, round_no=round_no,
    )
    if check != expected_check:
        errors.append(f"{names['check']} does not match {names['draft']}")
    if record.get("outcome") != "settled":
        errors.append(f"{names['verify']} does not record a settled outcome")
    for key in ("claims", "operations", "numeric_resolutions", "protected_units"):
        if record.get(key) != raw_verify.get(key):
            errors.append(f"{names['verify']} {key} do not match {names['verify_raw']}")
    if errors:
        raise FinalizationError(errors)

    required_units: list[int] = []
    if round_no == 2:
        repair = check_draft.load_repair(run_dir, run_id)
        required_units = sorted({entry["unit_id"] for entry in repair["missing"]})
    try:
        expected, missing, accepted = settle.settle_documents(
            draft, check, raw_verify, units_by_id, required_units=required_units,
        )
    except check_draft.CheckError as error:
        raise FinalizationError([f"settlement does not reproduce: {item}" for item in error.errors]) from error
    if missing:
        raise FinalizationError("the verification still reports missing protected content")
    if accepted != record["accepted_numeric"]:
        errors.append(f"{names['verify']} accepted numbers do not match the verification")
    if expected != settled:
        errors.append(f"{check_draft.SETTLED_NAME} does not match the verifier's operations on {names['draft']}")
    if errors:
        raise FinalizationError(errors)
    return settled


def pii_sweep(value):
    """Replace the two bounded clinician-name shapes with "your doctor"."""
    substitutions = 0

    def visit(item):
        nonlocal substitutions
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            for pattern in (check_draft.PII_HONORIFIC_RE, check_draft.PII_CREDENTIAL_RE):
                item, count = pattern.subn("your doctor", item)
                substitutions += count
        return item

    return visit(copy.deepcopy(value)), substitutions


def source_text(units_by_id: dict) -> str:
    """The non-skipped source text, for the before-simplification grade."""
    return "\n".join(
        units_by_id[unit_id]["text"] for unit_id in sorted(units_by_id)
        if not units_by_id[unit_id].get("skip")
    )


def build_final_plan(
    settled: dict,
    *,
    run_id: str,
    plugin_version: str,
    notices: list[str],
    before_grade,
) -> tuple[dict, int]:
    content, substitutions = pii_sweep(
        {key: value for key, value in settled.items() if key not in _IDENTITY_KEYS}
    )
    final = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "word_count": 0,
        "score": {"before_grade": before_grade, "after_grade": None},
        "notices": list(notices),
    }
    final.update(content)
    final["word_count"] = check_draft.word_count(final)
    final["score"]["after_grade"] = readability.fk_grade(plan_view.visible_text(final))
    return final, substitutions


def _failed(run_dir: str, run_id: str | None, errors: list[str]) -> int:
    _remove_outputs(run_dir)
    if run_id:
        try:
            runlog.record(run_dir, "finalize", "failed", checks={"errors": errors}, run_id=run_id)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    print(f"finalize: failed | errors={len(errors)}")
    print("finalize: workflow error; no clinical report was produced.", file=sys.stderr)
    for item in errors:
        print(f"  {item}", file=sys.stderr)
    return 1


def run(run_dir: str) -> int:
    _remove_outputs(run_dir)
    plugin_version = runlog.plugin_version()
    run_id = None
    try:
        try:
            run_log = check_draft.read_json(os.path.join(run_dir, "run.json"))
        except (OSError, json.JSONDecodeError) as error:
            raise FinalizationError(f"cannot read run.json: {error}") from error
        if not isinstance(run_log, dict):
            raise FinalizationError("run.json must contain a JSON object")
        run_id = _assert_run_log(run_log, plugin_version)
        round_no = final_round(run_dir)
        _require_stage_gates(run_dir, run_log, round_no)
        loaded_run_id, units_by_id, protected_categories = check_draft.load_source(run_dir)
        if loaded_run_id != run_id:
            raise FinalizationError("source artifacts do not belong to the current run")
        _assert_units_identity(run_dir, plugin_version)
        if round_no == 2:
            _assert_round_one_record(run_dir, run_id)
        settled = _assert_settlement(run_dir, run_id, round_no, units_by_id, protected_categories)
        final_plan, substitutions = build_final_plan(
            settled,
            run_id=run_id,
            plugin_version=plugin_version,
            notices=run_log.get("notices") or [],
            before_grade=readability.fk_grade(source_text(units_by_id)),
        )
        plan_errors = check_draft.schema_errors(final_plan, "plan", FINAL_PLAN_NAME)
        if plan_errors:
            raise FinalizationError(plan_errors)
        markdown = render_md.render(final_plan)
    except check_draft.CheckError as error:
        return _failed(run_dir, run_id, error.errors)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _failed(run_dir, run_id, [f"{type(error).__name__}: {error}"])

    final_path = os.path.join(run_dir, FINAL_PLAN_NAME)
    report_path = os.path.join(run_dir, REPORT_NAME)
    try:
        check_draft.atomic_write_json(final_path, final_plan)
        check_draft.atomic_write_text(report_path, markdown)
        runlog.record(
            run_dir,
            "finalize",
            "ok",
            checks={
                "round": round_no,
                "errors": [],
                "word_count": final_plan["word_count"],
                "pii_substitutions": substitutions,
                "before_grade": final_plan["score"]["before_grade"],
                "after_grade": final_plan["score"]["after_grade"],
            },
            artifacts=[FINAL_PLAN_NAME, REPORT_NAME],
            run_id=run_id,
        )
    except (OSError, ValueError) as error:
        return _failed(run_dir, run_id, [f"could not publish validated artifacts: {error}"])

    print(report_path)
    score_line = plan_view.score_line(final_plan["score"])
    print(score_line if score_line else "Reading level: not enough text to estimate.")
    print(
        f"finalize: ok | round={round_no} words={final_plan['word_count']} "
        f"pii_substitutions={substitutions} "
        f"before_grade={final_plan['score']['before_grade']} "
        f"after_grade={final_plan['score']['after_grade']}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assert and publish a fully settled Simplify run.")
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(_build_arg_parser().parse_args(argv).run_dir)


if __name__ == "__main__":
    sys.exit(main())
