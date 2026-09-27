# simplify-med — architecture

This document describes the implemented schema-3.0 pipeline: its execution
contract, two model calls, deterministic safeguards, run artifacts, and
rendering. Read [overview.md](overview.md) first for the patient-facing
behavior. The design rationale and evidence are in
`agent_files/claude-busy-gauss-okyysq-2026-09-26/` (`PRD.md`, `research.md`).

## Principles

- **Explicit invocation.** The `simplify` skill is not implicitly invoked.
  Once selected, it runs the complete workflow rather than answering with an
  ad hoc summary.
- **Write the short report, then verify what is shown.** The writer works
  directly from the numbered source; the work scales with the report, not with
  the chart. There is no fact ledger.
- **Cite units, not quotes.** Every visible item carries source unit ids;
  scripts check the ids and numbers, and the verifier checks the meaning.
- **Protected content is never silently dropped.** A high-recall keyword scan
  finds candidate units for six protected categories; each uncited candidate
  must be dismissed by the verifier with a reason or shown after one repair.
- **Independent verification.** A second model call, ideally in a fresh
  sub-agent, checks every visible item against the original source.
- **Fail closed.** A missing, failed, stale, or invalid core step prevents
  clinical output. There is no draft fallback and no host-written summary.
- **Immutable default output.** The default clinical response is the
  finalized `report.md`.

## Repository layout

```text
plugin.json                    portable OpenAI plugin manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build.py                       allowlist-based OpenAI ZIP builder
skills/simplify/
  SKILL.md                     invocation contract and workflow
  agents/openai.yaml           UI metadata and explicit-invocation policy
  assets/                      skill icons
  stages/                      write, verify, optional glossary
  scripts/                     deterministic pipeline and renderers
  schema/                      schema-3.0 data contracts
  reference/                   style rules and optional lookups
  templates/                   optional HTML report template
mcp/openai/                    parked widget; excluded from ZIP; not yet
                               updated to the current plan shape
tests/                         deterministic, integration, and package tests
docs/                          documentation and design history
simplify-runs/                 gitignored run folders
```

The distributable ZIP contains only `plugin.json`,
`.codex-plugin/plugin.json`, and `skills/`.

## Stage graph

```text
UNITIZE      scripts/unitize.py            (script)
  -> WRITE   stages/write.md               (model call 1)
  -> CHECK   scripts/check_draft.py        (script)
  -> VERIFY  stages/verify.md              (model call 2, independent)
  -> SETTLE  scripts/settle.py             (script)
       exit 3 = repair requested -> one repair round
                (WRITE -> CHECK -> VERIFY -> SETTLE, --round 2)
  -> FINALIZE scripts/finalize.py          (script) -> 05_plan.final.json + report.md
  -> optional glossary / HTML / audit
```

Clean path: two model calls and four script runs. Write may be retried once
per round when the check fails; verify may be retried once per round when
settlement rejects its contract. One repair round at most. Any second failure
stops the run without clinical output.

## Steps

### Unitize

`unitize.py` creates a fresh run identity, copies inputs under `00_input/`,
records SHA-256 input metadata in `run.json`, and numbers every non-blank line
as a unit in `01_units.json`. Lines that are only a URL, page counters, and
exact repeats (portal headers, footers, duplicated pages) are marked `skip`
and are never valid citations; a repeated line that matches a protected-content
pattern is never skipped. `01_source.txt` lists every non-skipped unit as
`[<id>] <text>` with file/page header lines. `protected.py` scans the units
and writes `01_protected.json`: candidate unit ids for `medication_changes`,
`follow_up`, `return_precautions`, `diagnoses`, `disposition`, and
`abnormal_or_pending_results`. The host never reads `01_units.json`.

### Write

`stages/write.md` reads `01_source.txt`, `01_protected.json`,
`reference/style_rules.md`, and `schema/draft.schema.json`, and writes
`02_draft.raw.json`. The draft has fixed slots: `visit_type`, `why_you_went`,
`findings_lead`, `findings[]` (one bottom-line bullet per test or exam area),
`diagnoses[]`, `disposition`, `next_steps[]`, `medicines` (changes or a
source-stated none-statement), `return_precautions[]`, `questions[]`, and a
`coverage` entry per protected category (`shown` or `none_in_source`). Every
visible item cites at least one unit. The prompt carries the SHOW/SKIP
selection rules and the anti-patterns seen in real runs.

### Check

`check_draft.py` validates the draft schema, that every cited unit exists and
is not skipped, that each `shown` coverage category is backed by a visible
item, and that visible text has no empty brackets or clinician names. It writes
`02_draft.json` and `02_check.json`: the visible word count against the budget
(target 300, warn 350, max 500; above max fails), numeric flags for number
tokens not found in an item's cited units, and protected candidates no visible
item cites.

### Verify

`stages/verify.md` reads `01_source.txt`, `02_draft.json`, `02_check.json`,
`reference/style_rules.md`, and `schema/verify_raw.schema.json`, and writes
`03_verify.raw.json` with four parts:

- **claims**: one per visible item path (`findings[2]`, `why_you_went`,
  `medicines.none_statement`, ...) — `supported`, `needs_correction`, or
  `unsupported`;
- **operations**: `replace` (a visible string field), `clear` (an optional
  item or `plain_name`), or `remove` (an array item, reason `unsupported`,
  `noise`, or `duplicate`), including trimming when the draft is over budget;
- **numeric resolutions**: each flag `equivalent`, `corrected`, or `removed`;
- **protected units**: each uncited candidate `covered`, `not_needed` with a
  reason, or `missing`.

The verifier adds no items; missing content goes only through `missing`.

### Settle

`settle.py` validates the verification contract (every visible path claimed
once, every flag and uncited candidate resolved once, operations on existing
paths, non-supported claims edited) and applies operations exactly, removals
from the highest index down. It re-asserts schema validity, protected
coverage, numeric parity, and the word maximum. Exit codes: `0` settled
(`03_verify.json`, `04_plan.settled.json`); `1` contract errors for the one
verify retry; `3` repair requested (round 1 only, `04_repair.json`). A
`missing` result in round 2 fails the run.

### Repair round

The writer receives `04_repair.json` (the missing units and the settled
draft), keeps the settled draft, adds only what is missing, and writes
`02_draft.r2.raw.json`. Check, a fresh verification of the whole repaired
draft, and settlement then run with `--round 2`.

### Finalize

`finalize.py` is assertion-only: current run identity everywhere, core stages
`unitize`, `write`, `check`, `verify`, and `settle` ok for the final round,
schema-valid artifacts, and a PII sweep. It writes `05_plan.final.json`
(settled plan plus versions, run id, timestamp, word count, and readability
score) and `report.md`.

## Visible paths

`scripts/plan_paths.py` is the single definition of what the patient sees, in
report order: `why_you_went`, `findings_lead`, `findings[i]`, `diagnoses[i]`,
`disposition`, `next_steps[i]`, `medicines.items[i]`,
`medicines.none_statement`, `return_precautions[i]`, `questions[i]`. The
check, settlement, renderers' word count, and verifier claims all use these
paths.

## Clean artifact contract

```text
run.json
00_input/<files>
01_units.json          all units incl. skipped (audit)
01_source.txt          numbered source the models read
01_protected.json      protected candidate units
02_draft.raw.json      WRITE output
02_draft.json          checked draft
02_check.json          budget, numeric flags, uncited protected units
03_verify.raw.json     VERIFY output
03_verify.json         settled verification record
04_plan.settled.json
05_plan.final.json
report.md
```

A repair round adds `04_repair.json`, `02_draft.r2.raw.json`,
`02_draft.r2.json`, `02_check.r2.json`, `03_verify.r2.raw.json`, and
`03_verify.r2.json`. Failed attempts keep an `.attempt1` suffix.

## Data contracts

Schemas in `skills/simplify/schema/`: `units`, `protected`, `draft` (writer
contract), `draft_checked` (`02_draft.json` and `04_plan.settled.json`),
`check`, `verify_raw` (verifier contract), `verify`, `plan` (final plan),
`run`, and the optional `glossary_raw` and `glossary`. Run-log core stages are
`unitize`, `write`, `check`, `verify`, `settle`, and `finalize`, with statuses
`ok` or `failed`, plus `repair_requested` for `settle`.

## Default and optional outputs

`report.md` is the only default clinical output. `plan_view.py` builds the
sections from the final plan and `render_md.py` renders them without another
model rewrite. After successful finalization, the user may request:

- **Glossary:** `stages/glossary.md` works only from visible finalized text;
  `glossary_check.py` validates it.
- **HTML:** `render_html.py` writes `report.html`.
- **Audit:** `render_audit.py` writes `report.audit.md`: each visible item
  followed by its cited source lines with file, page, and line.

Optional output failure never changes the final plan and never authorizes a
host-authored substitute summary.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

The suite covers each deterministic step, an end-to-end run on the synthetic
ER fixture (hand-written draft and verification), the repair round and failure
paths, renderers, stage documentation, skill consistency, and package
contents. Latency and token use are not benchmarked by the suite.

## Known gaps

- The parked `mcp/openai/` widget still reads the old plan shape.
- Very long packets that exceed one model call's context need a map pre-pass
  (not implemented).
