---
name: simplify
description: Simplify visit notes, discharge summaries, lab reports, imaging reports, and other clinical documents into a short, plain-language report in which every statement is checked against the source. Use when a user wants help understanding supplied medical paperwork. Do not use to diagnose, prescribe, or replace urgent medical care.
---

# Simplify Medical Documents

Turn supplied clinical documents into a short (about 150-300 words), plain-language report that answers: what happened, what did they find, what do I do now, and when do I come back. Every visible statement cites source units and is independently verified before release.

## Execution Contract

- When this skill is selected, run the whole workflow below. Never simplify, summarize, or answer directly from the documents.
- Do not present clinical content until `scripts/finalize.py` succeeds and the current run holds validated `05_plan.final.json` and `report.md`.
- Every step is mandatory. Never skip, reorder, degrade, or reproduce a script's check by hand. If a required command cannot run, stop and report the failure.
- Never read `01_units.json`; it is an audit file. Read the command output instead.
- Model stages write only their named JSON file and never answer the user.
- Present only `<run>/report.md`, as written. Do not create a second summary.

## Inputs

Use one UTF-8 text file per source document. Extract text from PDFs, DOCX files, images, or scans with the tools available before starting, and mark known page breaks with form-feed characters (`\f`). Treat all files in one request as one visit. Paths such as `scripts/...`, `stages/...`, `reference/...`, and `schema/...` are relative to this skill directory.

## Workflow

```text
UNITIZE -> WRITE -> CHECK -> VERIFY -> SETTLE -> FINALIZE
                                         exit 3: one repair round (--round 2)
```

The clean path is two model calls (write, verify) and four script runs.

### 1. Unitize

```bash
python3 scripts/unitize.py --runs-dir <workspace>/simplify-runs --input <file> [--input <file> ...]
```

Append `:ocr` to text transcribed from an image or scan and `:pasted` to manually entered text. The last output line is `<run>`.

### 2. Write (model call)

Follow `stages/write.md` with `<run>/01_source.txt`, `<run>/01_protected.json`, `reference/style_rules.md`, and `schema/draft.schema.json`. Write only `<run>/02_draft.raw.json`.

### 3. Check

```bash
python3 scripts/check_draft.py --run-dir <run>
```

On a non-zero exit, rerun Write once in retry mode with the printed errors, then rerun the check. A second failure stops the run.

### 4. Verify (model call, independent)

Run `stages/verify.md` in a fresh sub-agent when the host supports one; otherwise start from a clean slate and read only the named inputs. Give it only file paths, never the writer's reasoning. Inputs: `<run>/01_source.txt`, `<run>/02_draft.json`, `<run>/02_check.json`, `reference/style_rules.md`, `schema/verify_raw.schema.json`. It writes only `<run>/03_verify.raw.json`.

### 5. Settle

```bash
python3 scripts/settle.py --run-dir <run>
```

- Exit 0: settled; go to Finalize.
- Exit 1: the verification broke its contract. Rerun Verify once in retry mode with the printed errors, then settle again. A second failure stops the run.
- Exit 3 (`settle: repair requested`): run the repair round below.
- Any other exit stops the run.

### 6. Repair round (at most once)

1. Write in repair mode (`stages/write.md`) with `<run>/04_repair.json` added to its inputs. It writes `<run>/02_draft.r2.raw.json`.
2. `python3 scripts/check_draft.py --run-dir <run> --round 2` (one Write retry on failure).
3. Verify in a fresh sub-agent with `<run>/02_draft.r2.json` and `<run>/02_check.r2.json` in place of the round-1 files. It writes `<run>/03_verify.r2.raw.json`.
4. `python3 scripts/settle.py --run-dir <run> --round 2` (one Verify retry on exit 1). Exit 3 or any other failure in round 2 stops the run.

### 7. Finalize

```bash
python3 scripts/finalize.py --run-dir <run>
```

Finalization is assertion-only. It writes `<run>/05_plan.final.json` and `<run>/report.md`. Any failure stops the run.

## Retry Budget

Per round: Write at most twice (one retry after a failed check), Verify at most twice (one retry after settle exit 1). One repair round per run. Nothing else is retried.

## Present the Result

- Present only `<run>/report.md`; do not paraphrase, shorten, expand, or add to it.
- Do not expose unit ids, claims, operations, flags, or other pipeline internals.
- Only when the user asks, after successful finalization:
  - structured data: `<run>/05_plan.final.json`;
  - glossary: follow `stages/glossary.md`, then run `python3 scripts/glossary_check.py --run-dir <run>`;
  - printable HTML: `python3 scripts/render_html.py --run-dir <run>`;
  - source audit: `python3 scripts/render_audit.py --run-dir <run>`.
- An optional output failure never changes `report.md` and never justifies a host-written summary.

## Failure Behavior

- Stop on unusable input or any terminal failure above.
- Report only a short workflow error: which step failed and whether the user can retry or supply a better input.
- After a failure, show no clinical content from the source or any intermediate file, and never write your own summary instead.
- Present the report as a reading aid, not a diagnosis, prescription, or replacement for urgent medical care. Keep documents and run files local unless the user asks to share them.
