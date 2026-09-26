#!/usr/bin/env python3
"""SETTLE: validate the independent verification and apply its edits exactly.

CLI: python3 settle.py --run-dir D [--round 2]

Reads `02_draft.json`, `02_check.json`, and `03_verify.raw.json` (round 2:
the `.r2` versions, plus `04_repair.json`), with `01_units.json` and
`01_protected.json`. The verification contract (`schema/verify_raw`) must:

- give every visible item path in the draft exactly one claim, and give
  every `needs_correction` / `unsupported` claim an operation on that item;
- target only visible paths: `replace` a visible text field (its `unit_ids`
  replace the item's citations), `clear` `findings_lead`, `disposition`,
  `medicines.none_statement`, or `diagnoses[i].plain_name`, `remove` an
  array item (applied from the highest index down);
- resolve every numeric flag once: `equivalent` (the text stays as is),
  `corrected` (names the `replace` at the flag's path), or `removed` (names
  the `remove`/`clear` that deletes it, or a `replace` at the flag's path);
- resolve every uncited protected unit once: `covered`, `not_needed` with a
  reason, or `missing`.

After the edits the settled plan must still match `draft_checked`, cite only
valid units, back every "shown" coverage category with a visible citation,
contain only numbers found in cited units or accepted as `equivalent`, and
stay within the hard word budget.

Exit codes:
    0  settled: wrote `03_verify.json` and `04_plan.settled.json`
    1  contract error: the first one (`retry=allowed`) archives the raw
       verification as `03_verify.attempt1.raw.json` for the one VERIFY
       retry; a second one, or protected content still missing in round 2,
       is terminal (`retry=exhausted`: stop without clinical output, and
       every later settle or finalize of the run is refused); a workflow
       error (missing or mismatched inputs) consumes no attempt
    3  repair requested (round 1 only): wrote `03_verify.json` and
       `04_repair.json` with the missing units and the settled draft

Stdlib only. Importable as `settle`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_draft  # noqa: E402
import plan_paths  # noqa: E402
import runlog  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REPAIR = 3

ARRAY_KINDS = ("findings", "diagnoses", "next_steps", "medicines.items", "return_precautions", "questions")
_ARRAY_ITEM_RE = re.compile(r"^(.+)\[(\d+)\]$")
_NON_SUPPORTED = ("needs_correction", "unsupported")


class SettleError(check_draft.CheckError):
    """Errors that reject a verification (the verifier may retry once)."""


# --- paths ----------------------------------------------------------------

def _kind(item_path: str) -> str:
    return item_path.split("[", 1)[0]


def split_path(path: str, item_paths) -> tuple[str, str | None] | None:
    """Split an operation path into (visible item path, text field or None)."""
    if not isinstance(path, str):
        return None
    if path in item_paths:
        return path, None
    if "." in path:
        item_path, field = path.rsplit(".", 1)
        if item_path in item_paths:
            return item_path, field
    return None


def _locate(plan: dict, item_path: str):
    """Return (container, key) such that container[key] is the item."""
    match = _ARRAY_ITEM_RE.match(item_path)
    if match:
        parent, index = match.group(1), int(match.group(2))
        container = plan["medicines"]["items"] if parent == "medicines.items" else plan[parent]
        return container, index
    if item_path == "medicines.none_statement":
        return plan["medicines"], "none_statement"
    return plan, item_path


def apply_operations(draft: dict, operations: list[dict]) -> dict:
    """Return a deep copy of `draft` with each validated operation applied.

    `replace` sets the field and replaces the item's `unit_ids`; `clear` sets
    an optional item to null or `plain_name` to ""; removals are grouped per
    array and applied from the highest index down so paths stay valid.
    """
    item_paths = {path for path, _item in plan_paths.visible_items(draft)}
    settled = copy.deepcopy(draft)
    removals: dict[str, list[int]] = {}
    for operation in operations:
        item_path, field = split_path(operation["path"], item_paths)
        container, key = _locate(settled, item_path)
        if operation["op"] == "replace":
            container[key][field] = operation["value"]
            container[key]["unit_ids"] = list(operation["unit_ids"])
        elif operation["op"] == "clear":
            if field is None:
                container[key] = None
            else:
                container[key][field] = ""
        else:
            match = _ARRAY_ITEM_RE.match(item_path)
            removals.setdefault(match.group(1), []).append(int(match.group(2)))
    for parent, indices in removals.items():
        container, _index = _locate(settled, f"{parent}[0]")
        for index in sorted(set(indices), reverse=True):
            del container[index]
    return settled


def map_path(path: str, removed: dict[str, set[int]]) -> str | None:
    """Map a draft item or field path to its settled path, or None if removed."""
    match = re.match(r"^(.+?)\[(\d+)\](.*)$", path)
    if not match:
        return path
    parent, index, rest = match.group(1), int(match.group(2)), match.group(3)
    gone = removed.get(parent, set())
    if index in gone:
        return None
    return f"{parent}[{index - sum(1 for other in gone if other < index)}]{rest}"


def _removed_indices(operations: list[dict]) -> dict[str, set[int]]:
    removed: dict[str, set[int]] = {}
    for operation in operations:
        if operation["op"] == "remove":
            match = _ARRAY_ITEM_RE.match(operation["path"])
            removed.setdefault(match.group(1), set()).add(int(match.group(2)))
    return removed


# --- contract ---------------------------------------------------------------

def _claim_errors(claims: list[dict], item_paths: list[str], touched: dict) -> list[str]:
    errors = []
    counts = Counter(claim["path"] for claim in claims)
    for path in counts:
        if path not in item_paths:
            errors.append(
                f"claim for {path!r}, which is not a visible item path in the draft "
                "(use item paths such as findings[0], why_you_went, medicines.none_statement)"
            )
    for path in item_paths:
        if counts[path] == 0:
            errors.append(f"{path} has no claim; every visible item needs exactly one")
        elif counts[path] > 1:
            errors.append(f"{path} has {counts[path]} claims; every visible item needs exactly one")
    for claim in claims:
        if claim["result"] in _NON_SUPPORTED and claim["path"] in item_paths and claim["path"] not in touched:
            errors.append(
                f"{claim['path']} is {claim['result']!r} but no operation replaces, clears, or removes it"
            )
    return errors


def _operation_errors(draft: dict, operations: list[dict], units_by_id: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    item_map = dict(plan_paths.visible_items(draft))
    touched: dict[str, list[tuple[dict, str | None]]] = {}
    path_counts = Counter(operation["path"] for operation in operations)
    for path, count in path_counts.items():
        if count > 1:
            errors.append(f"{count} operations target {path}; use one operation per path")
    for index, operation in enumerate(operations):
        op, path = operation["op"], operation["path"]
        label = f"operations[{index}] ({op} {path})"
        split = split_path(path, item_map)
        if split is None:
            errors.append(f"{label} targets a path that is not a visible item or text field of the draft")
            continue
        item_path, field = split
        item = item_map[item_path]
        kind = _kind(item_path)
        if op == "replace":
            if field is None or field not in plan_paths.TEXT_FIELDS.get(kind, ()):
                fields = ", ".join(f"{item_path}.{name}" for name in plan_paths.TEXT_FIELDS.get(kind, ()))
                errors.append(f"{label} must target a visible text field ({fields})")
                continue
            errors.extend(check_draft._unit_id_errors(label, operation["unit_ids"], units_by_id))
            if item.get(field) == operation["value"] and sorted(item.get("unit_ids") or []) == sorted(operation["unit_ids"]):
                errors.append(f"{label} changes neither the text nor the citations")
        elif op == "clear":
            item_clear = field is None and item_path in plan_paths.CLEARABLE_ITEMS
            field_clear = field in plan_paths.CLEARABLE_FIELDS and kind == "diagnoses"
            if not (item_clear or field_clear):
                errors.append(
                    f"{label}: clear is only allowed on findings_lead, disposition, "
                    "medicines.none_statement, or diagnoses[i].plain_name"
                )
                continue
            if field_clear and not (item.get(field) or "").strip():
                errors.append(f"{label} clears a field that is already empty")
        else:
            if field is not None or kind not in ARRAY_KINDS:
                errors.append(f"{label}: remove must target a whole array item such as findings[2]")
                continue
        touched.setdefault(item_path, []).append((operation, field))
    for item_path, entries in touched.items():
        whole_item = [op for op, field in entries if field is None]
        if whole_item and len(entries) > 1:
            errors.append(f"{item_path} is removed or cleared and also edited; use one operation")
        replace_citations = {
            tuple(sorted(op["unit_ids"])) for op, _field in entries if op["op"] == "replace"
        }
        if len(replace_citations) > 1:
            errors.append(f"replacements on {item_path} give different unit_ids; the item has one citation list")
    return errors, touched


def _numeric_errors(check: dict, resolutions: list[dict], operations: list[dict]) -> list[str]:
    errors = []
    flags = {flag["flag_id"]: flag for flag in check["numeric_flags"]}
    ops_by_path = {operation["path"]: operation for operation in operations}
    counts = Counter(resolution["flag_id"] for resolution in resolutions)
    for flag_id in counts:
        if flag_id not in flags:
            errors.append(f"numeric resolution for unknown flag {flag_id!r}")
    for flag_id in flags:
        if counts[flag_id] == 0:
            errors.append(f"numeric flag {flag_id} ({flags[flag_id]['token']!r} at {flags[flag_id]['path']}) is unresolved")
        elif counts[flag_id] > 1:
            errors.append(f"numeric flag {flag_id} is resolved more than once")
    for resolution in resolutions:
        flag = flags.get(resolution["flag_id"])
        if flag is None:
            continue
        path, kind = flag["path"], resolution["resolution"]
        correction_path = resolution.get("correction_path")
        label = f"numeric flag {flag['flag_id']} ({kind})"
        if kind == "equivalent":
            for operation in operations:
                if operation["path"] == path or (
                    operation["op"] in ("remove", "clear") and path.startswith(operation["path"] + ".")
                ):
                    errors.append(
                        f"{label} contradicts {operation['op']} {operation['path']}; "
                        "use 'corrected' or 'removed' instead"
                    )
        elif kind == "corrected":
            operation = ops_by_path.get(correction_path)
            if correction_path != path or operation is None or operation["op"] != "replace":
                errors.append(f"{label} must set correction_path to {path} and replace that field")
        else:
            operation = ops_by_path.get(correction_path)
            deletes = operation is not None and (
                (operation["op"] in ("remove", "clear")
                 and (path == correction_path or path.startswith(f"{correction_path}.")))
                or (operation["op"] == "replace" and correction_path == path)
            )
            if not deletes:
                errors.append(
                    f"{label} must set correction_path to the remove or clear operation that deletes "
                    f"{path}, or to a replace of {path} that drops the number"
                )
    return errors


def _protected_errors(check: dict, protected_units: list[dict]) -> tuple[list[str], list[dict]]:
    errors: list[str] = []
    missing: list[dict] = []
    uncited = {entry["unit_id"]: entry["categories"] for entry in check["uncited_protected"]}
    counts = Counter(entry["unit_id"] for entry in protected_units)
    for unit_id in counts:
        if unit_id not in uncited:
            errors.append(f"protected unit {unit_id} is not an uncited protected candidate in the check file")
    for unit_id in uncited:
        if counts[unit_id] == 0:
            errors.append(f"uncited protected unit {unit_id} ({', '.join(uncited[unit_id])}) is unresolved")
        elif counts[unit_id] > 1:
            errors.append(f"protected unit {unit_id} is resolved more than once")
    for entry in protected_units:
        unit_id = entry["unit_id"]
        if unit_id not in uncited:
            continue
        if entry["result"] == "not_needed" and "reason" not in entry:
            errors.append(f"protected unit {unit_id} is 'not_needed' without a reason")
        if entry["result"] == "missing":
            category = entry.get("category")
            if category is not None and category not in uncited[unit_id]:
                errors.append(
                    f"protected unit {unit_id} is missing as {category!r}, but it is a candidate for "
                    f"{', '.join(uncited[unit_id])}"
                )
                continue
            for name in [category] if category else uncited[unit_id]:
                missing.append({"unit_id": unit_id, "category": name})
    return errors, missing


def settled_errors(
    settled: dict,
    units_by_id: dict,
    accepted: list[dict],
    *,
    required_units: list[int] = (),
) -> list[str]:
    """Assertions every settled plan must pass (shared with finalize.py)."""
    errors = check_draft.schema_errors(settled, "draft_checked", "settled plan")
    if errors:
        return errors
    errors.extend(check_draft.citation_errors(settled, units_by_id))
    errors.extend(
        f"after the operations, {error}" for error in check_draft.coverage_errors(settled, units_by_id)
    )
    errors.extend(check_draft.text_errors(settled))
    errors.extend(check_draft.budget_errors(settled))
    allowed = {(entry["path"], entry["token"]) for entry in accepted}
    for path, token, _unit_ids in check_draft.unbacked_numbers(settled, units_by_id):
        if (path, token) not in allowed:
            errors.append(
                f"settled {path} contains {token!r}, which is not in its cited units and was not "
                "resolved 'equivalent'"
            )
    cited = plan_paths.cited_unit_ids(settled)
    for unit_id in required_units:
        if unit_id not in cited:
            errors.append(f"unit {unit_id} was reported missing in round 1 and is no longer cited")
    return errors


def settle_documents(
    draft: dict,
    check: dict,
    raw_verify: dict,
    units_by_id: dict,
    *,
    required_units: list[int] = (),
) -> tuple[dict, list[dict], list[dict]]:
    """Validate the verification and return (settled plan, missing, accepted_numeric).

    Raises SettleError with every contract error.
    """
    errors = check_draft.schema_errors(raw_verify, "verify_raw", "schema")
    if errors:
        raise SettleError(errors)
    item_paths = [path for path, _item in plan_paths.visible_items(draft)]
    operations = raw_verify["operations"]
    op_errors, touched = _operation_errors(draft, operations, units_by_id)
    errors.extend(_claim_errors(raw_verify["claims"], item_paths, touched))
    errors.extend(op_errors)
    errors.extend(_numeric_errors(check, raw_verify["numeric_resolutions"], operations))
    protected_errors, missing = _protected_errors(check, raw_verify["protected_units"])
    errors.extend(protected_errors)
    if errors:
        raise SettleError(errors)

    settled = apply_operations(draft, operations)
    removed = _removed_indices(operations)
    flags = {flag["flag_id"]: flag for flag in check["numeric_flags"]}
    accepted = []
    for resolution in raw_verify["numeric_resolutions"]:
        if resolution["resolution"] == "equivalent":
            flag = flags[resolution["flag_id"]]
            settled_path = map_path(flag["path"], removed)
            if settled_path is not None:
                accepted.append({"path": settled_path, "token": flag["token"]})
    errors = settled_errors(settled, units_by_id, accepted, required_units=required_units)
    if errors:
        raise SettleError(errors)
    return settled, missing, accepted


def build_record(
    run_id: str,
    round_no: int,
    raw_verify: dict,
    missing: list[dict],
    accepted: list[dict],
    *,
    words_before: int,
    words_after: int,
) -> dict:
    results = Counter(claim["result"] for claim in raw_verify["claims"])
    if not missing:
        outcome = "settled"
    else:
        outcome = "repair_requested" if round_no == 1 else "missing_after_repair"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "round": round_no,
        "outcome": outcome,
        "claims": copy.deepcopy(raw_verify["claims"]),
        "operations": copy.deepcopy(raw_verify["operations"]),
        "numeric_resolutions": copy.deepcopy(raw_verify["numeric_resolutions"]),
        "protected_units": copy.deepcopy(raw_verify["protected_units"]),
        "accepted_numeric": accepted,
        "missing": missing,
        "counts": {
            "claims": len(raw_verify["claims"]),
            "supported": results["supported"],
            "needs_correction": results["needs_correction"],
            "unsupported": results["unsupported"],
            "operations": len(raw_verify["operations"]),
            "numeric_flags": len(raw_verify["numeric_resolutions"]),
            "protected_units": len(raw_verify["protected_units"]),
            "missing": len(missing),
            "word_count_before": words_before,
            "word_count_after": words_after,
        },
    }


# --- CLI ----------------------------------------------------------------------

def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"  {error}", file=sys.stderr)


def _workflow_failure(run_dir: str, run_id: str | None, round_no: int, errors: list[str]) -> int:
    if run_id:
        try:
            runlog.record(run_dir, "settle", "failed", checks={"round": round_no, "errors": errors}, run_id=run_id)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    print(f"settle: failed | round={round_no} workflow_error errors={len(errors)}")
    print("settle: the run inputs are missing or invalid; this is not a verification problem.", file=sys.stderr)
    _print_errors(errors)
    return EXIT_FAILED


def _contract_failure(run_dir: str, run_id: str, round_no: int, names: dict, errors: list[str]) -> int:
    raw_path = os.path.join(run_dir, names["verify_raw"])
    attempt_path = os.path.join(run_dir, names["verify_raw_attempt"])
    attempt = 2 if os.path.exists(attempt_path) else 1
    retry_allowed = attempt == 1
    if retry_allowed:
        os.replace(raw_path, attempt_path)
        artifact = names["verify_raw_attempt"]
    else:
        artifact = names["verify_raw"]
    checks = {
        "round": round_no, "attempt": attempt, "retry_allowed": retry_allowed,
        "terminal": not retry_allowed, "errors": errors,
    }
    runlog.record(run_dir, "verify", "failed", checks=checks, artifacts=[artifact], run_id=run_id)
    runlog.record(run_dir, "settle", "failed", checks=checks, run_id=run_id)
    if retry_allowed:
        print(f"settle: failed | round={round_no} attempt=1 errors={len(errors)} retry=allowed")
        print(
            f"settle: the verification was moved to {names['verify_raw_attempt']}. Retry VERIFY once: fix "
            f"every error below and write a new {names['verify_raw']}.",
            file=sys.stderr,
        )
    else:
        print(f"settle: failed | round={round_no} attempt={attempt} errors={len(errors)} retry=exhausted")
        print(
            "settle: the VERIFY retry also failed. Stop the run and do not show any clinical content.",
            file=sys.stderr,
        )
    _print_errors(errors)
    return EXIT_FAILED


def _load_inputs(run_dir: str, round_no: int, names: dict):
    run_id, units_by_id, protected_categories = check_draft.load_source(run_dir)
    terminal = check_draft.terminal_errors(runlog.read(run_dir))
    if terminal:
        raise check_draft.CheckError(terminal)
    errors = []
    documents = {}
    for key, schema_name in (("draft", "draft_checked"), ("check", "check")):
        name = names[key]
        try:
            document = check_draft.read_json(os.path.join(run_dir, name))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"cannot read {name}: {error}; run check_draft.py first")
            continue
        errors.extend(check_draft.schema_errors(document, schema_name, name))
        if isinstance(document, dict) and document.get("run_id") != run_id:
            errors.append(f"{name} does not belong to the current run")
        documents[key] = document
    if errors:
        raise check_draft.CheckError(errors)
    draft, check = documents["draft"], documents["check"]
    if check["round"] != round_no:
        raise check_draft.CheckError(f"{names['check']} is for round {check['round']}, not round {round_no}")
    stage = (runlog.read(run_dir).get("stages") or {}).get("check") or {}
    if stage.get("status") != "ok" or (stage.get("checks") or {}).get("round") != round_no:
        raise check_draft.CheckError(f"the check stage has not passed for round {round_no}")
    expected = check_draft.build_check(draft, units_by_id, protected_categories, run_id=run_id, round_no=round_no)
    if expected != check:
        raise check_draft.CheckError(f"{names['check']} does not match {names['draft']}; rerun check_draft.py")
    required_units: list[int] = []
    if round_no == 2:
        repair = check_draft.load_repair(run_dir, run_id)
        required_units = sorted({entry["unit_id"] for entry in repair["missing"]})
    return run_id, units_by_id, draft, check, required_units


def run(run_dir: str, round_no: int = 1) -> int:
    names = check_draft.artifact_names(round_no)
    stale = [names["verify"], check_draft.SETTLED_NAME]
    if round_no == 1:
        stale.append(check_draft.REPAIR_NAME)
    for name in stale:
        check_draft.remove_quietly(os.path.join(run_dir, name))

    try:
        run_id, units_by_id, draft, check, required_units = _load_inputs(run_dir, round_no, names)
    except check_draft.CheckError as error:
        return _workflow_failure(run_dir, runlog.read(run_dir).get("run_id"), round_no, error.errors)

    raw_path = os.path.join(run_dir, names["verify_raw"])
    if not os.path.isfile(raw_path):
        return _workflow_failure(
            run_dir, run_id, round_no, [f"{names['verify_raw']} is missing; run the VERIFY stage first"],
        )
    try:
        raw_verify = check_draft.read_json(raw_path)
    except (OSError, json.JSONDecodeError) as error:
        return _contract_failure(
            run_dir, run_id, round_no, names, [f"{names['verify_raw']} is not valid JSON: {error}"],
        )
    try:
        settled, missing, accepted = settle_documents(
            draft, check, raw_verify, units_by_id, required_units=required_units,
        )
    except SettleError as error:
        return _contract_failure(run_dir, run_id, round_no, names, error.errors)

    record = build_record(
        run_id, round_no, raw_verify, missing, accepted,
        words_before=check["word_count"], words_after=check_draft.word_count(settled),
    )
    internal = check_draft.schema_errors(record, "verify", names["verify"])
    if internal:
        return _workflow_failure(run_dir, run_id, round_no, ["internal error in settle.py:"] + internal)
    check_draft.atomic_write_json(os.path.join(run_dir, names["verify"]), record)
    attempt = 2 if os.path.exists(os.path.join(run_dir, names["verify_raw_attempt"])) else 1
    runlog.record(
        run_dir, "verify", "ok",
        checks={"round": round_no, "attempt": attempt, "retry_allowed": False, "errors": []},
        artifacts=[names["verify_raw"], names["verify"]], run_id=run_id,
    )
    checks = {
        "round": round_no,
        "errors": [],
        "operations_applied": record["counts"]["operations"],
        "missing": len(missing),
        "word_count": record["counts"]["word_count_after"],
    }

    if missing and round_no == 1:
        repair = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "missing": missing,
            "settled_draft": settled,
        }
        check_draft.atomic_write_json(os.path.join(run_dir, check_draft.REPAIR_NAME), repair)
        runlog.record(
            run_dir, "settle", "repair_requested", checks=checks,
            artifacts=[check_draft.REPAIR_NAME], run_id=run_id,
        )
        print(f"settle: repair requested | round=1 missing={len(missing)}")
        print(
            f"settle: run the repair round: WRITE with {check_draft.REPAIR_NAME}, then "
            "check_draft.py, VERIFY, and settle.py with --round 2.",
            file=sys.stderr,
        )
        return EXIT_REPAIR
    if missing:
        checks["terminal"] = True
        checks["errors"] = [
            f"unit {entry['unit_id']} ({entry['category']}) is still missing after the repair round"
            for entry in missing
        ]
        runlog.record(run_dir, "settle", "failed", checks=checks, run_id=run_id)
        print(f"settle: failed | round=2 missing={len(missing)} retry=exhausted")
        print(
            "settle: protected content is still missing after the repair round. Stop the run and do not "
            "show any clinical content.",
            file=sys.stderr,
        )
        _print_errors(checks["errors"])
        return EXIT_FAILED

    check_draft.atomic_write_json(os.path.join(run_dir, check_draft.SETTLED_NAME), settled)
    runlog.record(
        run_dir, "settle", "ok", checks=checks,
        artifacts=[check_draft.SETTLED_NAME], run_id=run_id,
    )
    print(
        f"settle: ok | round={round_no} claims={record['counts']['claims']} "
        f"operations={record['counts']['operations']} words={record['counts']['word_count_after']}"
    )
    return EXIT_OK


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the verification and apply its bounded edits.")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument("--round", type=int, choices=(1, 2), default=1, help="1, or 2 for the repair round")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return run(args.run_dir, args.round)


if __name__ == "__main__":
    sys.exit(main())
