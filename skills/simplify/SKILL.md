---
name: simplify
description: Simplify visit notes, discharge summaries, lab reports, imaging reports, and other clinical documents into a plain-language, source-anchored care plan. Use when a user wants help understanding supplied medical paperwork. Do not use to diagnose, prescribe, or replace urgent medical care.
---

# Simplify Medical Documents

Turn the supplied clinical documents into a plain-language report without adding medical claims that are not present in the source.

## Core Rules

- Treat the source documents as the only authority. Never infer a diagnosis, reason, dose, cause, severity, or recommendation that the documents do not state.
- Keep every clinical statement traceable to source text through the fact ledger and `source_fact_ids`.
- Keep the patient-facing result concise and action-first. Preserve every safety-critical fact, but do not display every extracted fact.
- Put technical, repetitive, generic, and non-actionable supporting detail in the hidden audit layer rather than the patient report.
- Preserve uncertainty. Use “not stated” or an empty optional field instead of guessing.
- Keep source documents and run artifacts local unless the user explicitly asks to share them.
- Present the result as a reading aid, not medical advice or a treatment instruction.

## Inputs

Use one UTF-8 text file per source document. Extract text from PDFs, DOCX files, images, or scans with the tools available in the current environment before starting. Preserve known page boundaries with form-feed characters (`\f`). Treat all files supplied for one request as a single visit.

Paths such as `scripts/...`, `stages/...`, `reference/...`, and `schema/...` are relative to this skill directory. Resolve them when using tools; do not add a separate path-resolution or environment-checking stage to the workflow.

## Why Scripts Are Used

The model performs the language work in `stages/*.md`. The bundled Python scripts handle deterministic operations that should not be improvised: source line numbering, schema validation, citation checks, numeric parity, bounded correction checks, audit logging, and rendering. Run the required command directly. If the environment cannot execute it, report that limitation and stop rather than recreating the check by hand.

## Stage Protocol

For each model stage:

1. Read only the named stage prompt and its named inputs, references, and schema.
2. Write only the requested JSON output file.
3. Run the listed deterministic check.
4. If the check reports invalid model output, retry that stage once using the reported errors. Apply the failure behavior below if the retry also fails.

Independent stages may run in parallel when the host supports it. Otherwise run them sequentially in the order below.

## Workflow

### 1. Prepare the Run

Run:

```bash
python3 scripts/unitize.py --runs-dir <workspace>/simplify-runs --input <file> [--input <file> ...]
```

Append `:ocr` to text transcribed from an image or scan and `:pasted` to manually entered text. Native text files and text extracted from digital documents need no suffix. The final output line is the run directory; use it as `<run>` below. Read `<run>/01_units.json` to find the numbered chunk files.

### 2. Extract Facts and Glossary

- For each chunk, follow `stages/ground.md` and write `<run>/02_facts.<k>.raw.json`. Check it with `python3 scripts/anchor_check.py --run-dir <run> --chunk <k>`.
- Once per run, follow `stages/glossary.md` and write `<run>/02_glossary.raw.json`. Check it with `python3 scripts/glossary_check.py --run-dir <run>`.
- After all fact chunks pass, run `python3 scripts/merge_facts.py --run-dir <run>`.

### 3. Assemble the Draft

- Follow `stages/assemble.md` and write `<run>/03_plan.raw.json`.
- Run `python3 scripts/cite_check.py --run-dir <run>`.
- Run `python3 scripts/numeric_parity.py --run-dir <run>`. Numeric flags inform review but do not fail the run by themselves.

### 4. Review Fidelity and Critical Coverage

These reviews are independent and may run in parallel:

- Follow `stages/review_fidelity.md`, write `<run>/04_review.raw.json`, then run `python3 scripts/sanitize_review.py --run-dir <run> --only review`.
- Follow `stages/review_coverage.md`, write `<run>/04_coverage.raw.json`, then run `python3 scripts/sanitize_review.py --run-dir <run> --only coverage`. This review checks that important patient-facing facts were not omitted; it does not force every extracted detail into the report.

If either review fails twice, remove its invalid raw output and run its sanitizer once more so the audit trail records that review as skipped.

### 5. Correct and Fill Gaps

Read the correction count in `<run>/04_review.json` and the missing-critical-fact count in `<run>/04_coverage.json`.

- If corrections exist, follow `stages/correct.md` and write `<run>/05_plan.corrected.raw.json`. Run `python3 scripts/diff_guard.py --run-dir <run> --strict`; retry the stage once if needed. Then run `python3 scripts/diff_guard.py --run-dir <run>` to produce the settled corrected plan. If no corrections exist, run only the non-strict command so the stage is recorded as skipped.
- If missing critical facts exist, follow `stages/assemble_missing.md` and write `<run>/05_additions.raw.json`. Run `python3 scripts/cite_check.py --run-dir <run> --additions`. If no critical facts are missing, run the same command without creating model output so the stage is recorded as skipped.

### 6. Finalize

Run:

```bash
python3 scripts/finalize.py --run-dir <run>
```

Finalization writes `<run>/06_plan.final.json` and `<run>/report.md`, records readability telemetry internally, and records any degraded or skipped checks.

## Present the Result

- Give a concise summary of the most important next actions, medication changes or questions, tests, appointments, follow-up timing, and uncertainty explicitly present in the report.
- Link or attach `<run>/report.md` and `<run>/06_plan.final.json`. Do not expose fact IDs, line numbers, chunk counts, or other pipeline internals in the user-facing summary.
- If the user wants a printable file, run `python3 scripts/render_html.py --run-dir <run>` and provide `<run>/report.html`.
- If the user asks how statements were verified or requests sources, run `python3 scripts/render_audit.py --run-dir <run>` and provide `<run>/report.audit.md`.
- State that the output is a reading aid based on the supplied documents, not a new diagnosis or treatment instruction. For urgent symptoms, direct the user to appropriate emergency or clinical care rather than relying on the report.

## Failure Behavior

- Stop on invalid or unusable input, failed fact extraction, failed draft assembly, or failed finalization. Explain the error in plain language.
- Continue without a glossary if glossary generation fails twice.
- Continue with a recorded notice if a review fails twice.
- Fall back to the draft plan if bounded correction cannot be validated.
- Continue without additions if gap filling fails twice.
