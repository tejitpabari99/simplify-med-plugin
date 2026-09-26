---
name: simplify
description: Simplify visit notes, discharge summaries, lab reports, imaging reports, and other clinical documents into a plain-language, source-anchored care plan. Use when a user wants help understanding supplied medical paperwork. Do not use to diagnose, prescribe, or replace urgent medical care.
---

# Simplify Medical Documents

Turn supplied clinical documents into a concise, critical-first, plain-language report without adding claims that are not present in the source.

## Non-Negotiable Execution Contract

When this skill is selected or explicitly invoked, execute the complete workflow below. Never simplify, summarize, or answer directly from the supplied documents.

Do not present clinical content until finalization succeeds and the current run contains validated `06_plan.final.json` and `report.md` artifacts. Every expected grounding chunk, deterministic plan check, combined independent review, deterministic settlement, and final validation is mandatory. A required stage may not be silently skipped, degraded, or replaced with an ordinary response.

Each model stage gets one retry for invalid JSON, schema failure, or deterministic validation failure. If a required stage still fails after its allowed retry, stop and report the workflow failure without providing a substitute medical summary.

Present only `<run>/report.md` as the default clinical response. Do not create a second summary from the source documents, fact ledger, draft, review, or final JSON. Provide other artifacts only when the user requests them and only after successful finalization.

## Core Rules

- Treat the source documents as the only authority. Never infer a diagnosis, reason, dose, cause, severity, urgency, or recommendation that the documents do not state.
- Keep every visible clinical statement traceable through `source_fact_ids`.
- Keep the patient-facing result concise and action-first. Preserve every critical patient-specific fact, but do not display every extracted fact.
- Keep generic education, technical mechanics, duplicate details, routine non-actionable information, and stable background out of the patient report unless they change this patient's understanding, action, or safety.
- Record every supporting fact as an audited omission rather than discarding it or forcing it into the report.
- Preserve negation, uncertainty, conditions, medication status, timing, numbers, units, and documented urgency.
- Use “not stated” or an empty optional field instead of guessing.
- Keep source documents and run artifacts local unless the user explicitly asks to share them.
- Present the finalized report as a reading aid, not a diagnosis, prescription, or replacement for urgent medical care.

## Inputs

Use one UTF-8 text file per source document. Extract text from PDFs, DOCX files, images, or scans with the tools available in the current environment before starting. Preserve known page boundaries with form-feed characters (`\f`). Treat all files supplied for one request as a single visit.

Paths such as `scripts/...`, `stages/...`, `reference/...`, and `schema/...` are relative to this skill directory. Resolve them when using tools; do not add a separate path-resolution or environment-checking stage.

## Deterministic Boundary

The model performs only three core responsibilities: `ground[1..K]`, `assemble`, and `combined independent review`. The Python scripts perform source unitization, anchoring, schema validation, citation and omission checks, numeric parity, exact bounded settlement, run logging, rendering, and final validation. Run each required command directly. If the environment cannot execute a required command, report the workflow failure and stop rather than recreating the check by hand.

The current model contracts are `schema/facts_raw.schema.json`, `schema/care_plan_agent.schema.json`, and `schema/review_raw.schema.json`. Deterministic artifacts also validate against `schema/units.schema.json`, `schema/facts.schema.json`, `schema/flags.schema.json`, `schema/review.schema.json`, `schema/care_plan.schema.json`, and `schema/run.schema.json`.

## Model Stage Protocol

For each model-stage invocation:

1. Read only the named stage prompt and its named inputs, references, and schema.
2. Write only the requested JSON output file; never answer the user from the stage.
3. Run the listed deterministic check.
4. On invalid output, retry that stage once using the exact validator errors.
5. If the retry fails, stop the workflow without clinical output.

Grounding chunks may run in parallel. Assembly starts only after every expected chunk passes and the fact ledger is merged. Review starts only after the draft passes citation, disposition, and numeric checks.

## Required Workflow

The clean core graph is:

```text
UNITIZE
  -> ground[1..K]
  -> ANCHOR_CHECK each chunk -> MERGE_FACTS
  -> assemble
  -> CITE_AND_DISPOSITION_CHECK + NUMERIC_PARITY
  -> combined independent review
  -> deterministic settlement
  -> FINALIZE
  -> optional post-finalization outputs
```

This is `K + 2` model calls on the clean path: one call per grounding chunk, one assembly call, and one review call.

### 1. Prepare the Run

Run:

```bash
python3 scripts/unitize.py --runs-dir <workspace>/simplify-runs --input <file> [--input <file> ...]
```

Append `:ocr` to text transcribed from an image or scan and `:pasted` to manually entered text. Native text files and text extracted from digital documents need no suffix. The final output line is `<run>`. Read `<run>/01_units.json` to identify every numbered `<run>/01_units.<k>.txt` chunk.

### 2. Ground Every Chunk

For each expected chunk:

1. Follow `stages/ground.md` using the chunk and `schema/facts_raw.schema.json`.
2. Write only `<run>/02_facts.<k>.raw.json`.
3. Run `python3 scripts/anchor_check.py --run-dir <run> --chunk <k>`.
4. Retry only that grounding chunk once if the check fails.

All expected chunks must pass. Then run:

```bash
python3 scripts/merge_facts.py --run-dir <run>
```

Do not continue unless `<run>/02_facts.json` is valid for the current run.

### 3. Assemble the Concise Draft

Follow `stages/assemble.md` using `<run>/02_facts.json`, `reference/style_rules.md`, `reference/ahrq_plain_language.json`, and `schema/care_plan_agent.schema.json`. Write only `<run>/03_plan.raw.json`.

Run:

```bash
python3 scripts/cite_check.py --run-dir <run>
python3 scripts/numeric_parity.py --run-dir <run>
```

The draft must be concise and critical-first. Every verified fact must be represented by visible cited content or exactly one audited omission disposition. Generic education is not patient-specific merely because it appeared in discharge paperwork. Retry assembly once if schema, citation, disposition, or numeric preparation fails. Do not continue unless `<run>/03_plan.draft.json` and `<run>/03_flags.json` are valid for the current run.

### 4. Run the Combined Independent Review

Follow `stages/review.md` using `<run>/02_facts.json`, `<run>/03_plan.draft.json`, `<run>/03_flags.json`, `reference/style_rules.md`, and `schema/review_raw.schema.json`. Write only `<run>/04_review.raw.json`.

The review must independently examine every fact and omission; check fidelity, negation, uncertainty, medication status, urgency, and critical-vs-supporting relevance; resolve every numeric flag; and emit only bounded operations or `reassemble_fact_ids`. Retry the review once if its output is invalid.

### 5. Settle or Reassemble Once

Run:

```bash
python3 scripts/settle_review.py --run-dir <run>
```

Settlement must apply every accepted operation exactly, rerun citation and disposition checks, resolve numeric flags, and write valid `<run>/04_review.json` and `<run>/05_plan.settled.json`.

If the review requests critical missing content, settlement must stop. Reassemble once using only the accepted draft, the relevant verified facts, and the requested fact IDs. Make the smallest patient-facing change needed, rerun `scripts/cite_check.py` and `scripts/numeric_parity.py`, then run a fresh independent review with `stages/review.md` and settle it with `scripts/settle_review.py`. New patient-facing prose must never bypass review. A second reassembly request fails the run.

There is no correction rewrite, additions stage, skipped-review path, degraded core stage, draft fallback, or unbounded repair loop.

### 6. Finalize

Run:

```bash
python3 scripts/finalize.py --run-dir <run>
```

Finalization is assertion-only. It must verify current-run identity, required stage statuses, required artifacts, schemas, citations, fact dispositions, numeric resolutions, and settled content. It reads only `<run>/05_plan.settled.json` and writes validated `<run>/06_plan.final.json` and `<run>/report.md`. Any missing, failed, degraded, stale, or invalid core state prevents publication.

## Clean Artifact Contract

A clean one-chunk run has approximately 13 core artifacts:

```text
run.json
01_units.json
01_units.1.txt
02_facts.1.raw.json
02_facts.json
03_plan.raw.json
03_plan.draft.json
03_flags.json
04_review.raw.json
04_review.json
05_plan.settled.json
06_plan.final.json
report.md
```

Additional chunk files and attempt-suffixed failed raw outputs are expected when applicable. Retain raw facts, draft, and review outputs for auditability, but never expose pipeline internals in the patient-facing response.

## Present the Result

- Present only `<run>/report.md`; do not paraphrase, shorten, expand, or independently summarize it.
- Do not expose fact IDs, omitted-fact records, line numbers, chunk counts, review operations, flags, or other pipeline internals in the default response.
- Provide `<run>/06_plan.final.json` only when the user explicitly requests structured data.
- Generate glossary, HTML, or audit views only after successful finalization and only when requested.
- For a requested glossary, follow `stages/glossary.md` against finalized visible content and validate it with `scripts/glossary_check.py`.
- For printable HTML, run `python3 scripts/render_html.py --run-dir <run>`.
- For verification details, run `python3 scripts/render_audit.py --run-dir <run>`.

Optional output failure must not alter the immutable final plan or replace `<run>/report.md` with a host-authored summary.

## Failure Behavior

- Stop on invalid or unusable input, any grounding chunk that fails its retry, merge failure, assembly failure, review failure, settlement failure, a second reassembly request, or finalization failure.
- Report only a concise workflow error explaining which stage failed and whether the user can retry or provide a usable input.
- Do not reveal clinical content from the source or intermediate artifacts after a terminal failure.
- Do not silently skip, degrade, synthesize, repair by hand, or substitute any required core stage.
- Never fall back to a draft or provide a substitute clinical summary.
