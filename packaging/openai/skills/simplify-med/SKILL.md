---
name: simplify-med
description: Turn a clinical document (visit note, discharge summary, lab or imaging report) into a plain-language, fact-checked care plan with an audit trail. Use when a user shares medical paperwork and wants to understand it. Takes plain text you have already extracted; produces report.html and report.md in a run folder.
---

Resolve `<skill>` once, to the absolute path of the directory containing
this file. Establish `<run>` at Stage 0. Use both absolute paths in every
command below.

This is a fact-first pipeline: the document is broken into atomic facts,
each anchored to a specific source line, and only those facts are ever
assembled into the plain-language plan. Never invent a reason, dose, or
cause the document does not state -- show it as "not stated," never
guessed. The plan is reviewed and corrected against its own facts before
anyone sees it. Every interim file stays in the run folder as an audit
trail from source text to final report.

## Prerequisites

Confirm `python3 --version` runs and you can execute code. If code
execution is unavailable here, stop and tell the user this skill needs it
to run its checker scripts -- do not attempt the pipeline by hand.

## Inputs

Get one `.txt` file per source document. If given a PDF, DOCX, image, or
scan, extract its text yourself first and save it as `.txt`; insert a
form-feed (`\f`) between pages if you know the boundaries. Treat every
file given for this request as one visit. There is exactly one
simplification level -- do not ask about it. Tell the user, in one line,
that you're starting and it takes several steps.

## Running a script

Invoke a script as `python3 <skill>/scripts/<name>.py --run-dir <run>
...` (Stage 0 is the exception -- it establishes `<run>`). Every script
exits 0 whether its outcome was ok, degraded, or skipped, and exits 1
only on a fatal error or invalid input needing a retry. On exit 1, read
stderr -- it's written for a human. On exit 0, the last stdout line is a
status line `<stage>: <status> | <key>=<value> ...` (`ok`, `degraded`, or
`skipped`) -- read it instead of inspecting output files (unitize is the
one exception; see Stage 0).

## Performing an LLM stage

Read `<skill>/stages/<stage>.md` yourself and follow it exactly: it names
its own input files (its `reference/` and `schema/` files live under
`<skill>`; everything else lives under `<run>`) and its one output file.
Write only that output file, in your current context -- there is no
sub-agent to dispatch to. Do every stage below in order, one at a time;
never skip one because it feels redundant.

**Validation and one retry.** After each stage, run its check script. On
exit 1 with validator errors, redo the stage once yourself, appending:

```
Retry: the previous output failed validation. Fix exactly these errors and rewrite the output file:
<the check's stderr>
```

If it fails again, treat the stage as failed per the failure table below
and continue.

## Stage 0 -- unitize (script)

```
python3 <skill>/scripts/unitize.py --runs-dir <cwd>/simplify-runs --input <file> [--input <file> ...]
```

Append `:ocr` to a file transcribed from an image or scan, `:pasted` to
typed/pasted text; otherwise nothing (default `native`) -- this only
labels the audit trail. The last stdout line is `<run>`; resolve it and
use it for everything below (unitize's status line prints too, but as
the second-to-last line). Read `<run>/01_units.json`'s `chunks` array for
the chunk count K. Exit 1 is fatal: explain the input problem in plain
words (an empty file or one with no usable text).

## Stage 1 -- ground and glossary

For each chunk `k` in 1..K: perform stage `stages/ground.md` -> output
`<run>/02_facts.<k>.raw.json`; check `python3
<skill>/scripts/anchor_check.py --run-dir <run> --chunk <k>`.

Also perform stage `stages/glossary.md` once (inputs: every chunk's units file)
-> output `<run>/02_glossary.raw.json`; check `python3
<skill>/scripts/glossary_check.py --run-dir <run>`.

When every ground chunk is checked (and retried if needed), run:

```
python3 <skill>/scripts/merge_facts.py --run-dir <run>
```

Exit 1 is fatal: tell the user, in plain words, the document could not be
read into facts (quote stderr).

## Stage 2 -- assemble

Perform stage `stages/assemble.md` -> output `<run>/03_plan.raw.json`; check
`python3 <skill>/scripts/cite_check.py --run-dir <run>` (writes
`<run>/03_plan.draft.json`). Fatal after one retry -- stop and explain.

Then always run:

```
python3 <skill>/scripts/numeric_parity.py --run-dir <run>
```

(writes `<run>/03_flags.json`; never fails the run).

## Stage 3 -- review

Perform stage `stages/review_fidelity.md` -> output `<run>/04_review.raw.json`;
check `python3 <skill>/scripts/sanitize_review.py --run-dir <run> --only
review`.

Perform stage `stages/review_coverage.md` -> output
`<run>/04_coverage.raw.json`; check `python3
<skill>/scripts/sanitize_review.py --run-dir <run> --only coverage`.

If a stage fails twice, delete its raw output file if present, then run
its `sanitize_review` command anyway (it records that side as skipped).

## Stage 4 -- correct and fill gaps

Read `<run>/04_review.json`'s `corrections` count and
`<run>/04_coverage.json`'s `missing` count first.

**Correct.** If `corrections` > 0: perform stage `stages/correct.md` -> output
`<run>/05_plan.corrected.raw.json`; check `python3
<skill>/scripts/diff_guard.py --run-dir <run> --strict`, retrying once on
exit 1 with the reported violation paths. Then always run `python3
<skill>/scripts/diff_guard.py --run-dir <run>` (no `--strict`) to settle
-- it writes `<run>/05_plan.corrected.json`. If `corrections` == 0: skip
the stage and run the no-`--strict` command directly (records skipped).

**Fill gaps.** If `missing` > 0: perform stage `stages/assemble_missing.md` ->
output `<run>/05_additions.raw.json`; check `python3
<skill>/scripts/cite_check.py --run-dir <run> --additions`. If `missing`
== 0: skip the stage and run that same check command directly (records
skipped).

## Stage 5 -- finalize (script)

```
python3 <skill>/scripts/finalize.py --run-dir <run>
```

Stdout gives, one per line: the HTML report path, the Markdown report
path, the reading-level line, any notices, then the `finalize: ...`
status line last (not a notice). Exit 1 is fatal -- show its stderr text.

## Present results

- Give a concise native summary: the most important next actions,
  medication changes or questions, tests, appointments, follow-up
  timing, and any uncertainty explicitly present in the report. State
  this is a reading aid based on the supplied documents, not a new
  diagnosis or treatment instruction.
- Attach or link `<run>/06_plan.final.json`, `<run>/report.md`, and
  `<run>/report.html`. Never paste the plan into chat, and never mention
  fact ids, line numbers, chunk counts, or other run internals.
- If asked how a statement was verified, or for sources, run:

  ```
  python3 <skill>/scripts/render_audit.py --run-dir <run>
  ```

  and point to `<run>/report.audit.md`.

## Failure table

| Stage | On failure |
|---|---|
| unitize | Stop; explain the input problem. |
| ground | Stop; the document could not be read into facts. |
| glossary | Continue without a glossary. |
| assemble | Stop; explain the failure. |
| review-fidelity / review-coverage | Continue; recorded as skipped; finalize adds a notice. |
| correct | The diff guard falls back to the draft plan and adds a notice. |
| assemble-missing | Continue without additions. |
| finalize | Stop; show its error text. |

## Run folder

Each run lives in `<cwd>/simplify-runs/<run-id>/` and contains numbered
stage files (`01_units.json` ... `06_plan.final.json`), `run.json` (the
audit trail: per-stage status, attempts, checks), and the three reports:
`report.md`, `report.html`, and, on request, `report.audit.md`.
Everything stays on the user's machine; deleting the folder removes all
traces of the run.
