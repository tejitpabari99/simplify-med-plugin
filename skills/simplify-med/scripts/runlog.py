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
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

try:
    from _version import PLUGIN_VERSION, SCHEMA_VERSION
except ImportError:  # pragma: no cover - defensive, mirrors validate.py style
    PLUGIN_VERSION = "0.1.0"
    SCHEMA_VERSION = "1.0"

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def plugin_version() -> str:
    """Return the plugin version.

    Prefers reading plugin.meta.json by walking up from this file's
    directory (so a dev checkout always reflects the source of truth in
    plugin.meta.json). Falls back to the PLUGIN_VERSION constant in
    _version.py if plugin.meta.json cannot be found -- e.g. when packaged
    for claude.ai, where plugin.meta.json is excluded from the archive.
    """
    current = _SCRIPTS_DIR
    while True:
        candidate = os.path.join(current, "plugin.meta.json")
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


def read(run_dir: str) -> dict:
    """Return the parsed contents of <run_dir>/run.json (empty dict if absent)."""
    path = _run_json_path(run_dir)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_run_json(run_dir: str) -> dict:
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


def record(
    run_dir: str,
    stage: str,
    status: str,
    checks: dict | None = None,
    attempts: int | None = None,
    started: bool = False,
    finished: bool = True,
) -> dict:
    """Create run.json if missing and upsert stages[stage].

    On repeated calls for the same stage, `checks` dicts are merged
    shallowly (new keys overwrite old ones). `started_at` is set the first
    time this stage is recorded (or whenever `started=True` is passed and
    it is not already set). `finished_at` is set when `finished=True`.
    """
    data = _ensure_run_json(run_dir)
    stages = data.setdefault("stages", {})
    entry = stages.get(stage)
    if entry is None:
        entry = {
            "status": status,
            "attempts": attempts if attempts is not None else 0,
            "started_at": None,
            "finished_at": None,
            "checks": {},
        }
        stages[stage] = entry

    entry["status"] = status
    if attempts is not None:
        entry["attempts"] = attempts

    if (started or entry.get("started_at") is None):
        entry["started_at"] = _utc_now_iso()

    if checks:
        existing_checks = entry.get("checks") or {}
        existing_checks.update(checks)
        entry["checks"] = existing_checks
    elif entry.get("checks") is None:
        entry["checks"] = {}

    if finished:
        entry["finished_at"] = _utc_now_iso()

    _atomic_write(_run_json_path(run_dir), data)
    return data


def notice(run_dir: str, text: str) -> dict:
    """Append `text` to notices if not already present."""
    data = _ensure_run_json(run_dir)
    notices = data.setdefault("notices", [])
    if text not in notices:
        notices.append(text)
    _atomic_write(_run_json_path(run_dir), data)
    return data


def set_inputs(run_dir: str, inputs_list: list) -> dict:
    """Replace the run's `inputs` list."""
    data = _ensure_run_json(run_dir)
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
        choices=["ok", "degraded", "failed", "skipped"],
        help="Stage status",
    )
    parser.add_argument("--checks", default=None, help="JSON object of checks to merge in")
    parser.add_argument("--attempts", type=int, default=None, help="Attempt count")
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
    )

    if args.notice:
        notice(args.run_dir, args.notice)

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
