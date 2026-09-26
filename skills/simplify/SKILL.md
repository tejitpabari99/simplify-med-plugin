---
name: simplify
description: Turn a clinical document (visit note, discharge summary, lab or imaging report) into a plain-language, fact-checked care plan with an audit trail. Use when a user shares medical paperwork and wants to understand it. Takes plain text you have already extracted; produces report.html and report.md in a run folder.
---

Resolve `<skill>` once, at the start, to the absolute path of the directory
containing this file (`skills/simplify/` in a plugin checkout). Every
run also has a `<run>` directory, resolved once you have it (Stage 0
prints it). Use these two absolute paths in every command and every
dispatch message below -- never a relative path.

If `<skill>/custom_start.md` exists, read it now and follow its
platform-specific instructions before Stage 0. If it does not exist or is
empty, continue unchanged.

## 1. What this does

This is a fact-first pipeline: a clinical document is first broken into
atomic facts, each one anchored to a specific line of the source text, and
only those facts are ever assembled into a plain-language care plan.
Nothing is invented -- a reason, dose, or cause that the document does not
state is shown to the patient as "not stated," never guessed. The plan is
reviewed and corrected against its own facts before it is shown to anyone.
Every interim file the pipeline writes is kept in the run folder as an
audit trail from source text to final report.

## 2. Before you start

- Confirm `python3 --version` runs.
- Get the input as one or more `.txt` files, one per source document. If
  the user supplied a PDF, DOCX, image, or scan, extract its text with
  your own tools first and save the result as `.txt`. If page boundaries
  are known, insert a form-feed character (`\f`) between pages.
- Treat every file the user gave you for this request as one visit.
- Do not ask the user about a simplification level -- there is exactly one.
- Tell the user, in one line, that you are starting and that it takes
  several steps.

## 3. How to run a script

Always invoke a script as `python3 <skill>/scripts/<name>.py --run-dir
<run> ...` (the one exception is Stage 0, which establishes `<run>`
itself). Every script exits 0 whether its own outcome was ok, degraded, or
skipped, and exits 1 only on a fatal error or an invalid agent output that
needs a retry. On exit 1, read stderr -- it is written for a human. On exit
0, the last line of stdout is always a status line of the shape `<stage>:
<status> | <key>=<value> ...`, where `<status>` is `ok`, `degraded`, or
`skipped` -- read it to know what happened without inspecting output files
(Stage 0's unitize is the one exception; see section 5).

## 4. How to dispatch an LLM stage

If you can dispatch sub-agents, dispatch the agent named `simplify-med-<stage>`
(defined under `agents/`) with this exact message shape. This plugin
registers these agents; their definitions are at `<plugin>/agents/<stage>.md`
(`<plugin>` being the parent directory of `skills/`, a sibling of `skills/`,
not a child of `<skill>`) -- if agents are not auto-registered for you, read
this file yourself and use it as the sub-agent's system prompt.

```
Stage file: <skill>/stages/<stage>.md
Inputs: <absolute paths, one per line>
Output: <absolute path>
Reference dir: <skill>/reference
Schema dir: <skill>/schema
```

Run every task of a parallel group at the same time when you can run tasks
in parallel, respecting any concurrency limit you have. Otherwise, read
the stage file yourself and perform the stage in the current context,
writing the output file, one stage at a time, in the same order as below
-- never skip a stage because it feels redundant.

**Validation and one retry.** After each agent task, run its check
script. If the check exits 1 with validator errors, re-dispatch the same
agent ONCE, with the dispatch message suffixed:

```
Retry: the previous output failed validation. Fix exactly these errors and rewrite the output file:
<the check's stderr>
```

If it fails again, treat the stage as failed per the failure table in
section 12 and continue.

## 5. Stage 0 -- unitize (script)

```
python3 <skill>/scripts/unitize.py --runs-dir <cwd>/simplify-runs --input <file> [--input <file> ...]
```

Append `:ocr` to a file you transcribed from an image or scanned page,
`:pasted` to text the user typed or pasted; otherwise nothing (default
`native`). This only labels the audit trail.

The last line of stdout is `<run>` -- resolve it to an absolute path and
use it for everything below. This is unitize's one exception to section
3's status-line rule: its status line is printed too, but as the
second-to-last stdout line, immediately before `<run>`, so that `<run>`
can stay the last line. Read `<run>/01_units.json`'s `chunks` array
to learn the chunk count K. On exit 1, this is fatal: stop and explain the
input problem in plain words (an empty file or a file with no usable
text).

## 6. Stage 1 -- ground and glossary (parallel group A)

Dispatch K ground tasks, one per chunk `k` in 1..K:

- Agent `simplify-med-ground`, stage file `<skill>/stages/ground.md`.
- Inputs: `<run>/01_units.<k>.txt`, `<skill>/reference/categories.md`,
  `<skill>/reference/abbreviations.json`.
- Output: `<run>/02_facts.<k>.raw.json`.
- Check: `python3 <skill>/scripts/anchor_check.py --run-dir <run> --chunk <k>`.

Alongside them, dispatch one glossary task:

- Agent `simplify-med-glossary`, stage file `<skill>/stages/glossary.md`.
- Inputs: every `<run>/01_units.<k>.txt` for this run.
- Output: `<run>/02_glossary.raw.json`.
- Check: `python3 <skill>/scripts/glossary_check.py --run-dir <run>`.

When every ground task has been checked (and retried if needed), run:

```
python3 <skill>/scripts/merge_facts.py --run-dir <run>
```

Exit 1 here is fatal: stop and tell the user, in plain words, that the
document could not be read into facts (quote stderr).

## 7. Stage 2 -- assemble (sequential)

- Agent `simplify-med-assemble`, stage file `<skill>/stages/assemble.md`.
- Inputs: `<run>/02_facts.txt`, `<skill>/reference/style_rules.md`,
  `<skill>/reference/ahrq_plain_language.json`,
  `<skill>/schema/care_plan_agent.schema.json`.
- Output: `<run>/03_plan.raw.json`.
- Check: `python3 <skill>/scripts/cite_check.py --run-dir <run>` (writes
  `<run>/03_plan.draft.json`). Fatal after one retry -- stop and explain.

Then always run:

```
python3 <skill>/scripts/numeric_parity.py --run-dir <run>
```

(writes `<run>/03_flags.json`; this check never fails the run).

## 8. Stage 3 -- review (parallel group B)

- Agent `simplify-med-review-fidelity`, stage file
  `<skill>/stages/review_fidelity.md`. Inputs: `<run>/02_facts.txt`,
  `<run>/03_plan.draft.json`, `<run>/03_flags.json`. Output:
  `<run>/04_review.raw.json`. Check:
  `python3 <skill>/scripts/sanitize_review.py --run-dir <run> --only review`.
- Agent `simplify-med-review-coverage`, stage file
  `<skill>/stages/review_coverage.md`. Inputs: `<run>/02_facts.txt`,
  `<run>/03_plan.draft.json`. Output: `<run>/04_coverage.raw.json`. Check:
  `python3 <skill>/scripts/sanitize_review.py --run-dir <run> --only coverage`.

If an agent fails twice, delete its raw output file if one exists, then
run its `sanitize_review` command anyway (it will write the sanitized
file with that side recorded as skipped).

## 9. Stage 4 -- correct and fill gaps (parallel group C)

Read `<run>/04_review.json`'s `corrections` count and
`<run>/04_coverage.json`'s `missing` count first.

**C1 -- correct.** If `corrections` > 0: dispatch agent
`simplify-med-correct`, stage file `<skill>/stages/correct.md`. Inputs:
`<run>/03_plan.draft.json`, `<run>/04_review.json`,
`<skill>/reference/style_rules.md`. Output:
`<run>/05_plan.corrected.raw.json`. Check:
`python3 <skill>/scripts/diff_guard.py --run-dir <run> --strict`; on exit
1, retry once with the reported violation paths. Then, regardless, run
`python3 <skill>/scripts/diff_guard.py --run-dir <run>` (no `--strict`) to
settle -- it writes `<run>/05_plan.corrected.json`.
If `corrections` == 0: skip the agent and just run
`python3 <skill>/scripts/diff_guard.py --run-dir <run>` directly (it
records the stage as skipped).

**C2 -- assemble-missing.** If `missing` > 0: dispatch agent
`simplify-med-assemble-missing`, stage file
`<skill>/stages/assemble_missing.md`. Inputs: `<run>/02_facts.txt`,
`<run>/03_plan.draft.json`, `<run>/04_coverage.json`,
`<skill>/reference/style_rules.md`,
`<skill>/schema/additions_raw.schema.json`. Output:
`<run>/05_additions.raw.json`. Check:
`python3 <skill>/scripts/cite_check.py --run-dir <run> --additions`.
If `missing` == 0: skip the agent and just run
`python3 <skill>/scripts/cite_check.py --run-dir <run> --additions`
directly (it records the stage as skipped).

## 10. Stage 5 -- finalize (script)

```
python3 <skill>/scripts/finalize.py --run-dir <run>
```

Stdout gives, one per line: the HTML report path, the Markdown report
path, the reading-level line, then any notices, then (per section 3) the
`finalize: ...` status line as the last line -- that last line is not a
notice. Exit 1 is fatal -- show the user its stderr text.

After finalization succeeds, if `<skill>/custom_end.md` exists, read it and
follow its platform-specific result-presentation instructions before
presenting the results. If it does not exist or is empty, continue unchanged.

## 11. What to tell the user

Give the two report paths (`report.html` is one file that opens in any
browser, works offline, and has tick-boxes that remember their state;
`report.md` has the same content as text); the reading-level line
verbatim; each notice verbatim; and one sentence that this is a reading
aid, not medical advice. Do NOT paste the plan into chat, and do NOT
mention fact ids, line numbers, chunk counts, or any other run internals.
If you can offer file downloads, offer `report.html` and
`report.md`. If the user asks how a statement was verified, or wants
sources, run:

```
python3 <skill>/scripts/render_audit.py --run-dir <run>
```

and point them to `<run>/report.audit.md`.

## 12. Failure table

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

## 13. Run folder

Each run lives in `<cwd>/simplify-runs/<run-id>/` and contains numbered
stage files (`01_units.json` ... `06_plan.final.json`), `run.json` (the
audit trail: per-stage status, attempts, checks), and the three reports:
`report.md`, `report.html`, and, on request, `report.audit.md`. Everything
in it stays on the user's machine; deleting the folder removes all traces
of the run.
