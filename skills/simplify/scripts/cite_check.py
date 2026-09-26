#!/usr/bin/env python3
"""Fail-closed citation and fact-disposition validation for care plans."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import SCHEMA_VERSION  # noqa: E402


ITEM_LIST_FIELDS = (
    "reason_for_visit", "medications", "tests", "procedures", "other",
    "follow_up", "warning_signs",
)
OMISSION_REASONS = {
    "duplicate_or_already_represented", "technical_detail",
    "routine_non_actionable", "rejected_non_actionable_differential",
    "generic_not_patient_specific", "stable_unchanged_background",
}

_GENERIC_PATTERNS = (
    re.compile(r"\b(?:all|most) (?:adults|patients|people)\b", re.IGNORECASE),
    re.compile(r"\b(?:general|generic|broad) (?:education|advice|guidance|information)\b", re.IGNORECASE),
    re.compile(r"\bhealthy (?:adults|people) should\b", re.IGNORECASE),
    re.compile(r"\beveryone should\b", re.IGNORECASE),
    re.compile(r"\beducation (?:sheet|handout|material)\b", re.IGNORECASE),
)
_BROAD_WELLNESS_PATTERN = re.compile(
    r"\b(?:exercise regularly|regular exercise|healthy diet|eat (?:a )?healthy|"
    r"balanced diet|drink (?:more |plenty of )?water|good sleep|sleep hygiene|"
    r"healthy lifestyle|wellness advice)\b",
    re.IGNORECASE,
)
_WELLNESS_TOPIC_PATTERN = re.compile(
    r"\b(?:exercise|physical activity|walking|healthy diet|balanced diet|hydration|sleep)\b",
    re.IGNORECASE,
)
_QUANTIFIED_WELLNESS_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s+(?:minutes?|hours?|days?|servings?)\b|"
    r"\b(?:daily|weekly|each day|each week|per day|per week)\b)",
    re.IGNORECASE,
)
_PATIENT_SPECIFIC_PATTERN = re.compile(
    r"\b(?:for (?:this|the) patient|the patient (?:was|has been) "
    r"(?:advised|instructed|told)|(?:clinician|doctor|provider) "
    r"(?:advised|instructed|recommended|told)|because of (?:your|the patient's)|"
    r"due to (?:your|the patient's)|to (?:manage|treat|address|lower|improve) your|"
    r"after your (?:result|diagnosis|visit)|patient-specific)\b",
    re.IGNORECASE,
)
_RESULT_SIGNAL_PATTERN = re.compile(
    r"\b(?:result|normal|negative|positive|found|showed|revealed|demonstrated|"
    r"no evidence|no [a-z][a-z-]+)\b",
    re.IGNORECASE,
)
_DISPOSITION_SIGNAL_PATTERN = re.compile(
    r"\b(?:discharged|admitted|sent home|cleared|reassur|decision|ruled out|"
    r"excluded|no treatment|no further|therefore|because|so)\b",
    re.IGNORECASE,
)
_MEANINGFUL_RESULT_PATTERN = re.compile(
    r"\b(?:abnormal|positive|elevated|worsened|improved|mass|fracture|infection)\b",
    re.IGNORECASE,
)
_TECHNICAL_PATTERN = re.compile(
    r"\b(?:technical|contrast|slice thickness|sequence|protocol|device detail|imaging technique)\b",
    re.IGNORECASE,
)
_ROUTINE_PATTERN = re.compile(
    r"\b(?:routine|normal|incidental|non-actionable|no action|completed)\b",
    re.IGNORECASE,
)
_DIFFERENTIAL_PATTERN = re.compile(
    r"\b(?:rejected|ruled out|unlikely|not consistent with|differential)\b",
    re.IGNORECASE,
)
_STABLE_PATTERN = re.compile(
    r"\b(?:stable|unchanged|background history|continue unchanged|home medication)\b",
    re.IGNORECASE,
)


class PlanCitationError(ValueError):
    """Raised when a plan is not exhaustively and validly fact-backed."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)
        handle.write("\n")


def _run_id(run_dir: str) -> str:
    return os.path.basename(os.path.normpath(run_dir))


def _fact_list(facts: dict | list[dict]) -> list[dict]:
    value = facts.get("facts", []) if isinstance(facts, dict) else facts
    return value if isinstance(value, list) else []


def _fact_text(fact: dict) -> str:
    return f"{fact.get('text', '')} {fact.get('quote', '')}".strip()


def _is_generic_advice(fact: dict) -> bool:
    text = _fact_text(fact)
    if any(pattern.search(text) for pattern in _GENERIC_PATTERNS):
        return True
    broad_wellness = bool(_BROAD_WELLNESS_PATTERN.search(text)) or bool(
        _WELLNESS_TOPIC_PATTERN.search(text) and _QUANTIFIED_WELLNESS_PATTERN.search(text)
    )
    return broad_wellness and not bool(_PATIENT_SPECIFIC_PATTERN.search(text))


def _is_critical_fact(fact: dict) -> bool:
    category = fact.get("category")
    text = _fact_text(fact)
    if _is_generic_advice(fact):
        return False
    if category in {"reason_for_visit", "follow_up", "warning_signs"}:
        return True
    if category == "medications":
        if re.search(
            r"\b(?:start|begin|stop|discontinue|hold|increase|decrease|change|switch|"
            r"dose|dosage|frequency|timing|duration|take|use|mg|mcg|tablet|capsule)\b",
            text,
            re.IGNORECASE,
        ):
            return True
        return not bool(_STABLE_PATTERN.search(text))
    if category == "diagnosis":
        return not bool(_DIFFERENTIAL_PATTERN.search(text) or _STABLE_PATTERN.search(text))
    if category in {"tests", "procedures"}:
        pending_or_actionable = bool(re.search(
            r"\b(?:order|ordered|pending|schedule|scheduled|refer|follow up|unresolved)\b",
            text, re.IGNORECASE,
        ))
        result_explains_disposition = bool(
            _RESULT_SIGNAL_PATTERN.search(text) and _DISPOSITION_SIGNAL_PATTERN.search(text)
        )
        return pending_or_actionable or result_explains_disposition or bool(
            _MEANINGFUL_RESULT_PATTERN.search(text)
        )
    if category == "other":
        return bool(
            _PATIENT_SPECIFIC_PATTERN.search(text)
            or re.search(
                r"\b(?:avoid|do not|nothing by mouth|no driving|precaution|restriction|hold)\b",
                text,
                re.IGNORECASE,
            )
        )
    return False


def _is_duplicate_of_visible_fact(fact: dict, visible_facts: list[dict]) -> bool:
    normalized = re.sub(r"\s+", " ", _fact_text(fact).strip().lower())
    return any(
        other.get("category") == fact.get("category")
        and re.sub(r"\s+", " ", _fact_text(other).strip().lower()) == normalized
        for other in visible_facts
    )


def _reason_matches_fact(reason: str, fact: dict, visible_facts: list[dict]) -> bool:
    text = _fact_text(fact)
    category = fact.get("category")
    if reason == "duplicate_or_already_represented":
        return _is_duplicate_of_visible_fact(fact, visible_facts)
    if _is_critical_fact(fact):
        return False
    if reason == "technical_detail":
        return category in {"tests", "procedures", "other"} and bool(_TECHNICAL_PATTERN.search(text))
    if reason == "routine_non_actionable":
        return not _is_critical_fact(fact) and bool(_ROUTINE_PATTERN.search(text))
    if reason == "rejected_non_actionable_differential":
        return category == "diagnosis" and bool(_DIFFERENTIAL_PATTERN.search(text))
    if reason == "generic_not_patient_specific":
        return _is_generic_advice(fact)
    if reason == "stable_unchanged_background":
        return bool(_STABLE_PATTERN.search(text))
    return False


def _citation_ids(
    value,
    path: str,
    valid_ids: set[int],
    errors: list[str],
    *,
    required: bool,
) -> list[int]:
    if not isinstance(value, list):
        if required:
            errors.append(f"{path} has content but no citations")
        return []
    if required and not value:
        errors.append(f"{path} has content but no citations")
        return []
    cited: list[int] = []
    for fact_id in value:
        if not isinstance(fact_id, int):
            errors.append(f"{path} contains a non-integer fact ID")
        elif fact_id not in valid_ids:
            errors.append(f"{path} cites unknown fact ID {fact_id}")
        else:
            cited.append(fact_id)
    if len(cited) != len(set(cited)):
        errors.append(f"{path} cites the same fact more than once")
    return cited


def _has_content(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    if value is None:
        return False
    return True


def _item_has_visible_content(item: dict) -> bool:
    return any(key != "source_fact_ids" and _has_content(value) for key, value in item.items())


def assert_plan_citations(plan: dict, facts: dict | list[dict]) -> dict:
    """Assert complete visible-or-omitted disposition without mutating input."""
    errors: list[str] = []
    fact_list = _fact_list(facts)
    fact_ids = [fact.get("id") for fact in fact_list]
    duplicate_fact_ids = sorted(
        fact_id for fact_id, count in Counter(fact_ids).items()
        if isinstance(fact_id, int) and count > 1
    )
    if duplicate_fact_ids:
        errors.append(f"fact ledger contains duplicate IDs {duplicate_fact_ids}")
    facts_by_id = {
        fact["id"]: fact for fact in fact_list
        if isinstance(fact, dict) and isinstance(fact.get("id"), int)
    }
    valid_ids = set(facts_by_id)
    visible_ids: set[int] = set()

    summary = plan.get("summary")
    summary_visible = isinstance(summary, str) and bool(summary.strip())
    summary_ids = _citation_ids(
        plan.get("summary_fact_ids"), "summary", valid_ids, errors, required=summary_visible,
    )
    if summary_visible:
        visible_ids.update(summary_ids)

    diagnosis = plan.get("diagnosis") if isinstance(plan.get("diagnosis"), dict) else {}
    changed = diagnosis.get("changed_since_last_visit")
    changed_visible = isinstance(changed, str) and bool(changed.strip())
    changed_ids = _citation_ids(
        diagnosis.get("changed_since_last_visit_fact_ids"),
        "diagnosis.changed_since_last_visit", valid_ids, errors, required=changed_visible,
    )
    if changed_visible:
        visible_ids.update(changed_ids)
    for index, detail in enumerate(diagnosis.get("details", [])):
        if isinstance(detail, dict):
            visible = _item_has_visible_content(detail)
            cited = _citation_ids(
                detail.get("source_fact_ids"), f"diagnosis.details[{index}]", valid_ids, errors,
                required=visible,
            )
            if visible:
                visible_ids.update(cited)

    for section in ITEM_LIST_FIELDS:
        items = plan.get(section, [])
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if isinstance(item, dict):
                visible = _item_has_visible_content(item)
                cited = _citation_ids(
                    item.get("source_fact_ids"), f"{section}[{index}]", valid_ids, errors,
                    required=visible,
                )
                if visible:
                    visible_ids.update(cited)

    questions_cited = 0
    questions = plan.get("questions", [])
    if isinstance(questions, list):
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                errors.append(f"questions[{index}] must be cited content")
                continue
            text = question.get("question")
            visible = isinstance(text, str) and bool(text.strip())
            cited = _citation_ids(
                question.get("source_fact_ids"), f"questions[{index}]", valid_ids, errors,
                required=visible,
            )
            if visible:
                visible_ids.update(cited)
                if cited:
                    questions_cited += 1

    omission_entries = plan.get("omitted_facts", [])
    omitted_ids: list[int] = []
    if not isinstance(omission_entries, list):
        errors.append("omitted_facts must be a list")
        omission_entries = []
    for index, entry in enumerate(omission_entries):
        if not isinstance(entry, dict):
            errors.append(f"omitted_facts[{index}] must be an object")
            continue
        fact_id = entry.get("fact_id")
        reason = entry.get("reason")
        if reason not in OMISSION_REASONS:
            errors.append(f"omitted_facts[{index}] has invalid omission reason {reason!r}")
        if not isinstance(fact_id, int) or fact_id not in valid_ids:
            errors.append(f"unknown omitted fact ID {fact_id}")
            continue
        omitted_ids.append(fact_id)
        visible_facts = [facts_by_id[visible_id] for visible_id in visible_ids]
        if reason in OMISSION_REASONS and not _reason_matches_fact(
            reason, facts_by_id[fact_id], visible_facts,
        ):
            errors.append(f"critical fact ID {fact_id} cannot be omitted as {reason}")

    for fact_id, count in sorted(Counter(omitted_ids).items()):
        if count > 1:
            errors.append(f"fact ID {fact_id} is omitted more than once")
    omitted_set = set(omitted_ids)
    for fact_id in sorted(visible_ids & omitted_set):
        errors.append(f"fact ID {fact_id} is both visible and omitted")
    for fact_id in sorted(valid_ids - visible_ids - omitted_set):
        errors.append(f"fact ID {fact_id} is uncovered")
    for fact_id in sorted(visible_ids):
        if _is_generic_advice(facts_by_id[fact_id]):
            errors.append(f"generic advice fact ID {fact_id} is presented as patient-specific")

    if errors:
        raise PlanCitationError(errors)
    return {
        "facts_total": len(valid_ids),
        "facts_visible": len(visible_ids),
        "facts_omitted": len(omitted_set),
        "questions_cited": questions_cited,
    }


def _failed(run_dir: str, message: str, errors: list[str] | None = None) -> int:
    runlog.record(
        run_dir, "plan_check", "failed",
        checks={"validation_errors": errors or [message]},
    )
    print(message, file=sys.stderr)
    for error in errors or []:
        print(f"  {error}", file=sys.stderr)
    return 1


def _run_assemble(run_dir: str) -> int:
    raw_path = os.path.join(run_dir, "03_plan.raw.json")
    facts_path = os.path.join(run_dir, "02_facts.json")
    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    if os.path.exists(draft_path):
        os.remove(draft_path)
    if not os.path.isfile(raw_path):
        return _failed(run_dir, "cite_check: could not find 03_plan.raw.json in the run directory.")
    if not os.path.isfile(facts_path):
        return _failed(run_dir, "cite_check: could not find 02_facts.json in the run directory.")
    try:
        raw = _read_json(raw_path)
        facts = _read_json(facts_path)
    except json.JSONDecodeError as exc:
        return _failed(run_dir, f"cite_check: input is not valid JSON ({exc}).")

    schema_errors = validate.validate(raw, validate.load_schema("care_plan_agent"))
    if schema_errors:
        return _failed(
            run_dir,
            "cite_check: 03_plan.raw.json does not match care_plan_agent.schema.json:",
            schema_errors,
        )
    try:
        checks = assert_plan_citations(raw, facts)
    except PlanCitationError as exc:
        return _failed(
            run_dir, "cite_check: plan citation/disposition validation failed:", exc.errors,
        )

    plugin_version = runlog.plugin_version()
    plan = dict(raw)
    plan["schema_version"] = SCHEMA_VERSION
    plan["plugin_version"] = plugin_version
    plan["meta"] = {
        "run_id": _run_id(run_dir), "plugin_version": plugin_version,
        "schema_version": SCHEMA_VERSION, "level": "standard",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    plan_errors = validate.validate(plan, validate.load_schema("care_plan"))
    if plan_errors:
        return _failed(run_dir, "cite_check: internal plan construction error:", plan_errors)

    _write_json(draft_path, plan)
    runlog.record(
        run_dir,
        "plan_check",
        "ok",
        checks=checks,
        artifacts=["03_plan.draft.json"],
        run_id=_run_id(run_dir),
    )
    print(f"OK wrote {draft_path} ({checks['facts_total']} facts accounted for)")
    print(
        "plan_check: ok | "
        f"facts_visible={checks['facts_visible']} facts_omitted={checks['facts_omitted']}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate assembled care-plan citations and omissions.")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run_assemble(_build_arg_parser().parse_args(argv).run_dir)


if __name__ == "__main__":
    sys.exit(main())
