#!/usr/bin/env python3
"""Deterministic unitizer: turns one or more input text files into a
numbered list of units, the only thing a grounding agent ever cites.

CLI:
    python3 unitize.py (--runs-dir DIR | --run-dir DIR)
        --input PATH[:native|ocr|pasted] [--input PATH[:method] ...]
        [--chunk-size 150]

Stdlib only. Reads and writes only inside the run directory (and reads the
paths named by --input). Runnable as a script and importable as `unitize`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402

_METHODS = ("native", "ocr", "pasted")
_DEFAULT_METHOD = "native"
_DEFAULT_CHUNK_SIZE = 150


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_id_for(all_bytes: bytes) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(all_bytes).hexdigest()[:6]
    return f"{ts}-{digest}"


def _parse_input_spec(spec: str) -> tuple[str, str]:
    """Split "path[:method]" into (path, method), defaulting to native."""
    if ":" in spec:
        maybe_path, maybe_method = spec.rsplit(":", 1)
        if maybe_method in _METHODS:
            return maybe_path, maybe_method
    return spec, _DEFAULT_METHOD


def _dedupe_basename(basename: str, used: dict) -> str:
    """Return a basename unique within `used` (a dict of name -> True),
    suffixing "-2", "-3", ... before the extension on collision."""
    if basename not in used:
        used[basename] = True
        return basename
    stem, ext = os.path.splitext(basename)
    n = 2
    while True:
        candidate = f"{stem}-{n}{ext}"
        if candidate not in used:
            used[candidate] = True
            return candidate
        n += 1


def _split_pages(text: str) -> list[str]:
    return text.split("\f")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unitize one or more input text files into a run directory")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--runs-dir", default=None, help="Parent directory; a new <run-id> directory is created inside it")
    group.add_argument("--run-dir", default=None, help="Exact run directory to use (created if missing)")
    parser.add_argument("--input", dest="inputs", action="append", required=True,
                         help="Input file, optionally suffixed :native|:ocr|:pasted (default native)")
    parser.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK_SIZE)
    return parser


def _fatal(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    specs = [_parse_input_spec(s) for s in args.inputs]

    # Read every input file's raw bytes up front. A read failure here means
    # we cannot even determine a run id (for --runs-dir mode), so there is
    # nowhere to log to; report and exit.
    raw_files = []  # list of (path, method, raw_bytes)
    for path, method in specs:
        try:
            with open(path, "rb") as f:
                raw_bytes = f.read()
        except OSError as exc:
            _fatal(
                f"unitize could not read input file {path!r}: {exc}. "
                "Check that the path is correct and readable, then try again."
            )
            return 1
        raw_files.append((path, method, raw_bytes))

    # Resolve the run directory.
    if args.run_dir is not None:
        run_dir = args.run_dir
    else:
        all_bytes = b"".join(rb for _, _, rb in raw_files)
        run_id = _run_id_for(all_bytes)
        run_dir = os.path.join(args.runs_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    input_dir = os.path.join(run_dir, "00_input")
    os.makedirs(input_dir, exist_ok=True)

    run_id = os.path.basename(os.path.normpath(run_dir))

    # Fatal: any input file that is empty (0 bytes).
    empty = [path for path, _method, raw_bytes in raw_files if len(raw_bytes) == 0]
    if empty:
        runlog.record(run_dir, "unitize", "failed", checks={"empty_files": empty})
        _fatal(
            "unitize found an empty input file (" + ", ".join(empty) + "). "
            "An empty document has no text to extract facts from, so the run cannot continue. "
            "Provide a non-empty file for this input and try again."
        )
        return 1

    return _run(raw_files, run_dir, run_id, args.chunk_size)


def _run(raw_files, run_dir: str, run_id: str, chunk_size: int) -> int:
    input_dir = os.path.join(run_dir, "00_input")
    os.makedirs(input_dir, exist_ok=True)

    used_basenames: dict = {}
    manifest_inputs = []
    pages_per_page_list: list[list[dict]] = []
    next_id = 1
    total_pages = 0
    blank_lines_skipped = 0

    for path, method, raw_bytes in raw_files:
        text = raw_bytes.decode("utf-8", errors="replace")
        basename = os.path.basename(path)
        dest_name = _dedupe_basename(basename, used_basenames)
        dest_path = os.path.join(input_dir, dest_name)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)

        pages = _split_pages(text)
        total_pages += len(pages)
        manifest_inputs.append({
            "file": dest_name,
            "extraction_method": method,
            "pages": len(pages),
        })

        for page_number, page_text in enumerate(pages, start=1):
            lines = page_text.split("\n")
            page_units: list[dict] = []
            for line_no, raw_line in enumerate(lines, start=1):
                line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
                if not line.strip():
                    blank_lines_skipped += 1
                    continue
                unit = {
                    "id": next_id,
                    "file": dest_name,
                    "page": page_number,
                    "line": line_no,
                    "text": line.rstrip(),
                    "extraction_method": method,
                }
                page_units.append(unit)
                next_id += 1
            pages_per_page_list.append(page_units)

    all_units = [u for page_units in pages_per_page_list for u in page_units]

    if len(all_units) == 0:
        runlog.record(run_dir, "unitize", "failed", checks={
            "files": len(raw_files), "pages": total_pages, "units": 0,
        })
        _fatal(
            "unitize found no usable text in the input document(s) -- every line was blank. "
            "There is nothing to extract facts from, so the run cannot continue. "
            "Check that the right file was provided and that it contains text."
        )
        return 1

    # Chunking: consecutive id ranges, never splitting a page across a chunk
    # boundary unless the page alone exceeds chunk_size.
    chunks_units: list[list[dict]] = []
    current: list[dict] = []
    for page_units in pages_per_page_list:
        if not page_units:
            continue
        if len(current) + len(page_units) <= chunk_size:
            current.extend(page_units)
            continue
        if current:
            chunks_units.append(current)
            current = []
        if len(page_units) > chunk_size:
            for i in range(0, len(page_units), chunk_size):
                chunks_units.append(page_units[i:i + chunk_size])
        else:
            current = list(page_units)
    if current:
        chunks_units.append(current)

    chunks_meta = [
        {"k": k, "first_id": group[0]["id"], "last_id": group[-1]["id"]}
        for k, group in enumerate(chunks_units, start=1)
    ]

    units_doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "units": all_units,
        "chunks": chunks_meta,
    }
    errors = validate.validate(units_doc, validate.load_schema("units"))
    if errors:
        runlog.record(run_dir, "unitize", "failed", checks={"schema_errors": errors})
        _fatal("unitize produced a units document that failed its own schema; this is a bug in unitize.py.")
        return 1

    units_path = os.path.join(run_dir, "01_units.json")
    with open(units_path, "w", encoding="utf-8") as f:
        json.dump(units_doc, f, indent=2)
        f.write("\n")

    for k, group in enumerate(chunks_units, start=1):
        chunk_path = os.path.join(run_dir, f"01_units.{k}.txt")
        with open(chunk_path, "w", encoding="utf-8") as f:
            for unit in group:
                f.write(f"[{unit['id']}] {unit['text']}\n")

    manifest_doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "level": "standard",
        "inputs": manifest_inputs,
    }
    manifest_errors = validate.validate(manifest_doc, validate.load_schema("manifest"))
    if manifest_errors:
        runlog.record(run_dir, "unitize", "failed", checks={"schema_errors": manifest_errors})
        _fatal("unitize produced a manifest that failed its own schema; this is a bug in unitize.py.")
        return 1
    manifest_path = os.path.join(input_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_doc, f, indent=2)
        f.write("\n")
    runlog.set_inputs(run_dir, manifest_inputs)

    checks = {
        "files": len(raw_files),
        "pages": total_pages,
        "units": len(all_units),
        "chunks": len(chunks_units),
        "blank_lines_skipped": blank_lines_skipped,
    }
    runlog.record(run_dir, "unitize", "ok", checks=checks)

    print(
        f"unitize: ok | files={checks['files']} units={checks['units']} "
        f"chunks={checks['chunks']}"
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
