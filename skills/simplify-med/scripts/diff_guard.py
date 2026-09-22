#!/usr/bin/env python3
"""Diff-guards the corrector agent's output against the review corrections.

CLI: python3 diff_guard.py --run-dir D [--strict]

Ported from simplify-med's pipeline._verify_correction_diff /
_diff_item / _split_array_path / _looks_like_pii_substitution /
_PII_ELIGIBLE_FIELDS: walks the whole care-plan tree comparing the
pre-correction draft against the corrector's raw output. A changed leaf is
allowed only if its path is named by a correction, or it is a bounded PII
substitution (<= 4 non-equal word tokens, difflib.SequenceMatcher) in an
eligible field. An array's length may change only where a "remove"
correction accounts for it, tracked by original-index survivorship.

Without --strict, a guard violation falls back to a byte-identical copy of
the draft plus a run notice ("degraded", prefer passing over failure). With
--strict, a violation exits 1 instead, for the orchestrator's single retry
and for tests.

Stdlib only. Importable as `diff_guard`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runlog  # noqa: E402
import sanitize_review as sr  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402

_PATH_SEGMENT_RE = sr._PATH_SEGMENT_RE

# Fields where a bounded name/facility substitution (the PII sweep) is a
# legitimate, unnamed change. Ported verbatim from pipeline.py.
_PII_ELIGIBLE_FIELDS = {
    "summary", "why", "description", "what_it_means_for_you", "instructions",
    "what_to_expect", "what_it_might_mean", "related_to",
    "changed_since_last_visit", "side_effects_to_watch", "preparation",
    "steps", "questions", "low_priority",
}
_MAX_PII_TOKEN_DELTA = 4


def _looks_like_pii_substitution(old, new) -> bool:
    """True if old->new plausibly represents ONLY a name/facility swap:
    word-level SequenceMatcher opcodes, counting non-'equal' tokens on
    either side, bounded by _MAX_PII_TOKEN_DELTA."""
    if not isinstance(old, str) or not isinstance(new, str):
        return False
    old_w, new_w = old.split(), new.split()
    ops = difflib.SequenceMatcher(a=old_w, b=new_w).get_opcodes()
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
    return changed <= _MAX_PII_TOKEN_DELTA


def _split_array_path(path: str):
    """"warning_signs[3]" -> ("warning_signs", 3); "diagnosis.details[0]" ->
    ("diagnosis.details", 0). Returns None if `path`'s last segment carries
    no "[N]" index."""
    head, _, last = path.rpartition(".")
    m = _PATH_SEGMENT_RE.fullmatch(last)
    if not m or m.group(3) is None:
        return None
    array_path = f"{head}.{m.group(1)}" if head else m.group(1)
    return array_path, int(m.group(3))


def _path_for_after(path: str, removed_by_array: dict):
    """Remaps a path addressing the ORIGINAL (draft) tree's array indices
    to the position that original item now occupies in the corrected
    tree, accounting for lower-indexed removals in the same array. Returns
    None if `path` itself addresses a removed item."""
    segments = path.split(".")
    prefix = ""
    out = []
    for seg in segments:
        m = _PATH_SEGMENT_RE.fullmatch(seg)
        if not m:
            return None
        name, _, idx = m.groups()
        array_path = f"{prefix}.{name}" if prefix else name
        if idx is not None:
            i = int(idx)
            removed = removed_by_array.get(array_path, set())
            if i in removed:
                return None
            shift = sum(1 for r in removed if r < i)
            out.append(f"{name}[{i - shift}]")
        else:
            out.append(name)
        prefix = array_path
    return ".".join(out)


def _diff_item(before_v, after_v, path, named, removed_by_array, violations, bad_arrays, pii_hits):
    """Recursively compares one node of the plan tree at `path`, appending
    to `violations` (list of path strings) on any change that is neither a
    named correction target, a bounded PII swap on an eligible leaf, nor
    accounted for by a `remove` correction's effect on the array at
    `path`. Containers are always recursed into structurally."""
    if isinstance(before_v, list) and isinstance(after_v, list):
        removed = removed_by_array.get(path, set())
        expected_survivors = [i for i in range(len(before_v)) if i not in removed]
        if len(after_v) != len(expected_survivors):
            violations.append(f"{path}: expected {len(expected_survivors)} items after correction, got {len(after_v)}")
            bad_arrays.add(path)
            return
        for k, orig_idx in enumerate(expected_survivors):
            _diff_item(before_v[orig_idx], after_v[k], f"{path}[{orig_idx}]", named, removed_by_array, violations, bad_arrays, pii_hits)
        return

    if isinstance(before_v, list) or isinstance(after_v, list):
        violations.append(f"{path}: type changed")
        return

    if isinstance(before_v, dict) and isinstance(after_v, dict):
        for key in set(before_v.keys()) | set(after_v.keys()):
            _diff_item(before_v.get(key), after_v.get(key), f"{path}.{key}", named, removed_by_array, violations, bad_arrays, pii_hits)
        return

    if isinstance(before_v, dict) or isinstance(after_v, dict):
        violations.append(f"{path}: type changed")
        return

    if before_v == after_v:
        return
    if path in named:
        return

    field_name = path.rsplit(".", 1)[-1].split("[", 1)[0]
    if field_name in _PII_ELIGIBLE_FIELDS and _looks_like_pii_substitution(before_v, after_v):
        pii_hits.append(path)
        return

    violations.append(f"{path}: changed unnamed, non-PII field")


def _copy_file(src: str, dst: str) -> None:
    with open(src, "r", encoding="utf-8") as f:
        data = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(data)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diff-guard the corrector agent's output against the review corrections")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--strict", action="store_true", help="Exit 1 on a guard violation instead of falling back")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir
    run_id = os.path.basename(os.path.normpath(run_dir))

    draft_path = os.path.join(run_dir, "03_plan.draft.json")
    review_path = os.path.join(run_dir, "04_review.json")
    raw_corrected_path = os.path.join(run_dir, "05_plan.corrected.raw.json")
    out_path = os.path.join(run_dir, "05_plan.corrected.json")

    corrections = []
    if os.path.isfile(review_path):
        with open(review_path, "r", encoding="utf-8") as f:
            review_doc = json.load(f)
        corrections = review_doc.get("corrections", [])

    if not corrections or not os.path.isfile(raw_corrected_path):
        _copy_file(draft_path, out_path)
        runlog.record(run_dir, "correct", "skipped", checks={"corrections": len(corrections)})
        print(f"correct: skipped | corrections={len(corrections)}")
        return 0

    try:
        with open(raw_corrected_path, "r", encoding="utf-8") as f:
            after_d = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"05_plan.corrected.raw.json is not valid JSON: {exc}")
        runlog.record(run_dir, "correct", "failed", checks={"schema_errors": [str(exc)]})
        return 1

    schema_errors = validate.validate(after_d, validate.load_schema("care_plan"))
    if schema_errors:
        for error in schema_errors:
            print(error)
        runlog.record(run_dir, "correct", "failed", checks={"schema_errors": schema_errors})
        return 1

    with open(draft_path, "r", encoding="utf-8") as f:
        before_d = json.load(f)

    named = {c["path"] for c in corrections}
    removed_by_array: dict = {}
    for c in corrections:
        if c.get("op") == "remove" and c.get("path") != "summary":
            split = _split_array_path(c["path"])
            if split is not None:
                array_path, idx = split
                removed_by_array.setdefault(array_path, set()).add(idx)

    violations: list = []
    bad_arrays: set = set()
    pii_hits: list = []
    for field in set(before_d.keys()) | set(after_d.keys()):
        _diff_item(before_d.get(field), after_d.get(field), field, named, removed_by_array, violations, bad_arrays, pii_hits)

    if violations:
        if args.strict:
            for v in violations:
                print(v)
            runlog.record(run_dir, "correct", "failed", checks={"violations": violations, "corrections": len(corrections)})
            return 1

        _copy_file(draft_path, out_path)
        runlog.notice(
            run_dir,
            "We could not safely apply every correction to this summary. Please compare "
            "important details, like medicine doses, with your original document.",
        )
        runlog.record(run_dir, "correct", "degraded", checks={"violations": violations, "corrections": len(corrections)})
        print(f"correct: degraded | corrections={len(corrections)} violations={len(violations)}")
        return 0

    applied = 0
    unapplied = 0
    for c in corrections:
        op = c.get("op")
        path = c.get("path")
        ok = False
        if op == "remove":
            ok = True
        elif op == "not_stated":
            adjusted = _path_for_after(path, removed_by_array)
            if adjusted is not None:
                found, value_after = sr.resolve_path(after_d, adjusted)
                ok = found and value_after is None
        elif op == "correct":
            adjusted = _path_for_after(path, removed_by_array)
            if adjusted is not None:
                found_before, value_before = sr.resolve_path(before_d, path)
                found_after, value_after = sr.resolve_path(after_d, adjusted)
                ok = found_after and value_after != value_before
        if ok:
            applied += 1
        else:
            unapplied += 1

    # care_plan.schema.json has no top-level "run_id" (additionalProperties:
    # false) -- run_id lives at "meta.run_id" only, and meta is one of the
    # fields the diff walk above already required to be byte-identical
    # between draft and corrected, so it is left untouched here.
    out_doc = dict(after_d)
    out_doc["schema_version"] = SCHEMA_VERSION
    out_doc["plugin_version"] = PLUGIN_VERSION
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, indent=2)
        f.write("\n")

    runlog.record(run_dir, "correct", "ok", checks={
        "corrections": len(corrections),
        "applied": applied,
        "unapplied": unapplied,
        "pii_substitutions": len(pii_hits),
    })
    print(f"correct: ok | corrections={len(corrections)} applied={applied} unapplied={unapplied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
