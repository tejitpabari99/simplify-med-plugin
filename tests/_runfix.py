"""Shared run fixtures for the check/settle/finalize pipeline tests.

Builds run directories directly (run.json, 01_units.json, 01_source.txt,
01_protected.json, raw model outputs) so script tests do not depend on the
unitizer or on a model.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os

import check_draft
import finalize
import runlog
import settle
from _version import SCHEMA_VERSION

NOTE_LINES = (
    "Chief complaint: chest pain for 2 days.",
    "https://portal.example.test/visits/000001",
    "Troponin normal. ECG normal.",
    "Clinical impression: Chest wall pain.",
    "Start ibuprofen 400 mg every 8 hours as needed for pain.",
    "Follow up with Dr. Alok Singh in 3 days.",
    "Return to the ER for shortness of breath or worsening pain.",
    "Discharged home in good condition.",
    "Lipid panel pending.",
    "All adults should exercise regularly.",
)
NOTE_TEXT = "\n".join(NOTE_LINES) + "\n"
SKIPS = {2: "url"}
PROTECTED = {
    "medication_changes": [5],
    "follow_up": [6],
    "return_precautions": [7],
    "diagnoses": [4],
    "disposition": [8],
    "abnormal_or_pending_results": [9],
}
PII_NAME = "Dr. Alok Singh"
NOISE_MARKER = "All adults should exercise regularly."


def write_json(path: str, document) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def read_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def call(main, *argv: str) -> tuple[int, str, str]:
    """Run a script's main(argv) and capture (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def make_source(
    run_dir: str,
    lines=NOTE_LINES,
    *,
    skips: dict | None = None,
    protected: dict | None = None,
) -> str:
    """Write run.json and the UNITIZE outputs for `lines`; return the run id."""
    skips = SKIPS if skips is None else skips
    protected = PROTECTED if protected is None else protected
    run_id = os.path.basename(os.path.normpath(run_dir))
    os.makedirs(os.path.join(run_dir, "00_input"), exist_ok=True)
    text = "\n".join(lines) + "\n"
    with open(os.path.join(run_dir, "00_input", "note.txt"), "w", encoding="utf-8") as handle:
        handle.write(text)
    runlog.initialize(run_dir, run_id, [{
        "file": "note.txt", "extraction_method": "native", "pages": 1, "sha256": "fixture",
    }])
    units = []
    for index, line in enumerate(lines, start=1):
        unit = {
            "id": index, "file": "note.txt", "page": 1, "line": index,
            "text": line, "extraction_method": "native",
        }
        if index in skips:
            unit["skip"] = skips[index]
        units.append(unit)
    write_json(os.path.join(run_dir, "01_units.json"), {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": runlog.plugin_version(),
        "run_id": run_id,
        "units": units,
    })
    with open(os.path.join(run_dir, "01_source.txt"), "w", encoding="utf-8") as handle:
        handle.write("=== note.txt page 1 ===\n")
        for unit in units:
            if not unit.get("skip"):
                handle.write(f"[{unit['id']}] {unit['text']}\n")
    categories = {category: list(protected.get(category, [])) for category in check_draft.PROTECTED_CATEGORIES}
    write_json(os.path.join(run_dir, "01_protected.json"), {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "categories": categories,
    })
    runlog.record(
        run_dir, "unitize", "ok", checks={"units": len(units)},
        artifacts=["00_input/note.txt", "01_units.json", "01_source.txt", "01_protected.json"],
        run_id=run_id,
    )
    return run_id


def coverage(**overrides) -> dict:
    """Coverage with every category 'none_in_source' unless overridden with unit ids."""
    return {
        category: (
            {"status": "shown", "unit_ids": list(overrides[category])}
            if category in overrides else {"status": "none_in_source", "unit_ids": []}
        )
        for category in check_draft.PROTECTED_CATEGORIES
    }


def draft_raw() -> dict:
    """A valid WRITE output for NOTE_LINES. Unit 9 (pending lab) is left uncited."""
    return {
        "visit_type": "er_visit",
        "why_you_went": {"text": "You went to the ER for chest pain for 2 days.", "unit_ids": [1]},
        "findings_lead": None,
        "findings": [
            {"name": "Heart tests", "result": "Your troponin blood test and heart tracing were normal.",
             "unit_ids": [3]},
        ],
        "diagnoses": [{"name": "Chest wall pain", "unit_ids": [4]}],
        "disposition": {"text": "You were sent home in good condition.", "unit_ids": [8]},
        "next_steps": [
            {"text": "Make a follow-up appointment with your doctor in 3 days.", "unit_ids": [6]},
        ],
        "medicines": {
            "items": [{
                "name": "Ibuprofen", "change": "start",
                "text": "Take 400 mg every 8 hours as needed for pain.", "unit_ids": [5],
            }],
            "none_statement": None,
        },
        "return_precautions": [
            {"text": "Go back to the ER if you have shortness of breath or your pain gets worse.",
             "unit_ids": [7]},
        ],
        "questions": [],
        "coverage": coverage(
            medication_changes=[5], follow_up=[6], return_precautions=[7], diagnoses=[4], disposition=[8],
        ),
    }


def verify_raw_for(
    draft: dict,
    check: dict,
    *,
    protected_result: str = "not_needed",
    reason: str = "not_patient_specific",
) -> dict:
    """An all-supported verification: no edits, numeric flags equivalent,
    every uncited protected unit resolved with `protected_result`."""
    import plan_paths

    protected_units = []
    for entry in check["uncited_protected"]:
        resolved = {"unit_id": entry["unit_id"], "result": protected_result}
        if protected_result == "not_needed":
            resolved["reason"] = reason
        protected_units.append(resolved)
    return {
        "claims": [{"path": path, "result": "supported"} for path, _item in plan_paths.visible_items(draft)],
        "operations": [],
        "numeric_resolutions": [
            {"flag_id": flag["flag_id"], "resolution": "equivalent"} for flag in check["numeric_flags"]
        ],
        "protected_units": protected_units,
    }


def write_draft(run_dir: str, draft: dict, round_no: int = 1) -> str:
    path = os.path.join(run_dir, check_draft.artifact_names(round_no)["draft_raw"])
    write_json(path, draft)
    return path


def write_verify(run_dir: str, verify: dict, round_no: int = 1) -> str:
    path = os.path.join(run_dir, check_draft.artifact_names(round_no)["verify_raw"])
    write_json(path, verify)
    return path


def checked(run_dir: str, round_no: int = 1) -> tuple[dict, dict]:
    """Return (02_draft.json, 02_check.json) for a round."""
    names = check_draft.artifact_names(round_no)
    return read_json(os.path.join(run_dir, names["draft"])), read_json(os.path.join(run_dir, names["check"]))


def make_run_dir(run_dir: str, *, final: bool = False, draft: dict | None = None) -> str:
    """Create a complete, valid run through settlement (and finalization when
    `final`); return the run id."""
    run_id = make_source(run_dir)
    write_draft(run_dir, draft or draft_raw())
    code, out, err = call(check_draft.main, "--run-dir", run_dir)
    if code != 0:
        raise AssertionError(f"fixture draft failed check_draft:\n{out}{err}")
    checked_draft, check = checked(run_dir)
    write_verify(run_dir, verify_raw_for(checked_draft, check))
    code, out, err = call(settle.main, "--run-dir", run_dir)
    if code != 0:
        raise AssertionError(f"fixture verification failed settle:\n{out}{err}")
    if final:
        code, out, err = call(finalize.main, "--run-dir", run_dir)
        if code != 0:
            raise AssertionError(f"fixture run failed finalize:\n{out}{err}")
    return run_id


def deep(document):
    return copy.deepcopy(document)
