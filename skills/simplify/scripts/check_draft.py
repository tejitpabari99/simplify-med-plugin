#!/usr/bin/env python3
"""CHECK: validate the WRITE stage's draft and prepare the verifier's inputs.

CLI: python3 check_draft.py --run-dir D [--round 2]

Reads `02_draft.raw.json` (round 2: `02_draft.r2.raw.json`), `01_units.json`,
`01_protected.json`, and in round 2 `04_repair.json`. The draft must:

- match `schema/draft.schema.json`;
- cite only existing, non-skipped source units;
- back every `coverage` category marked "shown" with a unit some visible
  item also cites ("none_in_source" entries cite nothing);
- contain no leftover empty brackets and no unexpanded clinician names in
  visible text;
- stay within the hard word budget (`BUDGET["max"]`);
- in round 2, cite every unit the verifier reported missing.

On pass it writes `02_draft.json` (the raw draft plus `schema_version` and
`run_id`; schema `draft_checked`) and `02_check.json` (schema `check`: word
count and budget, numeric flags, uncited protected candidates), and records
the `write` and `check` stages as ok.

On a draft failure it prints every error for the one WRITE retry
(`retry=allowed`), moves the failed raw draft to `02_draft.attempt1.raw.json`
(round 2: `02_draft.r2.attempt1.raw.json`), and exits 1. A second failure in
the same round (`retry=exhausted`) leaves the raw draft in place, records
`write` as a terminal failure, and tells the host to stop without clinical
output; every later check, settle, or finalize of the run is refused.

The helpers here (artifact names, citation/coverage/text checks, numeric
flags, word count) are shared by `settle.py` and `finalize.py`.

Stdlib only. Importable as `check_draft`.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)

import plan_paths  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


def _load_numbers():
    """Load scripts/numbers.py by path: `import numbers` may resolve to the
    standard library module of the same name."""
    cached = sys.modules.get("simplify_numbers")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "simplify_numbers", os.path.join(_SCRIPTS_DIR, "numbers.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["simplify_numbers"] = module
    spec.loader.exec_module(module)
    return module


numbers = _load_numbers()

BUDGET = {"target": 300, "warn": 350, "max": 500}
PROTECTED_CATEGORIES = (
    "medication_changes",
    "follow_up",
    "return_precautions",
    "diagnoses",
    "disposition",
    "abnormal_or_pending_results",
)
MAX_ROUND = 2

_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)|\[\s*\]")
# Intentionally not a general name detector: only the two bounded
# clinician-name shapes the pipeline has always handled.
PII_HONORIFIC_RE = re.compile(r"\b(?:Dr\.?|Doctor)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")
PII_CREDENTIAL_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+,?\s+(?:MD|DO|NP|PA|RN)\b")
_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9]")


class CheckError(ValueError):
    """A list of human-readable validation errors."""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


# --- artifact names and I/O ---------------------------------------------

def artifact_names(round_no: int) -> dict[str, str]:
    """Per-round artifact names. Round 1 is unsuffixed; round 2 adds `.r2`.
    A failed first attempt keeps an `.attempt1` suffix before `.raw.json`."""
    if round_no not in (1, 2):
        raise ValueError(f"round must be 1 or 2, got {round_no!r}")
    suffix = "" if round_no == 1 else ".r2"
    return {
        "draft_raw": f"02_draft{suffix}.raw.json",
        "draft_raw_attempt": f"02_draft{suffix}.attempt1.raw.json",
        "draft": f"02_draft{suffix}.json",
        "check": f"02_check{suffix}.json",
        "verify_raw": f"03_verify{suffix}.raw.json",
        "verify_raw_attempt": f"03_verify{suffix}.attempt1.raw.json",
        "verify": f"03_verify{suffix}.json",
    }


REPAIR_NAME = "04_repair.json"
SETTLED_NAME = "04_plan.settled.json"


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_text(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    descriptor, temporary_path = tempfile.mkstemp(prefix=".simplify.", suffix=".tmp", dir=directory)
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


def atomic_write_json(path: str, document) -> None:
    atomic_write_text(path, json.dumps(document, indent=2, sort_keys=False) + "\n")


def remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def schema_errors(document, schema_name: str, label: str) -> list[str]:
    return [f"{label}: {error}" for error in validate.validate(document, validate.load_schema(schema_name))]


def load_source(run_dir: str) -> tuple[str, dict, dict]:
    """Load and cross-check run.json, 01_units.json, and 01_protected.json.

    Returns (run_id, units_by_id, protected_categories). Raises CheckError
    when an input is missing, invalid, or belongs to another run.
    """
    run_log = runlog.read(run_dir)
    run_id = run_log.get("run_id") if isinstance(run_log, dict) else None
    if not isinstance(run_id, str) or not run_id:
        raise CheckError("run.json is missing or does not identify the current run; run unitize.py first")
    errors: list[str] = []
    documents = {}
    for name, schema_name in (("01_units.json", "units"), ("01_protected.json", "protected")):
        try:
            document = read_json(os.path.join(run_dir, name))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"cannot read {name}: {error}")
            continue
        errors.extend(schema_errors(document, schema_name, name))
        if isinstance(document, dict) and document.get("run_id") != run_id:
            errors.append(f"{name} does not belong to the current run")
        documents[name] = document
    if errors:
        raise CheckError(errors)
    units_by_id = {unit["id"]: unit for unit in documents["01_units.json"]["units"]}
    return run_id, units_by_id, documents["01_protected.json"]["categories"]


# --- content checks (shared with settle.py and finalize.py) --------------

def word_count(plan: dict) -> int:
    """Words in the plan's visible strings: whitespace tokens with a letter or digit."""
    return sum(
        1
        for _path, text, _unit_ids in plan_paths.visible_strings(plan)
        for token in text.split()
        if _WORD_CHAR_RE.search(token)
    )


def _unit_id_errors(label: str, unit_ids, units_by_id: dict) -> list[str]:
    errors = []
    for unit_id in unit_ids or []:
        unit = units_by_id.get(unit_id)
        if unit is None:
            errors.append(f"{label} cites unknown unit {unit_id}")
        elif unit.get("skip"):
            errors.append(
                f"{label} cites unit {unit_id}, which is skipped boilerplate ({unit['skip']}) "
                "and is not in 01_source.txt"
            )
    return errors


def citation_errors(plan: dict, units_by_id: dict) -> list[str]:
    """Every visible item cites >= 1 existing, non-skipped unit."""
    errors = []
    for path, item in plan_paths.visible_items(plan):
        unit_ids = item.get("unit_ids") or []
        if not unit_ids:
            errors.append(f"{path} has no unit_ids; every visible item must cite the units that support it")
        errors.extend(_unit_id_errors(path, unit_ids, units_by_id))
    return errors


def coverage_errors(plan: dict, units_by_id: dict) -> list[str]:
    """"shown" coverage is backed by a visible citation; "none_in_source" cites nothing."""
    errors = []
    cited = plan_paths.cited_unit_ids(plan)
    coverage = plan.get("coverage") or {}
    for category in PROTECTED_CATEGORIES:
        entry = coverage.get(category)
        if not isinstance(entry, dict):
            continue
        unit_ids = entry.get("unit_ids") or []
        label = f"coverage.{category}"
        if entry.get("status") == "shown":
            if not unit_ids:
                errors.append(f"{label} is 'shown' but lists no unit_ids")
                continue
            errors.extend(_unit_id_errors(label, unit_ids, units_by_id))
            if not cited.intersection(unit_ids):
                errors.append(
                    f"{label} is 'shown' but none of its unit_ids {sorted(unit_ids)} is cited by a "
                    "visible item; show that content or mark the category 'none_in_source'"
                )
        elif entry.get("status") == "none_in_source" and unit_ids:
            errors.append(f"{label} is 'none_in_source' and must have unit_ids []")
    return errors


def text_errors(plan: dict) -> list[str]:
    """No leftover empty brackets and no unexpanded clinician names."""
    errors = []
    for field_path, text, _unit_ids in plan_paths.visible_strings(plan):
        if _EMPTY_BRACKETS_RE.search(text):
            errors.append(f"{field_path} contains empty brackets; remove them or fill them from the source")
        for pattern in (PII_HONORIFIC_RE, PII_CREDENTIAL_RE):
            match = pattern.search(text)
            if match:
                errors.append(
                    f"{field_path} names a clinician ({match.group(0)!r}); write 'your doctor' "
                    "or the role instead"
                )
                break
    return errors


def budget_errors(plan: dict) -> list[str]:
    count = word_count(plan)
    if count > BUDGET["max"]:
        return [
            f"visible text is {count} words, over the hard maximum of {BUDGET['max']} "
            f"(target {BUDGET['target']}); cut the least important items"
        ]
    return []


def unbacked_numbers(plan: dict, units_by_id: dict) -> list[tuple[str, str, list[int]]]:
    """[(field_path, token, unit_ids)] for number tokens in a visible string
    that do not appear in the text of the units its item cites."""
    out = []
    for field_path, text, unit_ids in plan_paths.visible_strings(plan):
        backing = numbers.backing_tokens(
            units_by_id[unit_id]["text"] for unit_id in unit_ids if unit_id in units_by_id
        )
        for token in numbers.unbacked_tokens(text, backing):
            out.append((field_path, token, list(unit_ids)))
    return out


def numeric_flags(plan: dict, units_by_id: dict) -> list[dict]:
    """Numeric flags for the verifier, with ids n1, n2, ... in report order."""
    return [
        {"flag_id": f"n{index}", "path": path, "token": token, "unit_ids": unit_ids}
        for index, (path, token, unit_ids) in enumerate(unbacked_numbers(plan, units_by_id), start=1)
    ]


def uncited_protected(plan: dict, protected_categories: dict, units_by_id: dict) -> list[dict]:
    """Protected candidate units no visible item cites, with their categories."""
    cited = plan_paths.cited_unit_ids(plan)
    by_unit: dict[int, list[str]] = {}
    for category in PROTECTED_CATEGORIES:
        for unit_id in protected_categories.get(category) or []:
            unit = units_by_id.get(unit_id)
            if unit is None or unit.get("skip") or unit_id in cited:
                continue
            by_unit.setdefault(unit_id, []).append(category)
    return [{"unit_id": unit_id, "categories": by_unit[unit_id]} for unit_id in sorted(by_unit)]


def build_check(plan: dict, units_by_id: dict, protected_categories: dict, *, run_id: str, round_no: int) -> dict:
    count = word_count(plan)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "round": round_no,
        "word_count": count,
        "budget": dict(BUDGET),
        "over_budget": count > BUDGET["warn"],
        "numeric_flags": numeric_flags(plan, units_by_id),
        "uncited_protected": uncited_protected(plan, protected_categories, units_by_id),
    }


def draft_errors(raw, units_by_id: dict, *, repair_missing: list[dict] | None = None) -> list[str]:
    """Every WRITE-contract error in a raw draft (empty list = pass)."""
    if not isinstance(raw, dict):
        return ["the draft must be a JSON object"]
    errors = schema_errors(raw, "draft", "schema")
    if errors:
        return errors
    errors.extend(citation_errors(raw, units_by_id))
    errors.extend(coverage_errors(raw, units_by_id))
    errors.extend(text_errors(raw))
    errors.extend(budget_errors(raw))
    if repair_missing:
        cited = plan_paths.cited_unit_ids(raw)
        for entry in repair_missing:
            if entry["unit_id"] not in cited:
                errors.append(
                    f"repair: unit {entry['unit_id']} ({entry['category']}) was reported missing and "
                    "must be cited by a visible item"
                )
    return errors


def checked_draft(raw: dict, run_id: str) -> dict:
    """The raw draft with run identity first (schema `draft_checked`)."""
    document = {"schema_version": SCHEMA_VERSION, "run_id": run_id}
    document.update(copy.deepcopy(raw))
    return document


def terminal_errors(run_log: dict) -> list[str]:
    """Refuse to continue a run that already stopped after a terminal failure
    (a failed retry, or protected content still missing after repair)."""
    for name, stage in ((run_log or {}).get("stages") or {}).items():
        if isinstance(stage, dict) and (stage.get("checks") or {}).get("terminal"):
            return [
                f"this run already stopped at stage {name} after a terminal failure; "
                "start a new run from the original documents"
            ]
    return []


def load_repair(run_dir: str, run_id: str) -> dict:
    try:
        repair = read_json(os.path.join(run_dir, REPAIR_NAME))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"round 2 needs {REPAIR_NAME} from a round-1 repair request: {error}") from error
    if not isinstance(repair, dict) or repair.get("run_id") != run_id or not isinstance(repair.get("missing"), list):
        raise CheckError(f"{REPAIR_NAME} is malformed or does not belong to the current run")
    return repair


# --- CLI ------------------------------------------------------------------

def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"  {error}", file=sys.stderr)


def _workflow_failure(run_dir: str, run_id: str | None, round_no: int, errors: list[str]) -> int:
    """An input problem the writer cannot fix; no WRITE attempt is consumed."""
    if run_id:
        try:
            runlog.record(
                run_dir, "check", "failed",
                checks={"round": round_no, "errors": errors},
                run_id=run_id,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    print(f"check: failed | round={round_no} workflow_error errors={len(errors)}")
    print("check: the run inputs are missing or invalid; this is not a draft problem.", file=sys.stderr)
    _print_errors(errors)
    return 1


def _draft_failure(run_dir: str, run_id: str, round_no: int, names: dict, errors: list[str]) -> int:
    """A WRITE-contract failure: archive the first attempt, stop after the second."""
    raw_path = os.path.join(run_dir, names["draft_raw"])
    attempt_path = os.path.join(run_dir, names["draft_raw_attempt"])
    attempt = 2 if os.path.exists(attempt_path) else 1
    retry_allowed = attempt == 1
    if retry_allowed:
        os.replace(raw_path, attempt_path)
        artifact = names["draft_raw_attempt"]
    else:
        artifact = names["draft_raw"]
    checks = {
        "round": round_no, "attempt": attempt, "retry_allowed": retry_allowed,
        "terminal": not retry_allowed, "errors": errors,
    }
    runlog.record(run_dir, "write", "failed", checks=checks, artifacts=[artifact], run_id=run_id)
    runlog.record(run_dir, "check", "failed", checks=checks, run_id=run_id)
    if retry_allowed:
        print(f"check: failed | round={round_no} attempt=1 errors={len(errors)} retry=allowed")
        print(
            f"check: the draft was moved to {names['draft_raw_attempt']}. Retry WRITE once: fix every "
            f"error below and write a new {names['draft_raw']}.",
            file=sys.stderr,
        )
    else:
        print(f"check: failed | round={round_no} attempt={attempt} errors={len(errors)} retry=exhausted")
        print(
            "check: the WRITE retry also failed. Stop the run and do not show any clinical content.",
            file=sys.stderr,
        )
    _print_errors(errors)
    return 1


def run(run_dir: str, round_no: int = 1) -> int:
    names = artifact_names(round_no)
    for key in ("draft", "check"):
        remove_quietly(os.path.join(run_dir, names[key]))

    try:
        run_id, units_by_id, protected_categories = load_source(run_dir)
        terminal = terminal_errors(runlog.read(run_dir))
        if terminal:
            raise CheckError(terminal)
        repair_missing = load_repair(run_dir, run_id)["missing"] if round_no == 2 else None
    except CheckError as error:
        return _workflow_failure(run_dir, runlog.read(run_dir).get("run_id"), round_no, error.errors)

    raw_path = os.path.join(run_dir, names["draft_raw"])
    if not os.path.isfile(raw_path):
        return _workflow_failure(
            run_dir, run_id, round_no,
            [f"{names['draft_raw']} is missing; run the WRITE stage first"],
        )
    try:
        raw = read_json(raw_path)
    except (OSError, json.JSONDecodeError) as error:
        return _draft_failure(run_dir, run_id, round_no, names, [f"{names['draft_raw']} is not valid JSON: {error}"])

    errors = draft_errors(raw, units_by_id, repair_missing=repair_missing)
    if errors:
        return _draft_failure(run_dir, run_id, round_no, names, errors)

    draft = checked_draft(raw, run_id)
    check = build_check(draft, units_by_id, protected_categories, run_id=run_id, round_no=round_no)
    internal = schema_errors(draft, "draft_checked", names["draft"]) + schema_errors(check, "check", names["check"])
    if internal:
        return _workflow_failure(run_dir, run_id, round_no, ["internal error in check_draft.py:"] + internal)

    atomic_write_json(os.path.join(run_dir, names["draft"]), draft)
    atomic_write_json(os.path.join(run_dir, names["check"]), check)
    attempt = 2 if os.path.exists(os.path.join(run_dir, names["draft_raw_attempt"])) else 1
    runlog.record(
        run_dir, "write", "ok",
        checks={"round": round_no, "attempt": attempt, "retry_allowed": False, "errors": []},
        artifacts=[names["draft_raw"]], run_id=run_id,
    )
    summary = {
        "round": round_no,
        "errors": [],
        "word_count": check["word_count"],
        "over_budget": check["over_budget"],
        "visible_items": len(plan_paths.visible_items(draft)),
        "numeric_flags": len(check["numeric_flags"]),
        "uncited_protected": len(check["uncited_protected"]),
    }
    runlog.record(
        run_dir, "check", "ok", checks=summary,
        artifacts=[names["draft"], names["check"]], run_id=run_id,
    )
    print(
        f"check: ok | round={round_no} words={check['word_count']} "
        f"over_budget={str(check['over_budget']).lower()} "
        f"numeric_flags={len(check['numeric_flags'])} "
        f"uncited_protected={len(check['uncited_protected'])}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the WRITE draft and prepare the verifier's check file.")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument("--round", type=int, choices=(1, 2), default=1, help="1, or 2 for the repair round")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return run(args.run_dir, args.round)


if __name__ == "__main__":
    sys.exit(main())
