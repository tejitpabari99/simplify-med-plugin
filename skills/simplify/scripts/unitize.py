#!/usr/bin/env python3
"""Deterministic unitizer: turns one or more input text files into a
numbered list of units, the only thing the writer and verifier ever cite.

Every non-blank line becomes a unit with a contiguous id. Boilerplate units
are kept for audit but marked `"skip": "<reason>"`: a line that is only a
URL (`url`), a page counter such as "Page 2 of 3" (`page_counter`), or an
exact repeat, after whitespace normalization, of an earlier unit of at least
8 characters that carries no protected-content signal (`repeat`; the first
occurrence is kept). Skipped units are
left out of `01_source.txt` and of the protected-content scan and are never
valid citations.

Refuses (before creating a run) any input that is not written text: image
files by extension or signature, DICOM, PDF, and other binary files.

Writes, inside the run directory:
    01_units.json      every unit, including skipped ones (schema `units`)
    01_source.txt      non-skipped units as "[<id>] <text>", with a
                       "=== <file> page <n> ===" header line whenever the
                       file or page changes
    01_protected.json  protected-content candidate unit ids per category
                       (scripts/protected.py; schema `protected`)

Prints `unitize: ok | files=N units=N skipped=N protected=N` (units counts
every unit, skipped ones included; protected counts distinct candidate unit
ids), then the run directory on the last line.

CLI:
    python3 unitize.py (--runs-dir DIR | --run-dir DIR)
        --input PATH[:native|ocr|pasted] [--input PATH[:method] ...]

Stdlib only. Reads and writes only inside the run directory (and reads the
paths named by --input). Runnable as a script and importable as `unitize`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protected  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402
from _version import PLUGIN_VERSION, SCHEMA_VERSION  # noqa: E402

_METHODS = ("native", "ocr", "pasted")
_DEFAULT_METHOD = "native"
_REPEAT_MIN_CHARS = 8
_URL_ONLY = re.compile(r"^[<(\[]?(https?://|www\.)\S+?[>)\].,;]?$", re.IGNORECASE)
_PAGE_COUNTER = re.compile(r"^[-\u2013\u2014|\s]*(page|pg\.?)\s*\d+(\s*(of|/)\s*\d+)?[-\u2013\u2014|\s]*$",
                           re.IGNORECASE)


# Hard boundary: the pipeline reads written text only. Medical images
# (X-ray, CT, MRI, ultrasound, ECG tracings, photos) are refused, and so is
# any other binary file, so an image can never be "read" by accident.
_IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".heic", ".heif", ".dcm", ".dicom", ".svg",
})
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "a PNG image"),
    (b"\xff\xd8\xff", "a JPEG image"),
    (b"GIF87a", "a GIF image"),
    (b"GIF89a", "a GIF image"),
    (b"II*\x00", "a TIFF image"),
    (b"MM\x00*", "a TIFF image"),
)


def refusal_reason(path: str, raw_bytes: bytes) -> str | None:
    """Return why an input is not usable written text, or None when it is."""
    if os.path.splitext(path)[1].lower() in _IMAGE_EXTENSIONS:
        return "it is an image file"
    for signature, label in _IMAGE_SIGNATURES:
        if raw_bytes.startswith(signature):
            return f"it is {label}"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "it is a WEBP image"
    if raw_bytes[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypheif"):
        return "it is a HEIC image"
    if len(raw_bytes) >= 132 and raw_bytes[128:132] == b"DICM":
        return "it is a DICOM medical image"
    if raw_bytes.startswith(b"%PDF-"):
        return "it is a PDF; extract its text first"
    if b"\x00" in raw_bytes:
        return "it is a binary file, not text"
    return None


def _input_digest(raw_files) -> str:
    digest = hashlib.sha256()
    for _path, method, raw_bytes in raw_files:
        digest.update(method.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(raw_bytes).to_bytes(8, "big"))
        digest.update(raw_bytes)
    return digest.hexdigest()


def _run_id_for(input_digest: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{input_digest[:6]}-{secrets.token_hex(3)}"


def _prepare_run_dir(run_dir: str) -> None:
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir)


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
        reason = refusal_reason(path, raw_bytes)
        if reason:
            _fatal(
                f"unitize refused input file {path!r}: {reason}. "
                "This plugin works only with written text and never reads or interprets "
                "medical images (X-ray, CT, MRI, ultrasound, ECG tracings, photos). "
                "Provide the written report or the document's extracted text instead."
            )
            return 1
        raw_files.append((path, method, raw_bytes))

    input_digest = _input_digest(raw_files)
    run_id = _run_id_for(input_digest)
    if args.run_dir is not None:
        run_dir = args.run_dir
    else:
        run_dir = os.path.join(args.runs_dir, run_id)
    _prepare_run_dir(run_dir)
    return _run(raw_files, run_dir, run_id, input_digest)


def _mark_boilerplate(units: list[dict]) -> None:
    """Set `skip` on URL-only lines, page counters, and exact repeats (in place)."""
    seen: set[str] = set()
    for unit in units:
        normalized = " ".join(unit["text"].split())
        if _URL_ONLY.match(normalized):
            unit["skip"] = "url"
        elif _PAGE_COUNTER.match(normalized):
            unit["skip"] = "page_counter"
        elif (
            len(normalized) >= _REPEAT_MIN_CHARS
            and normalized in seen
            and not protected.categories_for(normalized)
        ):
            # A repeated line that carries protected content (e.g. a second
            # study's identical IMPRESSION line) stays citable.
            unit["skip"] = "repeat"
        seen.add(normalized)


def _source_text(units: list[dict]) -> str:
    """Render non-skipped units as "[<id>] <text>" under file/page headers."""
    lines: list[str] = []
    current = None
    for unit in units:
        if unit.get("skip"):
            continue
        location = (unit["file"], unit["page"])
        if location != current:
            lines.append(f"=== {unit['file']} page {unit['page']} ===")
            current = location
        lines.append(f"[{unit['id']}] {unit['text']}")
    return "".join(line + "\n" for line in lines)


def _write_json(path: str, doc: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")


def _run(raw_files, run_dir: str, run_id: str, input_digest: str) -> int:
    input_dir = os.path.join(run_dir, "00_input")
    os.makedirs(input_dir, exist_ok=True)

    used_basenames: dict = {}
    manifest_inputs = []
    pages_per_page_list: list[list[dict]] = []
    next_id = 1
    total_pages = 0
    blank_lines_skipped = 0

    prepared_inputs = []
    for path, method, raw_bytes in raw_files:
        text = raw_bytes.decode("utf-8", errors="replace")
        basename = os.path.basename(path)
        dest_name = _dedupe_basename(basename, used_basenames)
        dest_path = os.path.join(input_dir, dest_name)
        pages = _split_pages(text)
        input_record = {
            "file": dest_name,
            "extraction_method": method,
            "pages": len(pages),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }
        manifest_inputs.append(input_record)
        prepared_inputs.append((dest_path, raw_bytes, pages, input_record))

    runlog.initialize(run_dir, run_id, manifest_inputs)

    for dest_path, raw_bytes, pages, input_record in prepared_inputs:
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        total_pages += len(pages)
        method = input_record["extraction_method"]
        dest_name = input_record["file"]

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

    empty = [path for path, _method, raw_bytes in raw_files if len(raw_bytes) == 0]
    copied_artifacts = [f"00_input/{item['file']}" for item in manifest_inputs]
    if empty:
        runlog.record(
            run_dir,
            "unitize",
            "failed",
            checks={"empty_files": empty, "input_digest": input_digest},
            artifacts=copied_artifacts,
            run_id=run_id,
        )
        _fatal(
            "unitize found an empty input file (" + ", ".join(empty) + "). "
            "An empty document has no text to extract facts from, so the run cannot continue. "
            "Provide a non-empty file for this input and try again."
        )
        return 1

    all_units = [u for page_units in pages_per_page_list for u in page_units]

    if len(all_units) == 0:
        runlog.record(run_dir, "unitize", "failed", checks={
            "files": len(raw_files), "pages": total_pages, "units": 0, "input_digest": input_digest,
        }, artifacts=copied_artifacts, run_id=run_id)
        _fatal(
            "unitize found no usable text in the input document(s) -- every line was blank. "
            "There is nothing to extract facts from, so the run cannot continue. "
            "Check that the right file was provided and that it contains text."
        )
        return 1

    _mark_boilerplate(all_units)
    kept_units = [u for u in all_units if not u.get("skip")]
    skipped = len(all_units) - len(kept_units)
    if not kept_units:
        runlog.record(run_dir, "unitize", "failed", checks={
            "files": len(raw_files), "pages": total_pages, "units": len(all_units),
            "skipped": skipped, "input_digest": input_digest,
        }, artifacts=copied_artifacts, run_id=run_id)
        _fatal(
            "unitize found only boilerplate in the input document(s) -- every line was a URL, "
            "a page counter, or a repeat. There is nothing to extract facts from, so the run cannot continue. "
            "Check that the right file was provided and that it contains the clinical text."
        )
        return 1

    units_doc = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "run_id": run_id,
        "units": all_units,
    }
    categories = protected.scan(all_units)
    protected_doc = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "categories": categories,
    }
    errors = validate.validate(units_doc, validate.load_schema("units"))
    errors += validate.validate(protected_doc, validate.load_schema("protected"))
    if errors:
        runlog.record(run_dir, "unitize", "failed", checks={"schema_errors": errors}, run_id=run_id)
        _fatal("unitize produced a units or protected document that failed its own schema; this is a bug in unitize.py.")
        return 1

    _write_json(os.path.join(run_dir, "01_units.json"), units_doc)
    with open(os.path.join(run_dir, "01_source.txt"), "w", encoding="utf-8") as f:
        f.write(_source_text(all_units))
    _write_json(os.path.join(run_dir, "01_protected.json"), protected_doc)

    skipped_by_reason: dict[str, int] = {}
    for unit in all_units:
        if unit.get("skip"):
            skipped_by_reason[unit["skip"]] = skipped_by_reason.get(unit["skip"], 0) + 1
    checks = {
        "files": len(raw_files),
        "pages": total_pages,
        "units": len(all_units),
        "skipped": skipped,
        "skipped_by_reason": skipped_by_reason,
        "protected": len(protected.candidate_ids(categories)),
        "protected_by_category": {category: len(ids) for category, ids in categories.items()},
        "blank_lines_skipped": blank_lines_skipped,
        "input_digest": input_digest,
    }
    artifacts = copied_artifacts + ["01_units.json", "01_source.txt", "01_protected.json"]
    runlog.record(run_dir, "unitize", "ok", checks=checks, artifacts=artifacts, run_id=run_id)

    print(
        f"unitize: ok | files={checks['files']} units={checks['units']} "
        f"skipped={checks['skipped']} protected={checks['protected']}"
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
