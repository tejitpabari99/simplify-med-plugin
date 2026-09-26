#!/usr/bin/env python3
"""Validate one independent review and apply its bounded operations exactly."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cite_check  # noqa: E402
import numeric_parity  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402


_PATH_SEGMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")
_FINAL_INDEX_RE = re.compile(r"^(.*)\[(\d+)\]$")
_PROTECTED_ROOTS = {
    "schema_version", "plugin_version", "meta", "notices", "score", "omitted_facts",
}
_PROTECTED_KEYS = {
    "source_fact_ids", "summary_fact_ids", "changed_since_last_visit_fact_ids",
}
_NULLABLE_FIELDS = {"why", "severity", "urgency"}
_VISIBLE_RESULTS = {"visible_accurate", "visible_needs_correction"}


class SettlementError(ValueError):
    """Raised when review settlement cannot safely produce a patient plan."""

    def __init__(self, errors: str | list[str]):
        self.errors = [errors] if isinstance(errors, str) else errors
        super().__init__("; ".join(self.errors))


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write_json(path: str, document: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    descriptor, temporary_path = tempfile.mkstemp(prefix=".settle.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def _parse_path(path: str) -> list[tuple[str, int | None]]:
    if not isinstance(path, str) or not path:
        raise SettlementError("operation path must be a non-empty string")
    segments = path.split(".")
    parsed: list[tuple[str, int | None]] = []
    for segment in segments:
        match = _PATH_SEGMENT_RE.fullmatch(segment)
        if match is None:
            raise SettlementError(f"invalid operation path syntax: {path}")
        name, index = match.groups()
        parsed.append((name, int(index) if index is not None else None))
    return parsed


def _flat_tokens(path: str) -> tuple[tuple[str, object], ...]:
    tokens: list[tuple[str, object]] = []
    for name, index in _parse_path(path):
        tokens.append(("key", name))
        if index is not None:
            tokens.append(("index", index))
    return tuple(tokens)


def resolve_path(document: dict, path: str):
    """Return ``(found, value)`` for a strict dotted/indexed path."""
    try:
        segments = _parse_path(path)
    except SettlementError:
        return False, None
    value = document
    for name, index in segments:
        if not isinstance(value, dict) or name not in value:
            return False, None
        value = value[name]
        if index is not None:
            if not isinstance(value, list) or index >= len(value):
                return False, None
            value = value[index]
    return True, value


def _is_protected_path(path: str) -> bool:
    segments = _parse_path(path)
    return segments[0][0] in _PROTECTED_ROOTS or any(name in _PROTECTED_KEYS for name, _ in segments)


def _path_is_parent(parent_path: str, child_path: str) -> bool:
    parent = _flat_tokens(parent_path)
    child = _flat_tokens(child_path)
    return len(parent) < len(child) and child[:len(parent)] == parent


def _set_scalar(document: dict, path: str, value) -> None:
    segments = _parse_path(path)
    node = document
    for name, index in segments[:-1]:
        node = node[name]
        if index is not None:
            node = node[index]
    name, index = segments[-1]
    if index is None:
        node[name] = value
    else:
        node[name][index] = value


def _visible_and_omitted_fact_ids(plan: dict) -> tuple[set[int], set[int]]:
    visible: set[int] = set()

    def add(values) -> None:
        if isinstance(values, list):
            visible.update(value for value in values if isinstance(value, int))

    if isinstance(plan.get("summary"), str) and plan["summary"].strip():
        add(plan.get("summary_fact_ids"))
    diagnosis = plan.get("diagnosis", {})
    if isinstance(diagnosis, dict):
        if isinstance(diagnosis.get("changed_since_last_visit"), str) and diagnosis["changed_since_last_visit"].strip():
            add(diagnosis.get("changed_since_last_visit_fact_ids"))
        for detail in diagnosis.get("details", []):
            if isinstance(detail, dict):
                add(detail.get("source_fact_ids"))
    for section in cite_check.ITEM_LIST_FIELDS:
        for item in plan.get(section, []):
            if isinstance(item, dict):
                add(item.get("source_fact_ids"))
    for question in plan.get("questions", []):
        if isinstance(question, dict) and isinstance(question.get("question"), str) and question["question"].strip():
            add(question.get("source_fact_ids"))
    omitted = {
        item.get("fact_id") for item in plan.get("omitted_facts", [])
        if isinstance(item, dict) and isinstance(item.get("fact_id"), int)
    }
    return visible, omitted


def _path_citations(plan: dict, path: str) -> set[int]:
    segments = _parse_path(path)
    root = segments[0][0]
    if root == "summary":
        return set(plan.get("summary_fact_ids", []))
    if root == "diagnosis":
        if len(segments) > 1 and segments[1][0] == "changed_since_last_visit":
            return set(plan.get("diagnosis", {}).get("changed_since_last_visit_fact_ids", []))
        if len(segments) > 1 and segments[1][0] == "details" and segments[1][1] is not None:
            index = segments[1][1]
            details = plan.get("diagnosis", {}).get("details", [])
            if index < len(details):
                return set(details[index].get("source_fact_ids", []))
        return set()
    if root in cite_check.ITEM_LIST_FIELDS + ("questions",):
        index = segments[0][1]
        items = plan.get(root, [])
        if index is not None and index < len(items) and isinstance(items[index], dict):
            return set(items[index].get("source_fact_ids", []))
    return set()


def _validate_versions(run_id: str, draft: dict, facts: dict, flags: dict, raw_review: dict) -> list[str]:
    errors: list[str] = []
    documents = {
        "draft plan": draft,
        "fact ledger": facts,
        "numeric flags": flags,
        "raw review": raw_review,
    }
    for name, document in documents.items():
        if not isinstance(document, dict):
            errors.append(f"{name} must be a JSON object")
    if errors:
        return errors
    if draft.get("meta", {}).get("run_id") != run_id:
        errors.append("draft plan does not belong to the current run")
    for name, document in (("draft plan", draft), ("fact ledger", facts), ("numeric flags", flags)):
        if document.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{name} has the wrong schema version")
        if document.get("plugin_version") != PLUGIN_VERSION:
            errors.append(f"{name} has the wrong plugin version")
    for name, document in (("fact ledger", facts), ("numeric flags", flags)):
        if document.get("run_id") != run_id:
            errors.append(f"{name} does not belong to the current run")
    if draft.get("meta", {}).get("schema_version") != SCHEMA_VERSION:
        errors.append("draft metadata has the wrong schema version")
    if draft.get("meta", {}).get("plugin_version") != PLUGIN_VERSION:
        errors.append("draft metadata has the wrong plugin version")
    if "schema_version" in raw_review and raw_review["schema_version"] != SCHEMA_VERSION:
        errors.append("raw review has the wrong schema version")
    if "plugin_version" in raw_review and raw_review["plugin_version"] != PLUGIN_VERSION:
        errors.append("raw review has the wrong plugin version")
    return errors


def _schema_errors(document: dict, schema_name: str, label: str) -> list[str]:
    return [f"{label}: {error}" for error in validate.validate(document, validate.load_schema(schema_name))]


def _validate_review_contract(draft: dict, facts: dict, raw_review: dict) -> tuple[dict[int, str], set[int]]:
    errors: list[str] = []
    fact_ids = [fact.get("id") for fact in facts.get("facts", []) if isinstance(fact, dict)]
    expected = set(fact_ids)
    reviewed = raw_review.get("reviewed_fact_ids", [])
    if len(reviewed) != len(expected) or set(reviewed) != expected:
        errors.append("reviewed_fact_ids must exhaustively match the fact ledger")

    reviews = raw_review.get("fact_reviews", [])
    review_counts = Counter(
        item.get("fact_id") for item in reviews if isinstance(item, dict)
    )
    for fact_id in sorted(expected):
        count = review_counts.get(fact_id, 0)
        if count == 0:
            errors.append(f"fact {fact_id} has no fact review")
        elif count > 1:
            errors.append(f"fact {fact_id} is reviewed more than once")
    for fact_id in sorted(set(review_counts) - expected):
        errors.append(f"unknown fact {fact_id} is reviewed")
    results = {
        item["fact_id"]: item["result"] for item in reviews
        if isinstance(item, dict) and item.get("fact_id") in expected
    }

    visible, omitted = _visible_and_omitted_fact_ids(draft)
    for fact_id in sorted(visible):
        if results.get(fact_id) not in _VISIBLE_RESULTS:
            errors.append(f"visible fact {fact_id} must have a visible review result")
    for fact_id in sorted(omitted):
        if results.get(fact_id) not in {"omission_acceptable", "must_include"}:
            errors.append(f"omitted fact {fact_id} must have an omission review result")

    must_include = {fact_id for fact_id, result in results.items() if result == "must_include"}
    reassemble = raw_review.get("reassemble_fact_ids", [])
    if len(reassemble) != len(set(reassemble)) or set(reassemble) != must_include:
        errors.append("reassemble_fact_ids must exactly match must_include fact reviews")

    if errors:
        raise SettlementError(errors)
    return results, must_include


def _validate_operations(draft: dict, facts: dict, raw_review: dict, results: dict[int, str]) -> list[dict]:
    errors: list[str] = []
    operations = raw_review.get("corrections", [])
    paths: list[str] = []
    facts_by_id = {fact["id"] for fact in facts.get("facts", []) if isinstance(fact, dict)}
    touched_needs: set[int] = set()

    for operation in operations:
        path = operation.get("path") if isinstance(operation, dict) else None
        try:
            _parse_path(path)
        except SettlementError as error:
            errors.extend(error.errors)
            continue
        paths.append(path)
        if _is_protected_path(path):
            errors.append(f"operation targets protected path {path}")
            continue
        found, current = resolve_path(draft, path)
        if not found:
            errors.append(f"operation targets unknown path {path}")
            continue

        op = operation.get("op")
        path_citations = _path_citations(draft, path)
        affected_facts = set(path_citations)
        if op == "replace":
            if not isinstance(current, str) and current is not None:
                errors.append(f"replace requires an existing string or nullable field at {path}")
            if operation.get("value") == current:
                errors.append(f"replace is a no-op at {path}")
            source_fact_ids = operation.get("source_fact_ids", [])
            affected_facts = set(source_fact_ids)
            if not affected_facts or not affected_facts.issubset(facts_by_id):
                errors.append(f"replace at {path} has invalid source fact IDs")
            if not affected_facts.issubset(path_citations):
                errors.append(f"replace at {path} cites facts outside the path citations")
        elif op == "clear":
            if not isinstance(current, str) and current is not None:
                errors.append(f"clear requires an existing string or nullable field at {path}")
            if current in {None, ""}:
                errors.append(f"clear is a no-op at {path}")
        elif op == "remove":
            if _FINAL_INDEX_RE.fullmatch(path) is None:
                errors.append(f"remove requires an exact array item path at {path}")
        else:
            errors.append(f"unsupported operation {op!r} at {path}")

        needs_here = {fact_id for fact_id in affected_facts if results.get(fact_id) == "visible_needs_correction"}
        if not needs_here:
            errors.append(f"operation at {path} is not tied to a visible_needs_correction fact")
        touched_needs.update(needs_here)

    for path, count in Counter(paths).items():
        if count > 1:
            errors.append(f"operation path {path} is applied more than once")
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            if _path_is_parent(path, other) or _path_is_parent(other, path):
                errors.append(f"operations conflict at parent and child paths {path} and {other}")

    expected_needs = {fact_id for fact_id, result in results.items() if result == "visible_needs_correction"}
    for fact_id in sorted(expected_needs - touched_needs):
        errors.append(f"visible_needs_correction fact {fact_id} has no bounded operation")

    if errors:
        raise SettlementError(errors)
    return operations


def apply_operations(draft: dict, operations: list[dict]) -> dict:
    """Return a deep copy with each validated operation applied exactly once."""
    settled = copy.deepcopy(draft)
    removals: list[dict] = []
    for operation in operations:
        op = operation["op"]
        path = operation["path"]
        if op == "remove":
            removals.append(operation)
        elif op == "replace":
            _set_scalar(settled, path, copy.deepcopy(operation["value"]))
        else:
            field_name = _parse_path(path)[-1][0]
            _set_scalar(settled, path, None if field_name in _NULLABLE_FIELDS else "")

    grouped: dict[str, list[int]] = {}
    for operation in removals:
        match = _FINAL_INDEX_RE.fullmatch(operation["path"])
        if match is None:
            raise SettlementError(f"remove requires an array item path: {operation['path']}")
        parent_path, index = match.groups()
        grouped.setdefault(parent_path, []).append(int(index))
    for parent_path in sorted(grouped, key=lambda value: len(_flat_tokens(value)), reverse=True):
        found, array = resolve_path(settled, parent_path)
        if not found or not isinstance(array, list):
            raise SettlementError(f"remove parent is not an array: {parent_path}")
        for index in sorted(grouped[parent_path], reverse=True):
            if index >= len(array):
                raise SettlementError(f"remove index shifted out of range: {parent_path}[{index}]")
            del array[index]
    return settled


def _build_review_document(run_id: str, raw_review: dict) -> dict:
    result_counts = Counter(item["result"] for item in raw_review["fact_reviews"])
    reassemble = raw_review["reassemble_fact_ids"]
    corrections = raw_review["corrections"]
    verdict = "needs_reassembly" if reassemble else "needs_correction" if corrections else "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "reviewed_fact_ids": copy.deepcopy(raw_review["reviewed_fact_ids"]),
        "fact_reviews": copy.deepcopy(raw_review["fact_reviews"]),
        "corrections": copy.deepcopy(corrections),
        "numeric_resolutions": copy.deepcopy(raw_review["numeric_resolutions"]),
        "reassemble_fact_ids": copy.deepcopy(reassemble),
        "dropped_operations": [],
        "counts": {
            "facts_reviewed": len(raw_review["reviewed_fact_ids"]),
            "visible_accurate": result_counts["visible_accurate"],
            "visible_needs_correction": result_counts["visible_needs_correction"],
            "omission_acceptable": result_counts["omission_acceptable"],
            "must_include": result_counts["must_include"],
            "corrections": len(corrections),
            "numeric_resolutions": len(raw_review["numeric_resolutions"]),
            "dropped_operations": 0,
            "reassemble_facts": len(reassemble),
        },
        "verdict": verdict,
    }


def settle_documents(
    draft: dict,
    facts: dict,
    flags: dict,
    raw_review: dict,
    *,
    run_id: str,
) -> tuple[dict, dict]:
    errors = []
    errors.extend(_schema_errors(draft, "care_plan", "draft plan"))
    errors.extend(_schema_errors(facts, "facts", "fact ledger"))
    errors.extend(_schema_errors(flags, "flags", "numeric flags"))
    errors.extend(_schema_errors(raw_review, "review_raw", "raw review"))
    errors.extend(_validate_versions(run_id, draft, facts, flags, raw_review))
    if errors:
        raise SettlementError(errors)

    try:
        cite_check.assert_plan_citations(draft, facts)
    except cite_check.PlanCitationError as error:
        raise SettlementError([f"draft citation/disposition: {item}" for item in error.errors]) from error

    results, must_include = _validate_review_contract(draft, facts, raw_review)
    review = _build_review_document(run_id, raw_review)
    review_schema_errors = _schema_errors(review, "review", "review")
    if review_schema_errors:
        raise SettlementError(review_schema_errors)
    if must_include:
        raise SettlementError(
            f"review requests reassembly for fact IDs {sorted(must_include)}"
        )

    operations = _validate_operations(draft, facts, raw_review, results)
    settled = apply_operations(draft, operations)
    plan_schema_errors = _schema_errors(settled, "care_plan", "settled plan")
    if plan_schema_errors:
        raise SettlementError(plan_schema_errors)
    try:
        citation_checks = cite_check.assert_plan_citations(settled, facts)
    except cite_check.PlanCitationError as error:
        raise SettlementError([f"settled citation/disposition: {item}" for item in error.errors]) from error
    try:
        numeric_checks = numeric_parity.assert_post_settlement_numeric(
            draft, settled, facts, flags, review,
        )
    except numeric_parity.NumericParityError as error:
        raise SettlementError([f"settled numeric parity: {item}" for item in error.errors]) from error

    review["counts"]["facts_reviewed"] = citation_checks["facts_total"]
    if numeric_checks["numeric_resolutions"] != review["counts"]["numeric_resolutions"]:
        raise SettlementError("numeric resolution count changed during settlement")
    return review, settled


def _remove_outputs(run_dir: str) -> None:
    for name in ("04_review.json", "05_plan.settled.json"):
        try:
            os.remove(os.path.join(run_dir, name))
        except FileNotFoundError:
            pass


def _record_failure(run_dir: str, stage: str, errors: list[str]) -> None:
    runlog.record(
        run_dir,
        stage,
        "failed",
        checks={"errors": errors},
        run_id=os.path.basename(os.path.normpath(run_dir)),
    )


def _run(run_dir: str) -> int:
    run_id = os.path.basename(os.path.normpath(run_dir))
    _remove_outputs(run_dir)
    required = {
        "draft": "03_plan.draft.json",
        "facts": "02_facts.json",
        "flags": "03_flags.json",
        "raw_review": "04_review.raw.json",
    }
    documents: dict[str, dict] = {}
    try:
        for key, name in required.items():
            documents[key] = _read_json(os.path.join(run_dir, name))
    except (OSError, json.JSONDecodeError) as error:
        errors = [f"cannot read required settlement input: {error}"]
        _record_failure(run_dir, "review", errors)
        for item in errors:
            print(item)
        return 1

    raw_review = documents["raw_review"]
    try:
        schema_errors = _schema_errors(raw_review, "review_raw", "raw review")
        version_errors = _validate_versions(
            run_id, documents["draft"], documents["facts"], documents["flags"], raw_review,
        )
        if schema_errors or version_errors:
            raise SettlementError(schema_errors + version_errors)
        cite_check.assert_plan_citations(documents["draft"], documents["facts"])
        results, must_include = _validate_review_contract(
            documents["draft"], documents["facts"], raw_review,
        )
        review = _build_review_document(run_id, raw_review)
        review_errors = _schema_errors(review, "review", "review")
        if review_errors:
            raise SettlementError(review_errors)
    except (SettlementError, cite_check.PlanCitationError) as error:
        errors = error.errors
        _record_failure(run_dir, "review", errors)
        for item in errors:
            print(item)
        return 1

    if must_include:
        errors = [f"review requests reassembly for fact IDs {sorted(must_include)}"]
        runlog.record(
            run_dir,
            "review",
            "ok",
            checks=review["counts"],
            run_id=run_id,
        )
        _record_failure(run_dir, "settle_review", errors)
        for item in errors:
            print(item)
        return 1

    try:
        operations = _validate_operations(documents["draft"], documents["facts"], raw_review, results)
        settled = apply_operations(documents["draft"], operations)
        errors = []
        errors.extend(_schema_errors(documents["draft"], "care_plan", "draft plan"))
        errors.extend(_schema_errors(documents["facts"], "facts", "fact ledger"))
        errors.extend(_schema_errors(documents["flags"], "flags", "numeric flags"))
        errors.extend(_schema_errors(settled, "care_plan", "settled plan"))
        if errors:
            raise SettlementError(errors)
        try:
            citation_checks = cite_check.assert_plan_citations(settled, documents["facts"])
        except cite_check.PlanCitationError as error:
            raise SettlementError([f"settled citation/disposition: {item}" for item in error.errors]) from error
        try:
            numeric_checks = numeric_parity.assert_post_settlement_numeric(
                documents["draft"], settled, documents["facts"], documents["flags"], review,
            )
        except numeric_parity.NumericParityError as error:
            raise SettlementError([f"settled numeric parity: {item}" for item in error.errors]) from error
        review["counts"]["facts_reviewed"] = citation_checks["facts_total"]
        if numeric_checks["numeric_resolutions"] != review["counts"]["numeric_resolutions"]:
            raise SettlementError("numeric resolution count changed during settlement")
    except SettlementError as error:
        runlog.record(
            run_dir,
            "review",
            "ok",
            checks=review["counts"],
            run_id=run_id,
        )
        _record_failure(run_dir, "settle_review", error.errors)
        for item in error.errors:
            print(item)
        return 1

    review_path = os.path.join(run_dir, "04_review.json")
    settled_path = os.path.join(run_dir, "05_plan.settled.json")
    _atomic_write_json(review_path, review)
    _atomic_write_json(settled_path, settled)
    runlog.record(
        run_dir,
        "review",
        "ok",
        checks=review["counts"],
        artifacts=[{"path": "04_review.json"}],
        run_id=run_id,
    )
    runlog.record(
        run_dir,
        "settle_review",
        "ok",
        checks={
            "operations_applied": len(operations),
            "citation_checks": citation_checks,
            "numeric_checks": numeric_checks,
        },
        artifacts=[{"path": "05_plan.settled.json"}],
        run_id=run_id,
    )
    print(
        "settle_review: ok | "
        f"facts={review['counts']['facts_reviewed']} operations={len(operations)} "
        f"numeric_resolutions={review['counts']['numeric_resolutions']}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a combined review and deterministically settle its bounded operations",
    )
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return _run(args.run_dir)


if __name__ == "__main__":
    sys.exit(main())
