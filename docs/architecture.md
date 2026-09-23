# simplify-med — architecture

A deep dive into the pipeline: the run folder, the stage graph, every
deterministic check by name, the data contracts, the stage prompts,
rendering, testing, and known gaps. Read [overview.md](overview.md) first
for the patient-facing picture; this document is for someone changing or
porting the pipeline.

## Principles

- **Fact-first.** Nothing reaches the plan without first being an atomic
  fact anchored to a line of the source text.
- **Extraction before generation.** The assemble agent never sees the
  original document, only the fact ledger.
- **Deterministic wherever possible.** Every LLM stage is followed by a
  script that validates its output against a JSON Schema and applies
  mechanical guards; scripts never call an LLM.
- **File handoffs.** Every stage reads named input files and writes one
  named output file; no stage holds the whole pipeline's state at once.
- **Prefer passing over failure, with a notice.** Only `unitize`, `ground`,
  `assemble` failing stops a run; everything else degrades with a notice.
- **Audit trail.** Every interim file stays in the run folder; every script
  appends its result to `run.json`.

## Repository layout

```
plugin.meta.json               source of truth for name/version/description/schema_version
.claude-plugin/plugin.json     Claude Code manifest (version must match plugin.meta.json)
build.py                       root dispatcher for platform packages
skills/simplify-med/           the portable Agent Skill (SKILL.md + bundled files)
  SKILL.md                     orchestration: stage list, file handoffs, parallel groups, fallback
  stages/                      one prompt per LLM stage
  scripts/                     stdlib-only Python: the deterministic pipeline
  schema/                      JSON Schema for every interim and final file
  reference/                   style rules, category checklist, abbreviation/plain-language dictionaries
  templates/                   report.html
agents/                        thin Claude Code agent definitions, one per LLM stage
packaging/                     shared staging plus per-platform profiles/overlays
mcp/openai/                    presentation-only MCP server and ChatGPT report widget
tests/                         unittest modules and fixtures
docs/                          this documentation suite, plus agent_files/ (design history)
simplify-runs/                 gitignored; one folder per run
```

## The run folder

Files in write order, script or agent that writes them, and the schema
each is checked against (schemas live in `skills/simplify-med/schema/`):

| File | Written by | Schema |
|---|---|---|
| `00_input/<file>.txt` | `unitize.py` (copy of each input file) | — |
| `00_input/manifest.json` | `unitize.py` | `manifest` |
| `01_units.json` | `unitize.py` | `units` |
| `01_units.<k>.txt` | `unitize.py` (one per chunk) | — |
| `02_facts.<k>.raw.json` | `ground` agent (one per chunk) | `facts_raw` |
| `02_glossary.raw.json` | `glossary` agent | `glossary_raw` |
| `02_facts.json` / `.txt` | `merge_facts.py` | `facts` |
| `02_glossary.json` | `glossary_check.py` | `glossary` |
| `03_plan.raw.json` | `assemble` agent | `care_plan_agent` |
| `03_plan.draft.json` | `cite_check.py` | `care_plan` |
| `03_flags.json` | `numeric_parity.py` | `flags` |
| `04_review.raw.json` | `review-fidelity` agent | `review_raw` |
| `04_coverage.raw.json` | `review-coverage` agent | `coverage_raw` |
| `04_review.json` | `sanitize_review.py --only review` | `review` |
| `04_coverage.json` | `sanitize_review.py --only coverage` | `coverage` |
| `05_plan.corrected.raw.json` | `correct` agent (skip if 0 corrections) | `care_plan` |
| `05_additions.raw.json` | `assemble-missing` agent (skip if 0 missing) | `additions_raw` |
| `05_plan.corrected.json` | `diff_guard.py` | `care_plan` |
| `05_additions.json` | `cite_check.py --additions` | `additions` |
| `06_plan.final.json` | `finalize.py` | `care_plan` |
| `report.md` / `report.html` | `finalize.py` (via `render_md.py` / `render_html.py`) | — |
| `run.json` | every script, via `runlog.py` | `run` |
| `report.audit.md` | `render_audit.py`, on request only | — |

## The stage graph

`‖` marks a parallel group. Caps are scripts; lowercase are agents.

```
UNITIZE (script) -> 01_units.json, 01_units.<k>.txt
 ground[1..K] (agent) ‖ glossary (agent)              <- group A
   -> 02_facts.<k>.raw.json            02_glossary.raw.json
ANCHOR_CHECK (per chunk) + MERGE_FACTS      GLOSSARY_CHECK
   -> 02_facts.json/.txt                     02_glossary.json
 assemble (agent, sequential) -> 03_plan.raw.json
CITE_CHECK + NUMERIC_PARITY (never fails)
   -> 03_plan.draft.json               03_flags.json
 review-fidelity (agent) ‖ review-coverage (agent)    <- group B
   -> 04_review.raw.json       04_coverage.raw.json
SANITIZE_REVIEW --only review  +  SANITIZE_REVIEW --only coverage
   -> 04_review.json                    04_coverage.json
 correct (skip if 0 corr.) ‖ assemble-missing (skip if 0 missing)  <- group C
   -> 05_plan.corrected.raw.json              05_additions.raw.json
DIFF_GUARD  +  CITE_CHECK --additions
   -> 05_plan.corrected.json              05_additions.json
FINALIZE -> 06_plan.final.json, report.md, report.html, run.json
RENDER_AUDIT (on request only) -> report.audit.md
```

### Stage 0 — unitize (script)

**Purpose:** split input text files into numbered, citable units and chunk
them for grounding. **Command:**
`python3 unitize.py (--runs-dir DIR | --run-dir DIR) --input PATH[:native|ocr|pasted] [--input PATH ...] [--chunk-size 150]`

Splits each file on `\f` into pages, each page on `\n` into lines; a blank
line is skipped (`blank_lines_skipped`) but still advances the line
counter. Unit ids are sequential across every input file in the order
given, starting at 1 — a two-file run has one continuous id space, not one
per file. Chunks are consecutive id ranges of at most `--chunk-size`
(default 150) units, never splitting a page across a chunk boundary unless
the page alone exceeds the chunk size.

**Failure:** an empty input file, or a document with no non-blank lines,
records `unitize: failed` and exits 1 — fatal. **Status line exception:**
the status line prints second-to-last; the resolved run directory path is
always the true last line.

### Stage 1 — ground (agent, one per chunk) ‖ glossary (agent)

**Ground.** Extracts atomic facts from one chunk, each anchored to one unit
id with a verbatim quote. Inputs: `01_units.<k>.txt`,
`reference/categories.md`, `reference/abbreviations.json`. Output:
`02_facts.<k>.raw.json`. Check: `anchor_check.py --run-dir <run> --chunk <k>`
(validates against `facts_raw.schema.json`, then anchor-checks every fact).

**Glossary.** Proposes plain-language definitions from the source alone.
Inputs: every `01_units.<k>.txt`. Output: `02_glossary.raw.json`. Check:
`glossary_check.py --run-dir <run>`.

**Anchor check** (`anchor_check.check_fact`), first failing reason wins:
`unknown_unit` (bad `unit_id`) → `empty_quote` → `quote_not_in_unit` (the
normalized quote isn't a substring of the unit's normalized text —
`textnorm.find_normalized`: NFKD-decompose, ASCII-fold, lowercase, collapse
whitespace, both sides) → `uninformative_quote` (fails the
informativeness floor) → `bad_category`.

**Quote informativeness floor** (`textnorm.is_informative`): true if the
quote has a digit, a word of 7+ characters, or is 12+ characters long.

`merge_facts.py --run-dir <run>` (once, after every ground task is
checked/retried): re-validates each `02_facts.<k>.raw.json`, re-runs
`anchor_check.check_fact` on every fact, keeps survivors, **deduplicates**
by `(unit_id, normalized_quote, category)` — this key includes `unit_id`,
so it cannot catch a duplicate grounded from two different files/chunks
(see Known gaps) — then **renumbers** survivors 1..N in chunk order.

**Failure:** zero surviving facts → `ground: failed`, exit 1, fatal.
`glossary_check.py` is never fatal: a missing/invalid raw file yields an
empty glossary, `glossary: skipped`.

### Stage 2 — assemble (agent, sequential)

Turns the fact ledger into a typed, plain-language plan. Inputs:
`02_facts.txt`, `reference/style_rules.md`,
`reference/ahrq_plain_language.json`, `schema/care_plan_agent.schema.json`.
Output: `03_plan.raw.json`. Check: `cite_check.py --run-dir <run>` (writes
`03_plan.draft.json`). Fatal after one retry.

**Citation guards** (`cite_check._apply_guards`), in order:
1. `questions` truncated to at most 3.
2. `summary_fact_ids` filtered to existing ids; `summary` text kept even if
   this empties the list (`summary_uncited`).
3. Every item's `source_fact_ids` (the seven flat sections plus
   `diagnosis.details`) filtered to existing ids; zero survivors drops the
   item (`dropped_uncited_by_section`).
4. `changed_since_last_visit_fact_ids` filtered the same way; nothing
   surviving clears both it and the text to `""`/`[]`.
5. Empty-string `why` on `medications`/`tests`/`procedures`/`other` →
   `null` (`why_nulled`).
6. Invalid `severity`/`urgency` (outside its enum) → `null`.
7. `null` `status` on an actionable item defaults to `"to_do"`
   (`status_defaulted`).

Then, always, `numeric_parity.py --run-dir <run>` (writes `03_flags.json`;
never fails the run).

### Stage 3 — review-fidelity (agent) ‖ review-coverage (agent)

**Fidelity.** Finds every place the plan says something its facts don't
support; emits corrections. Inputs: `02_facts.txt`, `03_plan.draft.json`,
`03_flags.json`. Output: `04_review.raw.json`. Check:
`sanitize_review.py --run-dir <run> --only review`.

**Coverage.** Enumerate-then-check every fact id against the plan; never
judges fidelity. Inputs: `02_facts.txt`, `03_plan.draft.json`. Output:
`04_coverage.raw.json`. Check: `sanitize_review.py --run-dir <run> --only coverage`.

**Review sanitize rules** (`sanitize_review.sanitize_corrections`), each a
named drop reason: `unresolvable_path` (path doesn't resolve) ·
`not_stated_outside_why` (`not_stated` on anything but a `*.why` field) ·
`correct_without_value` (`correct` with no value) · `summary_only_remove`
(`correct`/`not_stated` targeting `summary`) · `duplicate` (exact repeat) ·
`removed_item` (targets a path inside an item another kept `remove`
already covers — **remove wins**, applied last over the kept set).

**Coverage backfill** (`sanitize_review.process_coverage`): an entry
citing an unknown fact id is dropped (`unknown_dropped`); every fact id the
agent's walk omitted is backfilled `present: false` (`backfilled`) — the
output always has exactly one entry per fact id, ascending, no gaps.
`missing` is every id left `present: false`.

### Stage 4 — correct (agent, skip if 0 corrections) ‖ assemble-missing (agent, skip if 0 missing)

**Correct.** Applies exactly the fixed correction list plus one bounded PII
sweep. Inputs: `03_plan.draft.json`, `04_review.json`,
`reference/style_rules.md`. Output: `05_plan.corrected.raw.json`. Check:
first `diff_guard.py --run-dir <run> --strict` (retry once with the
violation paths), then, regardless, `diff_guard.py --run-dir <run>` (no
`--strict`) to settle and write `05_plan.corrected.json`. If
`corrections == 0`: agent skipped, `diff_guard.py` run directly (copies the
draft through, `correct: skipped`).

**Assemble-missing.** Turns coverage misses into new items, citing only
those facts, never touching existing items. Inputs: `02_facts.txt`,
`03_plan.draft.json`, `04_coverage.json`, `reference/style_rules.md`,
`schema/additions_raw.schema.json`. Output: `05_additions.raw.json`.
Check: `cite_check.py --run-dir <run> --additions`. If `missing == 0`:
agent skipped, check run directly (`assemble_missing: skipped`).

**Diff guard rules** (`diff_guard._diff_item`): walks the whole plan tree,
draft vs. corrected-raw. A changed leaf is allowed only if its path is
named by a correction, or it's a **bounded PII substitution**: field name
in `{summary, why, description, what_it_means_for_you, instructions,
what_to_expect, what_it_might_mean, related_to, changed_since_last_visit,
side_effects_to_watch, preparation, steps, questions, low_priority}`, and
word-level `difflib.SequenceMatcher` opcodes count ≤4 non-equal tokens on
either side (`_MAX_PII_TOKEN_DELTA`). An array's length may change only
where a `remove` correction accounts for it (original-index
survivorship). Any other change is a violation: `--strict` exits 1;
otherwise falls back to a byte-identical copy of the draft, adds the
notice "We could not safely apply every correction to this summary. Please
compare important details, like medicine doses, with your original
document," and records `correct: degraded`.

**Additions cite guard** (`cite_check._run_additions`): `source_fact_ids`
filtered to valid ids first; zero survivors drops the item
(`dropped_uncited`); survivors not a subset of `missing` also drops it
(`dropped_not_missing`).

### Stage 5 — finalize (script)

`python3 finalize.py --run-dir <run>`. **Preconditions:** `run.json` must
record `unitize`, `ground`, `assemble` as non-`failed`, else exit 1,
nothing written. In order:

1. **Load** `05_plan.corrected.json` if present, else `03_plan.draft.json`
   (`used_draft_fallback` records which).
2. **Merge additions** (`_merge_additions`): appends each `05_additions.json`
   item into its plan section, deduplicated by `(frozenset(source_fact_ids),
   key_field_value)` — key field `title` (most sections), `reason`
   (`reason_for_visit`), `time_frame` (`follow_up`), `symptom`
   (`warning_signs`).
3. **Citation existence guard** (`_apply_citation_guard`): re-runs
   `cite_check._apply_guards` over the merged plan, dropping anything left
   uncited (`items_dropped`).
4. **Glossary re-detect** (`_apply_glossary`): keeps a term only if its
   normalized `matched_term` is found inside the normalized patient-visible
   text (`plan_view.visible_text`) of the current plan.
5. **PII sweep** (`_pii_sweep`): bounded regex over every string field
   except `meta` — `Dr./Doctor <Name>` and `<Name>, MD/DO/NP/PA/RN` → "your
   doctor"; substitution count recorded.
6. **Readability** (`_compute_score`): `readability.fk_grade` on the raw
   input text (`before_grade`) and `plan_view.visible_text` of the final
   plan (`after_grade`).
7. **Notices** (`_build_notices`): draft-fallback notice ("We could not run
   every check on this summary") if step 1 fell back; generic verify
   notice ("We could not fully verify every part of this summary against
   your document. Please compare important details, like medicine doses
   and dates, with your original paperwork") if any stage failed, or
   `ground`/`assemble`/`correct` degraded, or step 3 dropped anything.
   Deduplicated.
8. Validate against `care_plan.schema.json`, write `06_plan.final.json`,
   `report.md`, `report.html`.

**Failure:** exit 1, nothing written, on failed preconditions or a final
document that doesn't validate (internal-bug case). **Stdout order:** HTML
path, Markdown path, the reading-level line (or "Reading level: not enough
text to estimate."), each notice verbatim, then the `finalize: ...` status
line last.

### render_audit (script, on request only)

`render_audit.py --run-dir <run> [--out PATH]` (default
`<run>/report.audit.md`). Never runs inside `finalize.py`. Reads
`06_plan.final.json`, `02_facts.json`, `01_units.json`, `04_coverage.json`
(if present), `run.json`; renders a stage table (status, attempts, checks);
every item with its facts as `file:page:line "quote"`; facts in
`04_coverage.json`'s `missing`; facts dropped at grounding with reason.

## Data contracts

All files are UTF-8 JSON with `schema_version`/`plugin_version` at the top
level except where noted; full definitions in `skills/simplify-med/schema/*.json`.

**`01_units.json`** (`units`): `units[] {id, file, page, line, text,
extraction_method}` (`native`/`ocr`/`pasted`); `chunks[] {k, first_id, last_id}`.
**`02_facts.json`** (`facts`) / raw (`facts_raw`): `facts[]` — raw
`{category, unit_id, quote, text}`, merged adds `{id, char_start,
char_end}`; `dropped[] {chunk, reason, fact}` (merged only); `category` ∈
`reason_for_visit, diagnosis, medications, tests, procedures, other,
follow_up, warning_signs`.

**The care plan** (`care_plan`; agent subset `care_plan_agent`):

| Field | Shape |
|---|---|
| `summary`, `summary_fact_ids` | string, `int[]` |
| `reason_for_visit[]` | `{reason, description, source_fact_ids}` |
| `diagnosis` | `{changed_since_last_visit, changed_since_last_visit_fact_ids, details[]}` |
| `diagnosis.details[]` | `{title, plain_name, description, what_it_means_for_you, severity: high\|medium\|low\|null, source_fact_ids}` |
| `medications[]` | `{title, plain_name, why: string\|null, dosage, frequency, timing, duration, instructions, side_effects_to_watch, change, status: to_do\|done, source_fact_ids}` |
| `tests[]` | `{title, plain_name, why, description, preparation, status, source_fact_ids}` |
| `procedures[]` | `{title, plain_name, why, what_to_expect, timeframe, status, source_fact_ids}` |
| `other[]` | `{title, why, steps[], description, frequency, duration, status, source_fact_ids}` |
| `follow_up[]` | `{time_frame, description, status, source_fact_ids}` |
| `warning_signs[]` | `{symptom, what_it_might_mean, what_to_do, urgency: emergency\|call_doctor\|monitor\|normal_side_effect\|null, related_to, source_fact_ids}` |
| `questions[]` (max 3), `low_priority[]` | string |
| `terms` | `{matched_term: {definition, source}}` — final schema only |
| `meta`, `notices[]`, `score` | final schema only |

Agent-facing schema excludes `schema_version`, `plugin_version`, `meta`,
`notices`, `terms`, `score`.

**`04_review.json`** (`review`) / raw: `verdict: pass|needs_correction`;
`corrections[] {op: correct|not_stated|remove, path, value?}`; `dropped[]
{correction, reason}` (sanitized only). **`04_coverage.json`** (`coverage`)
/ raw: `coverage[] {fact_id, present}`; `missing[]` (sanitized only).

**`05_additions.json`** (`additions`) / raw: same item shapes as the care
plan, but `diagnosis` flattens to top-level `diagnosis_details[]` (no
`changed_since_last_visit`). Fields: `reason_for_visit[]`,
`diagnosis_details[]`, `medications[]`, `tests[]`, `procedures[]`,
`other[]`, `follow_up[]`, `warning_signs[]`, `low_priority[]`, plus
`dropped[] {item, reason}` (sanitized only).

**`03_flags.json`** (`flags`): `numeric_parity[] {path, tokens_in_field[],
tokens_in_facts[]}`; `thin_fields[] {path, value}`. **`run.json`** (`run`):
`inputs[] {file, extraction_method, pages}`; `stages {<stage>: {status:
ok|degraded|failed|skipped, attempts, started_at, finished_at, checks}}`;
`notices[]`.

## Stage prompt design

Prompts live once, in `skills/simplify-med/stages/*.md`; `agents/*.md` are
thin wrappers that tell the sub-agent to read the matching stage file,
follow it, then reply in one line.

**`reference/style_rules.md`**, applied by every writing stage (assemble,
assemble-missing, correct): **PII** (every name → a generic form, the one
case where exact wording isn't preserved) · **NUMERACY** (a number and its
unit are copied verbatim; only spacing/spelling may change, never the
value, unit, a label, a range, or an unstated severity word) ·
**LANGUAGE RULES** (active voice, "you," one idea per sentence, expand
every abbreviation, never invent/round a number, start actions with a
clear verb, ~6th-grade reading level) · **PLAIN WORDS**
(`reference/ahrq_plain_language.json`, 299 `{term, replacement}` pairs).

**`reference/categories.md`** — the eight-category checklist
(`reason_for_visit`, `diagnosis`, `medications`, `tests`, `procedures`,
`other`, `follow_up`, `warning_signs`), each with a criterion and boundary
rule (e.g. contrast given during a scan is a `tests`/`procedures` fact,
never `medications`; a merely-listed side effect is not a `warning_signs`
fact). Billing, insurance, scheduling metadata are explicitly not facts.

**`stages/assemble.md`**'s named rules: MAPPING (category → array) ·
SOURCE_FACT_IDS (every kept item cites ≥1 fact) · STATUS (`to_do`/`done`,
defaults `to_do`) · NOT STATED (`why` is the clinician's *stated reason for
this patient* — never a drug's usual indication, never a timing/dosing
instruction, never mined from a fact that says the reason isn't documented;
a worked ondansetron example exists specifically to rule this out) · MERGE
(facts describing the identical clinical fact become one item, preserving
every differing detail, never collapsed to a vaguer collective term) ·
LOW PRIORITY (routine/normal/administrative only, narrow) · QUESTIONS
(≤3, interrogative, no presupposed fact).

**Why review is split.** `review_fidelity.md` (does the plan say something
its facts don't support — never judges placement) and
`review_coverage.md` (is every fact's content somewhere in the plan,
enumerate-then-check — never judges truth) run as independent parallel
dispatches of different shape.

**How the reviewer uses `03_flags.json`.** Both hint types are "a place to
look, not an automatic correction": a `numeric_parity` hint requires either
a `correct` or confirmed-equivalent values (a dropped unit or added label
is never waved off as respacing); a `thin_fields` hint only becomes a
correction if the field actually misstates something, never for brevity
alone.

**`assemble_missing.md`** may only build items from fact ids in `missing`,
using assemble's own MAPPING/STATUS/NOT STATED rules; may never restate,
edit, or duplicate anything already in the plan.

**Why the corrector is an LLM.** A `"correct"` value must be re-rendered in
the document's existing style (units, abbreviations, "you" phrasing) — a
bare substitution can't do that — so `correct.md` is an agent, and
`diff_guard.py` is the mechanical backstop keeping its blast radius to the
named corrections plus a bounded PII sweep.

## Rendering

`plan_view.py` is the single view model; `render_md.py` and
`render_html.py` both call `plan_view.build_view(plan)`, sharing section
order/content selection. Order: summary, reason, findings, next-steps,
watch, questions, glossary; an empty section builder returns `None`
(omitted).

**Next-steps grouping and type precedence.** Rows split "to do" / "already
done" by `status`; within each group, ordered by `TYPE_PRECEDENCE =
[medication, test, procedure, appointment, instruction]`, not array order.

**Warning-sign ordering.** `URGENCY_ORDER = [emergency, call_doctor,
monitor, normal_side_effect, None]`; an ungraded sign sorts last but is
never dropped.

**Always omitted:** `low_priority`, every `*_fact_ids` field, `meta`,
`run_id` — audit-trail-only, belong to `render_audit.py`, which reads the
plan directly instead of through the view model.

**Markdown vs HTML.** Same seven sections and content. Markdown uses `[ ]`/
`[x]` rows and plain headers; HTML additionally wraps the first occurrence
of each surviving glossary term (summary, findings, next-steps, watch
sections only) in `<span class="term" tabindex="0" data-def="...">`.

**`report.html`'s inline features.** One self-contained file via
`string.Template` into `templates/report.html`: `$title`, `$body`,
`$plan_json` (the full final plan, embedded in
`<script type="application/json" id="simplify-med-plan">`, `</` escaped),
`$run_id`. Inline CSS: light/dark via `prefers-color-scheme` plus a
`data-theme` override. Inline JS: checkbox state in `localStorage` under
`simplify-med:<run_id>` (try/catch, degrades silently); glossary term
tap/click reveals a popover, one open at a time; `beforeprint`/`afterprint`
force-opens every `<details>` for printing and restores prior state. Print
stylesheet hides checkboxes/hint, shows an empty `☐` glyph instead.

**`render_audit.py`** reads the plan directly (not through `plan_view`) to
surface what the view model hides: citations as `file:page:line "quote"`,
the low-priority list, coverage misses, grounding drops.

## Agents and orchestration

`SKILL.md` drives the run; `agents/*.md` are deliberately thin (read the
stage file, follow it, write the output, reply in one line) so the same
content works as a real sub-agent or in-context.

**Dispatch message shape** (SKILL.md section 4):
```
Stage file: <skill>/stages/<stage>.md
Inputs: <absolute paths, one per line>
Output: <absolute path>
Reference dir: <skill>/reference
Schema dir: <skill>/schema
```

**One retry.** If the check script exits 1 with validator errors, the same
agent is re-dispatched once with the dispatch message suffixed by the
check's stderr. A second failure is treated as that stage failing.

**Running without sub-agents.** Current SKILL.md: "Otherwise, read the
stage file yourself and perform the stage in the current context, writing
the output file, one stage at a time, in the same order as below." Every
parallel group still runs, just sequentially.

**Concurrency.** "Run every task of a parallel group at the same time when
you can run tasks in parallel, respecting any concurrency limit you have."
Both kill tests ran under a 2-concurrent-agent cap; group A (ground×K plus
glossary) split into batches when K+1 exceeded 2; group B always fit in
one batch. The cap was never the actual bottleneck in either test.

### Platform extension points

`SKILL.md` has two platform extension points. After resolving bundled paths and before
Stage 0 it reads `custom_start.md`; after Stage 5 finalization and before presenting
results it reads `custom_end.md`. Canonical defaults are blank no-ops. A platform build
copies the skill to a temporary staging tree, installs the defaults, and replaces them
with platform versions when present. It never edits the source skill.

This is the only OpenAI-related change inside orchestration. The OpenAI final hook tells
ChatGPT to expose the native summary and three generated artifacts, then call the report
viewer with `06_plan.final.json`. It does not change the stage graph, medical prompts,
checks, schemas, or failure table.

## OpenAI presentation architecture

The OpenAI package adds a post-finalization presentation path:

```text
06_plan.final.json --OpenAI file parameter--> render_simplify_med_report
        |                                        |
        |                                        +--> generic result + static UI only
        v
ChatGPT iframe receives original tool input
        |
        +--> getFileDownloadUrl(file_id) --> fetch from OpenAI --> validate --> render
```

The streamable-HTTP MCP endpoint registers exactly one read-only render tool and one
versioned `text/html;profile=mcp-app` resource. The endpoint receives the file ID and
temporary download URL in the tool call but must not fetch, process, store, echo, or log
them. The browser widget obtains a fresh URL from the ChatGPT bridge and validates the
final care-plan JSON locally.

The widget is a renderer over the same final JSON, not another pipeline stage. Inline
mode is compact; fullscreen mode preserves the seven-section information architecture
and is requested only after the user activates **Open full report**. Markdown and the
self-contained HTML remain the complete portable fallback.

See [openai.md](openai.md) for the complete tool schema, data flow, privacy boundary,
CSP, deployment, prototype gates, and PHI/publication constraints.

## Uncalibrated constants

From the design brief (`brainstorm.v1.md` section 5), verified against the
current code:

| Constant | Value | Where | Why this value |
|---|---|---|---|
| Ground chunk size | 150 units | `unitize.py` (`_DEFAULT_CHUNK_SIZE`) | Fits a typical note in one agent |
| Quote informativeness floor | 12 chars, or 7+ char word, or a digit | `textnorm.py` (`is_informative`); own copy of the same constants in `numeric_parity.py` | Inherited from simplify-med PRD 03 |
| PII substitution token delta | 4 tokens | `diff_guard.py` (`_MAX_PII_TOKEN_DELTA`) | Inherited from simplify-med PRD 05 |
| Numeric unit-word length | 15 chars | `numeric_parity.py` (`_UNIT_WORD_MAX_LENGTH`) | Inherited from simplify-med PRD 10 |
| Glossary soft cap | 25 terms | `stages/glossary.md` (instruction) + `glossary_check.py` (`_CAP`, enforced) | Fewer than simplify-med's 40 |
| Target reading level | grade 6 | `reference/style_rules.md` | AHRQ/CDC recommendation |

None recalibrated against real documents; see `futures.md` for the
proposed calibration protocol.

## Testing

**Layers:** unit tests per deterministic script (`test_anchor_check.py`,
`test_cite_check.py`, `test_diff_guard.py`, `test_finalize.py`,
`test_glossary_check.py`, `test_merge_facts.py`, `test_numeric_parity.py`,
`test_plan_view.py`, `test_readability.py`, `test_render_audit.py`,
`test_render_html.py`, `test_render_md.py`, `test_runlog.py`,
`test_sanitize_review.py`, `test_schemas.py`, `test_textnorm.py`,
`test_unitize.py`, `test_validate.py`) · end-to-end deterministic chain
(`test_pipeline_e2e.py`: drives the whole script chain via `subprocess`,
hand-written JSON standing in for every LLM stage) · skill consistency
(`test_skill_consistency.py`: every script/stage/reference/schema file
`SKILL.md` names exists, agent-name ↔ stage-file mapping is a total
bijection, every agent's `tools:` is exactly `Read, Write`) · stage-doc
rules (`test_stage_docs.py`: text-content regression guards for the
kill-test fixes) · status lines (`test_status_lines.py`: every script ends
stdout, second-to-last for `unitize`, with `^[a-z_]+: (ok|degraded|failed|skipped) \|`)
· fixtures (`test_fixtures.py`: structural assertions, not LLM stages) ·
packaging (`test_build.py`: platform zips, staging/override behavior, archive contents,
and version mismatches) · OpenAI MCP/widget contract tests (file schema, non-fetching
handler, non-echoing result, client validation, capability fallbacks, and user-gesture
fullscreen).

**How to run the Python suite:** `python3 -m unittest discover -s tests -v` — stdlib-only,
no network, and expected to pass from a clean checkout. The OpenAI Node/widget commands
are documented in [openai.md](openai.md#test-and-verify) and `mcp/openai/README.md`.

**Fixtures** (`tests/fixtures/documents/`): `synthetic-visit-note.txt`,
`synthetic-discharge-summary.txt` (173 units, two form-feed page breaks),
`synthetic-lab-report.txt` (24 units, single page) — all labeled synthetic
in a top comment line; `tests/fixtures/README.md` forbids labeling a
fabricated document as de-identified real data.

**Kill test 1** (`agent_files/.../kill-test-1.md`): host-simulated run on
`synthetic-visit-note.txt` (1 chunk); every stage `ok`/`skipped`; verdict
yes. Six friction items found — agent-path ambiguity in `SKILL.md`; agents
not honoring their one-line reply; a silent skip-path script; a real
NUMERACY violation (dropped `mmHg`) no stage was positioned to catch;
duplicated title/plain_name phrasing; no retry-path exercise. Fixed: path
ambiguity, silent skip-path, numeracy gap, phrasing duplication. Left open:
reply discipline, retry path.

**Kill test 2** (`kill-test-2.md`): same protocol, harder two-file bundle
(discharge summary + lab report, 197 units, 2 chunks). Kill test 1's fixes
held; reply discipline recurred. Verdict mostly yes, one clear defect: a
new medication's `why` said "For nausea" instead of not-stated, though its
fact stated no reason was documented (closed afterward via the ondansetron
example in `assemble.md`/`assemble_missing.md`/`review_fidelity.md`). New
finding: cross-chunk fact duplication (same lab analytes, two source
files) deduplicated only by the assemble agent's MERGE rule —
`merge_facts.py`'s dedupe key includes `unit_id`, so it can't catch a
cross-file duplicate — worked here but with no deterministic backstop.
Retry path still unexercised.

## Known gaps

From `futures.md`, the kill tests, and this documentation pass:

- **Numeric-parity is a hint, not a gate.** Nothing mechanically blocks an
  unaddressed mismatch from shipping; kill test 1 found a real instance
  before the fix tightened instructions (not the mechanism).
- **Cross-document duplicate merging has no deterministic backstop** — see
  kill test 2, and `futures.md`'s "Cross-document duplicate merging
  backstop" entry.
- **Agent reply discipline is not enforced.** `ground` and `assemble` have
  both replied with an extra sentence before their required one-liner, in
  both kill tests. Harmless today (control flow reads files and
  check-script stdout only) but unenforced.
- **The retry path has never been exercised in a kill test.** Every stage
  validated cleanly on the first attempt in both kill tests.
- **`render_audit.py` does not surface `extraction_method`.** Every unit
  and manifest input carries `extraction_method` (`native`/`ocr`/`pasted`,
  from `unitize.py`), but no renderer — not `plan_view.py`, not
  `render_md.py`/`render_html.py`, not `render_audit.py`'s `_fact_line` —
  ever prints it. A reader of `report.audit.md` has no way to tell whether
  a cited line came from native text, OCR, or a pasted excerpt, even
  though the data exists in `01_units.json`. Real, currently-existing gap,
  not a documented feature.
- **Everything in `futures.md`** — simplification levels, level-based
  rendering, generated per-platform manifests, follow-up conversation mode,
  cross-run history/memory, a caregiver view, visual aids, color-coding,
  translation, external resource links, reviewed (LLM-checked) additions,
  a real evaluation harness — is deliberately out of scope for v0.1.0.
