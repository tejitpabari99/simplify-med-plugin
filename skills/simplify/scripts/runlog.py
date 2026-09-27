#!/usr/bin/env python3
"""Shared run-log helper.

Every deterministic script in this plugin appends its result to
``<run-dir>/run.json`` through this module, so the run's audit trail is
always in one place and always written atomically.

Stdlib only. Runnable as ``python3 runlog.py ...`` and importable as
``runlog`` (or ``skills.simplify_med.scripts.runlog`` depending on how the
caller's sys.path is set up).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone

try:
    from _version import PLUGIN_VERSION, SCHEMA_VERSION
except ImportError:  # pragma: no cover - defensive, mirrors validate.py style
    PLUGIN_VERSION = "0.1.0"
    SCHEMA_VERSION = "3.0"

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_STAGES = frozenset({"unitize", "write", "check", "verify", "settle", "finalize"})
# `settle` may also end a round by requesting the one repair round.
_CORE_STATUSES = {"ok", "failed"}
_SETTLE_STATUSES = _CORE_STATUSES | {"repair_requested"}
_OPTIONAL_STAGES = frozenset({"glossary", "render_md", "render_html", "render_audit"})
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def plugin_version() -> str:
    """Return the plugin version.

    Prefers reading the portable root plugin.json by walking up from this
    file's directory. Falls back to the embedded constant when the scripts
    run outside a complete plugin checkout.
    """
    current = _SCRIPTS_DIR
    while True:
        candidate = os.path.join(current, "plugin.json")
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                version = data.get("version")
                if isinstance(version, str) and version:
                    return version
            except (OSError, json.JSONDecodeError):
                pass
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return PLUGIN_VERSION


def _run_json_path(run_dir: str) -> str:
    return os.path.join(run_dir, "run.json")


def _atomic_write(path: str, data: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".run.json.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _thread_lock(run_dir: str) -> threading.Lock:
    key = os.path.abspath(run_dir)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


@contextlib.contextmanager
def _locked(run_dir: str):
    os.makedirs(run_dir, exist_ok=True)
    digest = hashlib.sha256(os.path.abspath(run_dir).encode("utf-8")).hexdigest()
    lock_path = os.path.join(tempfile.gettempdir(), f"simplify-runlog-{digest}.lock")
    with _thread_lock(run_dir):
        with open(lock_path, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read(run_dir: str) -> dict:
    """Return the parsed contents of <run_dir>/run.json (empty dict if absent)."""
    with _locked(run_dir):
        path = _run_json_path(run_dir)
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def _ensure_run_json_unlocked(run_dir: str) -> dict:
    path = _run_json_path(run_dir)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    run_id = os.path.basename(os.path.normpath(run_dir))
    data = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version(),
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "level": "standard",
        "inputs": [],
        "stages": {},
        "notices": [],
    }
    return data


def initialize(run_dir: str, run_id: str, inputs_list: list) -> dict:
    """Create a fresh run log, replacing any prior run identity."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    data = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version(),
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "level": "standard",
        "inputs": inputs_list,
        "stages": {},
        "notices": [],
    }
    with _locked(run_dir):
        _atomic_write(_run_json_path(run_dir), data)
    return data


def _normalize_artifacts(artifacts: list | None) -> list[dict]:
    normalized = []
    for artifact in artifacts or []:
        path = artifact if isinstance(artifact, str) else artifact.get("path") if isinstance(artifact, dict) else None
        if not isinstance(path, str) or not path or os.path.isabs(path):
            raise ValueError("artifact paths must be non-empty paths relative to the run directory")
        normalized_path = os.path.normpath(path)
        if normalized_path == ".." or normalized_path.startswith(".." + os.sep):
            raise ValueError("artifact paths must stay inside the run directory")
        normalized.append({"path": normalized_path.replace(os.sep, "/")})
    return normalized


def _validate_stage(stage: str, status: str, skip_reason: str | None) -> None:
    if stage not in _CORE_STAGES | _OPTIONAL_STAGES:
        raise ValueError(f"unrecognized stage: {stage}")
    if stage == "settle" and status not in _SETTLE_STATUSES:
        raise ValueError("stage settle requires status ok, failed, or repair_requested")
    if stage in _CORE_STAGES and stage != "settle" and status not in _CORE_STATUSES:
        raise ValueError(f"core stage {stage} requires status ok or failed")
    if stage in _OPTIONAL_STAGES and status not in {"ok", "degraded", "failed", "skipped"}:
        raise ValueError(f"invalid optional stage status: {status}")
    if status == "skipped" and (stage not in _OPTIONAL_STAGES or not skip_reason):
        raise ValueError("skipped optional stages require a skip reason")
    if status != "skipped" and skip_reason is not None:
        raise ValueError("skip_reason is only valid for skipped optional stages")


def record(
    run_dir: str,
    stage: str,
    status: str,
    checks: dict | None = None,
    attempts: int | None = None,
    started: bool = False,
    finished: bool = True,
    artifacts: list | None = None,
    skip_reason: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Create run.json if missing and upsert stages[stage].

    On repeated calls for the same stage, `checks` dicts are merged
    shallowly (new keys overwrite old ones). `started_at` is set the first
    time this stage is recorded (or whenever `started=True` is passed and
    it is not already set). `finished_at` is set when `finished=True`.
    """
    _validate_stage(stage, status, skip_reason)
    normalized_artifacts = _normalize_artifacts(artifacts)
    with _locked(run_dir):
        data = _ensure_run_json_unlocked(run_dir)
        if run_id is not None and data.get("run_id") != run_id:
            raise ValueError(f"run_id {run_id!r} does not own {run_dir!r}")
        stages = data.setdefault("stages", {})
        entry = stages.get(stage)
        now = _utc_now_iso()
        if entry is None:
            attempt_count = attempts if attempts is not None else 1
            entry = {
                "status": status,
                "attempts": attempt_count,
                "started_at": now,
                "finished_at": None,
                "checks": {},
                "artifacts": [],
            }
            stages[stage] = entry
        else:
            if attempts is not None:
                if attempts < entry.get("attempts", 0):
                    raise ValueError("attempt count cannot decrease")
                entry["attempts"] = attempts
            elif started or (finished and entry.get("finished_at") is not None):
                entry["attempts"] = entry.get("attempts", 0) + 1
            if entry.get("started_at") is None:
                entry["started_at"] = now
        entry["status"] = status
        if started:
            entry["finished_at"] = None
        if checks:
            entry.setdefault("checks", {}).update(checks)
        existing_artifacts = entry.setdefault("artifacts", [])
        for artifact in normalized_artifacts:
            if artifact not in existing_artifacts:
                existing_artifacts.append(artifact)
        if status == "skipped":
            entry["skip_reason"] = skip_reason
        else:
            entry.pop("skip_reason", None)
        if finished:
            entry["finished_at"] = now
        _atomic_write(_run_json_path(run_dir), data)
        return data


def notice(run_dir: str, text: str) -> dict:
    """Append `text` to notices if not already present."""
    with _locked(run_dir):
        data = _ensure_run_json_unlocked(run_dir)
        notices = data.setdefault("notices", [])
        if text not in notices:
            notices.append(text)
        _atomic_write(_run_json_path(run_dir), data)
        return data


def set_inputs(run_dir: str, inputs_list: list, run_id: str | None = None) -> dict:
    """Replace the run's `inputs` list."""
    with _locked(run_dir):
        data = _ensure_run_json_unlocked(run_dir)
        if run_id is not None and data.get("run_id") != run_id:
            raise ValueError(f"run_id {run_id!r} does not own {run_dir!r}")
        data["inputs"] = inputs_list
        _atomic_write(_run_json_path(run_dir), data)
        return data


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a stage result in a run's run.json")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument("--stage", required=True, help="Stage name")
    parser.add_argument(
        "--status",
        required=True,
        choices=["ok", "degraded", "failed", "skipped", "repair_requested"],
        help="Stage status",
    )
    parser.add_argument("--checks", default=None, help="JSON object of checks to merge in")
    parser.add_argument("--attempts", type=int, default=None, help="Attempt count")
    parser.add_argument("--artifact", action="append", default=None, help="Produced artifact path")
    parser.add_argument("--skip-reason", default=None, help="Reason an optional stage was skipped")
    parser.add_argument("--run-id", default=None, help="Expected current run identity")
    parser.add_argument("--notice", default=None, help="Append a notice to the run log")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    checks = None
    if args.checks is not None:
        try:
            checks = json.loads(args.checks)
        except json.JSONDecodeError as exc:
            print(f"--checks is not valid JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(checks, dict):
            print("--checks must be a JSON object", file=sys.stderr)
            return 1

    record(
        run_dir=args.run_dir,
        stage=args.stage,
        status=args.status,
        checks=checks,
        attempts=args.attempts,
        artifacts=args.artifact,
        skip_reason=args.skip_reason,
        run_id=args.run_id,
    )

    if args.notice:
        notice(args.run_dir, args.notice)

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
