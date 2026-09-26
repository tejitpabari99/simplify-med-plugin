#!/usr/bin/env python3
"""Publish a fully validated schema-v2 Simplify run.

Finalization is assertion-only for clinical content. It reads only the
settled plan, reruns the deterministic safety checks, applies the bounded
PII substitution, computes readability telemetry, and writes the final JSON
and Markdown report atomically.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cite_check  # noqa: E402
import numeric_parity  # noqa: E402
import plan_view  # noqa: E402
import readability  # noqa: E402
import render_md  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


_REQUIRED_STAGE_ARTIFACTS = {
    "unitize": ("01_units.json",),
    "ground": ("02_facts.json",),
    "assemble": ("03_plan.raw.json",),
    "plan_check": ("03_plan.draft.json",),
    "numeric_parity": ("03_flags.json",),
    "review": ("04_review.raw.json", "04_review.json"),
    "settle_review": ("05_plan.settled.json",),
}
_STRUCTURED_ARTIFACTS = {
    "01_units.json": "units",
    "02_facts.json": "facts",
    "03_plan.raw.json": "care_plan_agent",
    "03_plan.draft.json": "care_plan",
    "03_flags.json": "flags",
    "04_review.raw.json": "review_raw",
    "04_review.json": "review",
    "05_plan.settled.json": "care_plan",
}
_SYSTEM_OWNED_ARTIFACTS = (
    "01_units.json",
    "02_facts.json",
    "03_plan.draft.json",
    "03_flags.json",
    "04_review.json",
    "05_plan.settled.json",
)
_V1_INTERMEDIATE_NAMES = (
    "01_units.json",
    "02_facts.json",
    "03_plan.raw.json",
    "03_plan.draft.json",
    "03_flags.json",
    "04_review.json",
    "04_coverage.json",
    "05_plan.corrected.json",
    "05_additions.json",
)
_FINAL_NAMES = ("06_plan.final.json", "report.md")

# This is intentionally not a general name detector. Only the two bounded
# clinician-name shapes already supported by the pipeline are substituted.
_PII_HONORIFIC_RE = re.compile(r"\b(?:Dr\.?|Doctor)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")
_PII_CREDENTIAL_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+,?\s+(?:MD|DO|NP|PA|RN)\b")


class FinalizationError(ValueError):
    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else errors
        super().__init__("; ".join(self.errors))


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise FinalizationError(f"{os.path.basename(path)} must contain a JSON object")
    return document


def _atomic_write_text(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, temporary_path = tempfile.mkstemp(prefix=".finalize.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def _atomic_write_json(path: str, document: dict) -> None:
    _atomic_write_text(path, json.dumps(document, indent=2, sort_keys=False) + "\n")


def _remove_outputs(run_dir: str) -> None:
    for name in _FINAL_NAMES:
        try:
            os.remove(os.path.join(run_dir, name))
        except FileNotFoundError:
            pass


def _schema_version_hint(path: str) -> str | None:
    try:
        document = _read_json(path)
    except (OSError, json.JSONDecodeError, FinalizationError):
        return None
    version = document.get("schema_version")
    return version if isinstance(version, str) else None


def _is_partial_v1_run(run_dir: str) -> bool:
    run_version = _schema_version_hint(os.path.join(run_dir, "run.json"))
    if run_version and run_version.startswith("1."):
        return True
    if run_version is not None:
        return False
    for name in _V1_INTERMEDIATE_NAMES:
        path = os.path.join(run_dir, name)
        version = _schema_version_hint(path) if os.path.isfile(path) else None
        if version and version.startswith("1."):
            return True
    return False


def _artifact_paths(stage: dict) -> set[str]:
    paths = set()
    for artifact in stage.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
            paths.add(artifact["path"])
    return paths


def _require_stage_gates(run_dir: str, run_log: dict) -> None:
    errors: list[str] = []
    stages = run_log.get("stages")
    if not isinstance(stages, dict):
        raise FinalizationError("run.json is missing its stage records")
    for stage_name, required_artifacts in _REQUIRED_STAGE_ARTIFACTS.items():
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            errors.append(f"missing required stage {stage_name}")
            continue
        if stage.get("status") != "ok":
            errors.append(f"required stage {stage_name} must have status ok")
        recorded = _artifact_paths(stage)
        for artifact in required_artifacts:
            if artifact not in recorded:
                errors.append(f"stage {stage_name} is missing artifact record {artifact}")
            if not os.path.isfile(os.path.join(run_dir, artifact)):
                errors.append(f"missing required artifact {artifact}")
    if errors:
        raise FinalizationError(errors)


def _require_chunk_artifacts(run_dir: str, run_log: dict, units: dict) -> None:
    errors: list[str] = []
    unit_artifacts = _artifact_paths(run_log["stages"]["unitize"])
    ground_artifacts = _artifact_paths(run_log["stages"]["ground"])
    chunks = units.get("chunks", [])
    for chunk in chunks if isinstance(chunks, list) else []:
        chunk_number = chunk.get("k") if isinstance(chunk, dict) else None
        if not isinstance(chunk_number, int):
            continue
        unit_name = f"01_units.{chunk_number}.txt"
        raw_name = f"02_facts.{chunk_number}.raw.json"
        for name, recorded, stage_name in (
            (unit_name, unit_artifacts, "unitize"),
            (raw_name, ground_artifacts, "ground"),
        ):
            if name not in recorded:
                errors.append(f"stage {stage_name} is missing artifact record {name}")
            if not os.path.isfile(os.path.join(run_dir, name)):
                errors.append(f"missing required artifact {name}")
    if errors:
        raise FinalizationError(errors)


def _validate_schema(name: str, document: dict, artifact_name: str) -> None:
    errors = validate.validate(document, validate.load_schema(name))
    if errors:
        raise FinalizationError(
            [f"{artifact_name} schema validation failed: {error}" for error in errors]
        )


def _require_identity(
    document: dict,
    artifact_name: str,
    run_id: str,
    plugin_version: str,
) -> None:
    errors = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"{artifact_name} schema version must be {SCHEMA_VERSION}"
        )
    if document.get("plugin_version") != plugin_version:
        errors.append(
            f"{artifact_name} plugin version must be {plugin_version}"
        )
    if artifact_name in {"03_plan.draft.json", "05_plan.settled.json"}:
        meta = document.get("meta")
        if not isinstance(meta, dict):
            errors.append(f"{artifact_name} is missing meta identity")
        else:
            if meta.get("run_id") != run_id:
                errors.append(f"{artifact_name} meta.run_id does not match the current run")
            if meta.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"{artifact_name} meta schema version must be {SCHEMA_VERSION}")
            if meta.get("plugin_version") != plugin_version:
                errors.append(f"{artifact_name} meta plugin version must be {plugin_version}")
    elif document.get("run_id") != run_id:
        errors.append(f"{artifact_name} run_id does not match the current run")
    if errors:
        raise FinalizationError(errors)


def _load_and_assert_artifacts(run_dir: str, run_log: dict) -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for artifact_name, schema_name in _STRUCTURED_ARTIFACTS.items():
        path = os.path.join(run_dir, artifact_name)
        try:
            document = _read_json(path)
        except (OSError, json.JSONDecodeError) as error:
            raise FinalizationError(f"cannot read required artifact {artifact_name}: {error}") from error
        _validate_schema(schema_name, document, artifact_name)
        documents[artifact_name] = document

    units = documents["01_units.json"]
    _require_chunk_artifacts(run_dir, run_log, units)
    for chunk in units["chunks"]:
        artifact_name = f"02_facts.{chunk['k']}.raw.json"
        try:
            raw_facts = _read_json(os.path.join(run_dir, artifact_name))
        except (OSError, json.JSONDecodeError) as error:
            raise FinalizationError(f"cannot read required artifact {artifact_name}: {error}") from error
        _validate_schema("facts_raw", raw_facts, artifact_name)

    run_id = run_log.get("run_id")
    plugin_version = runlog.plugin_version()
    for artifact_name in _SYSTEM_OWNED_ARTIFACTS:
        _require_identity(documents[artifact_name], artifact_name, run_id, plugin_version)
    return documents


def _pii_sweep(value):
    substitutions = 0

    def visit(item):
        nonlocal substitutions
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            item, count = _PII_HONORIFIC_RE.subn("your doctor", item)
            substitutions += count
            item, count = _PII_CREDENTIAL_RE.subn("your doctor", item)
            substitutions += count
        return item

    return visit(copy.deepcopy(value)), substitutions


def _concatenate_input_text(run_dir: str) -> str:
    input_dir = os.path.join(run_dir, "00_input")
    if not os.path.isdir(input_dir):
        return ""
    parts = []
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if name.endswith(".txt") and os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                parts.append(handle.read().replace("\f", "\n"))
    return "\n".join(parts)


def _assert_run_log(run_log: dict, plugin_version: str) -> str:
    errors = []
    if run_log.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"run.json schema version must be {SCHEMA_VERSION}")
    if run_log.get("plugin_version") != plugin_version:
        errors.append(f"run.json plugin version must be {plugin_version}")
    run_id = run_log.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        errors.append("run.json must identify the current run")
    if errors:
        raise FinalizationError(errors)
    return run_id


def _assert_clinical_content(documents: dict[str, dict], final_plan: dict) -> dict:
    facts = documents["02_facts.json"]
    draft = documents["03_plan.draft.json"]
    flags = documents["03_flags.json"]
    review = documents["04_review.json"]
    try:
        citation_checks = cite_check.assert_plan_citations(final_plan, facts)
    except cite_check.PlanCitationError as error:
        raise FinalizationError(
            [f"final citation/disposition assertion failed: {item}" for item in error.errors]
        ) from error
    try:
        numeric_checks = numeric_parity.assert_post_settlement_numeric(
            draft, final_plan, facts, flags, review,
        )
    except numeric_parity.NumericParityError as error:
        raise FinalizationError(
            [f"final numeric assertion failed: {item}" for item in error.errors]
        ) from error
    return {"citation": citation_checks, "numeric": numeric_checks}


def _run(run_dir: str) -> int:
    if _is_partial_v1_run(run_dir):
        print(
            "finalize: schema-v1 partial run cannot be finalized by schema-v2 code; "
            "start a new schema-v2 run from the original source documents.",
            file=sys.stderr,
        )
        return 1

    _remove_outputs(run_dir)
    plugin_version = runlog.plugin_version()
    try:
        run_log = _read_json(os.path.join(run_dir, "run.json"))
        run_id = _assert_run_log(run_log, plugin_version)
        _require_stage_gates(run_dir, run_log)
        _validate_schema("run", run_log, "run.json")
        documents = _load_and_assert_artifacts(run_dir, run_log)

        settled = documents["05_plan.settled.json"]
        _assert_clinical_content(documents, settled)
        final_plan, pii_substitutions = _pii_sweep(settled)
        final_plan["score"] = {
            "before_grade": readability.fk_grade(_concatenate_input_text(run_dir)),
            "after_grade": readability.fk_grade(plan_view.visible_text(final_plan)),
        }
        _require_identity(
            final_plan, "05_plan.settled.json", run_id, plugin_version,
        )
        _validate_schema("care_plan", final_plan, "06_plan.final.json")
        checks = _assert_clinical_content(documents, final_plan)
        markdown = render_md.render(final_plan)
    except (OSError, json.JSONDecodeError, FinalizationError) as error:
        errors = error.errors if isinstance(error, FinalizationError) else [str(error)]
        print("finalize: workflow error; no clinical report was produced.", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        _remove_outputs(run_dir)
        return 1

    final_path = os.path.join(run_dir, "06_plan.final.json")
    report_path = os.path.join(run_dir, "report.md")
    try:
        _atomic_write_json(final_path, final_plan)
        _atomic_write_text(report_path, markdown)
        runlog.record(
            run_dir,
            "finalize",
            "ok",
            checks={
                "citation": checks["citation"],
                "numeric": checks["numeric"],
                "pii_substitutions": pii_substitutions,
                "before_grade": final_plan["score"]["before_grade"],
                "after_grade": final_plan["score"]["after_grade"],
            },
            artifacts=["06_plan.final.json", "report.md"],
            run_id=run_id,
        )
    except (OSError, ValueError) as error:
        _remove_outputs(run_dir)
        print("finalize: workflow error; no clinical report was produced.", file=sys.stderr)
        print(f"  could not publish validated artifacts: {error}", file=sys.stderr)
        return 1

    print(report_path)
    score_line = plan_view.score_line(final_plan["score"])
    print(score_line if score_line else "Reading level: not enough text to estimate.")
    print(
        "finalize: ok | "
        f"pii_substitutions={pii_substitutions} "
        f"before_grade={final_plan['score']['before_grade']} "
        f"after_grade={final_plan['score']['after_grade']}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assert and publish a fully settled schema-v2 Simplify run."
    )
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run(_build_arg_parser().parse_args(argv).run_dir)


if __name__ == "__main__":
    sys.exit(main())
