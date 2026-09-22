# Simplify-med as a plugin — design brief

Date: 2026-09-22
Status: approved in a brainstorm session; implementation proceeds directly from this brief (no separate PRD/tasks pass, by owner decision).
Source system: `/root/projects/juno-projects/simplify-med` at `origin/main` (commit `e0e1dce`, "Fidelity hardening: PRDs 10-18"). Read that repo's `docs/agent_files/2026-09-09-docs-fidelity-concision-brief/brainstorm.v1.md` and `backend/care_plan/prompts/*.txt` for the pipeline this plugin reproduces.

## 1. Problem

Simplify-med turns a clinical document into a plain-language care plan through a fact-first pipeline: deterministic line numbering, an LLM grounding step that emits a flat ledger of facts each anchored to a line id and a verbatim quote, an LLM assemble-and-render step that maps facts into a typed care plan with field-level plain language, an LLM review step (fidelity corrections plus enumerate-then-check coverage), and an LLM correct step, with deterministic checks between every stage. It runs as a Flask service on Cloud Run with Firestore, Cloud Tasks, GCS, and Vertex AI.

This project reproduces that pipeline with none of that infrastructure. The plugin runs entirely on the host that loads it (Claude Code today, claude.ai or any Agent Skills host tomorrow). The host does file ingestion (PDF, image OCR, DOCX) and hands the plugin plain text. The plugin numbers the lines, runs the LLM stages as discrete file-handoff steps so no single context holds the whole pipeline, verifies every anchor mechanically, and produces one JSON document in a fixed schema. Deterministic scripts render that JSON to Markdown and to a single self-contained interactive HTML file. Interim JSON files stay on disk as the audit trail.

For: a patient or caregiver who has a clinical document and a Claude session, with no clinician in the loop and no server behind it. They never see line numbers or fact ids; they see a seven-section care plan.

## 2. Decision log

### Platform and shape

| Decision | Alternative rejected | Why |
|---|---|---|
| A Claude Code plugin whose substance is one skill in the portable Agent Skills format (SKILL.md with only the standard frontmatter fields, plus bundled `scripts/`, `stages/`, `schema/`, `reference/`, `templates/`). The plugin wrapper adds `agents/` for Claude Code. | Platform-specific plugin per host | The same skill folder uploads to claude.ai unchanged. Claude Code-specific frontmatter fields would break packaging elsewhere, so SKILL.md uses only `name` and `description`. |
| Context isolation comes from the host: each LLM stage is a plugin agent in Claude Code, reading its input file and writing its output file. On a host without sub-agents the same stages run sequentially in one context, still reading and writing files. | Scripts call an LLM API directly | Needs a key and network; the claude.ai sandbox has neither. Fails the platform-agnostic rule. |
| Prose orchestration in SKILL.md: the model reads the stage list and dispatches agents and scripts in order. | A bundled `pipeline.py` state machine with `next`/`complete` commands | Owner decision: agents follow instructions reliably; the state machine is complexity without a demonstrated need. Each script still appends its result to `run.json` so the audit trail and resumability do not depend on the orchestrator. |
| Deterministic scripts are Python 3 standard library only. | Allow dependencies; Node | claude.ai has no pip and no network. Everything needed (json, re, difflib, html, unicodedata, string.Template, zipfile) is in stdlib. |
| Input contract: one or more `.txt` files, one per source document. Page breaks are a form-feed (`\f`) the host inserts when it knows them; otherwise the file is one page. Extraction method is declared per file (`native`, `ocr`, `pasted`), default `native`. | Single blob, no file/page; plugin ships its own extractors | Keeps the `{file, page, line}` provenance simplify-med built. Extractors would need dependencies. |
| One run = one visit. Several input files are one encounter's bundle; the grounder sees all units together and merge rules apply across files. No cross-visit reasoning. | Infer "changed since last visit" across files | Inference the ledger cannot back. A user with two visits runs it twice. |
| Everything runs on the host. No server, no stored state outside the run folder. | — | Owner requirement. |

### Pipeline

| Decision | Alternative rejected | Why |
|---|---|---|
| The LLM stages are simplify-med's: ground, glossary, assemble-and-render, review, correct. Review is split into two agents (fidelity, coverage). One new bounded agent, assemble-missing, turns coverage misses into items. | Fewer stages; single-agent skill | Owner decision. The split lets review run as two parallel jobs of different shape. |
| Parallel groups: (1) ground per chunk of ~150 units alongside glossary; (2) review-fidelity alongside review-coverage; (3) correct alongside assemble-missing. Assemble is sequential. | Fully sequential | Owner asked to parallelize everything possible. |
| Coverage misses feed an assemble-missing agent whose additions are deterministically cite-checked (must cite only the missing facts) and parity-checked, then merged into the plan at finalize. They are not LLM-reviewed. | Coverage stays a log-only signal (simplify-med today); re-run review on additions | The only way coverage becomes more than a metric. Not re-reviewing is the price of running additions beside correct; recorded as a risk. |
| The corrector is an LLM agent, not a deterministic patch applier. Its output is diff-guarded by script: only paths named in the correction list, plus bounded PII substitutions, may change. A guard failure keeps the pre-correction plan and adds a notice. | Deterministic application of the three ops | Owner decision, consistent with simplify-med: corrected values must be re-rendered in the document's style. |
| Deterministic checks feed the pipeline instead of logs: numeric-parity mismatches and thin-field flags from the assemble output go to the fidelity reviewer as hints; anchor-check failures drop the fact; uncited items are dropped at citation check. | Log-only, as simplify-med | There is no logging backend in a plugin. A check that only logs is a check nobody reads. |
| Every agent output is validated against its JSON schema by script. An invalid output earns one retry with the validator's message appended to the agent's input. A second failure counts as the stage failing. | No retry; unlimited retries | Prefer passing over failure, bounded. |
| Ground and assemble failing ends the run with a plain explanation and the run folder intact. Glossary, review, correct, coverage, and assemble-missing degrade: the last good plan proceeds and a notice is added. | Hard gate on any failure | Owner: prefer passing over failure. A gate leaves someone with nothing over a transient failure. |
| Long inputs: ground is chunked at a fixed unit count per agent (150, uncalibrated). Chunk outputs are merged and facts renumbered by script. | Single ground agent over the whole document | A long document costs more agents, not a bigger context. |

### Content and output

| Decision | Alternative rejected | Why |
|---|---|---|
| Output schema is simplify-med's CarePlan as landed on main (nullable `why`, `source_fact_ids` on reason-for-visit and diagnosis items, `changed_since_last_visit_fact_ids`, `status` required on actionable items, `low_priority`, `terms`), plus top-level `meta`, `notices[]`, and `score`. | Redesign the schema around the criteria doc | The categories map one to one; the prompts and checks already target this schema. |
| `low_priority` stays in the JSON and is omitted by the patient-facing renderers. Grounding gets an explicit rule that billing codes and administrative detail are not facts. | Render it as a collapsed section (simplify-med); never extract it | Owner: the report should not show distracting content. Keeping it in JSON preserves the audit trail and the "remove nothing from the ledger" principle. |
| One fixed simplification level, `standard`, targeting about a 6th-grade reading level, expressed in the style rules. `level` is stored in `meta` and `run.json` so presets can be added without a schema change. | Three presets now | Owner: keep it simple for now. Presets are in futures.md. |
| One score: Flesch-Kincaid grade level, computed by a stdlib implementation, before (concatenated input text) and after (rendered plan text). Shown once in the report as "reading level before → after". Never gates. | Seven-method breakdown; no score | Owner asked for exactly one score, previous vs after. |
| Provenance stays in the final JSON (`source_fact_ids`, `summary_fact_ids`, `changed_since_last_visit_fact_ids`); renderers do not print it. A separate audit render, invoked only on request, prints every item with its facts as `file:page:line "quote"`. | Strip provenance from final JSON; separate trace file | One file, one schema; the audit view can be regenerated at any time. |
| Safety notice: when any non-fatal stage degraded or any deterministic check dropped or flagged content, the report carries one plain-language notice at the top. Details stay in `run.json`. | Silent (simplify-med); hard gate | The patient should not see fact ids, but should know when the safety net did not fully run. |
| Glossary: bundle `abbreviations.json` (47 entries, feeds grounding recall) and `ahrq_plain_language.json` (299 entries, feeds rendering). Do not bundle the Michigan dictionary. The glossary agent proposes terms by criterion ("a general reader plausibly could not define this"), writes one- to two-sentence definitions tagged `source: "llm_proposed"`, and finalize re-detects each term against the final plan text by normalized substring match; terms that no longer appear are dropped. Soft cap 25. | Port all three dictionaries and deterministic detection | The 320 KB Michigan file is mostly everyday words and the wrong shape for a subset. |
| PII: the style rules' PII paragraph applies at assemble and correct. Finalize adds a bounded regex sweep (`Dr.`/`Doctor`/trailing `MD` followed by capitalized words becomes "your doctor") and records the count. | Prompt-only | The late sweep catches what leaks. Regex is bounded on purpose; it is not a name detector. |
| Report: seven sections in this order. What you need to know; Why you were seen; What the doctor found (key findings, then "what changed since last time" when present); Your next steps (to-do first, then already done; each row labelled medication / test / procedure / appointment / instruction; fixed type precedence within each group); What to watch for (stated urgency first, ungraded last, never removed); Questions to ask your doctor; Medical terms explained. No source section. | simplify-med's eight cards | Follows the criteria doc's sequence; `low_priority` is hidden. |
| Medication rows: one summary line plus an expander for dose, frequency, timing, duration, instructions, side effects, change. | All fields inline | Concision. |
| HTML: one self-contained file. Inline CSS, inline JS, no external assets. Interactions: Next Steps checkboxes persisted in localStorage keyed by run id; collapsible sections, all open except the glossary; inline glossary terms with tap-to-reveal definition; print stylesheet with empty checkboxes. The final JSON is embedded in a `<script type="application/json">` block so the file is self-describing. | Separate CSS/JS; host-specific artifacts | Owner: one downloadable HTML file, platform agnostic. |
| Markdown: same seven sections, `[ ]` / `[x]` rows. | — | — |
| Audit trail: one folder per run, `simplify-runs/<run-id>/`, numbered stage files. Run id is a UTC timestamp plus a short hash of the input. | Flat `temp_<id>_<type>` prefix | Numbered names give order for free; the folder is what the user downloads or deletes. |

### Repository, versioning, packaging

| Decision | Alternative rejected | Why |
|---|---|---|
| `plugin.meta.json` is the source of truth for name, version (semver from 0.1.0), description, tags, schema_version. `.claude-plugin/plugin.json` is committed (needed for `--plugin-dir` local dev) and `build.py` refuses to package if the versions differ. | Generate the manifest only at build | Local development needs the manifest in the tree. |
| `packaging/build.py --platform claude-code|claude-ai` applies `packaging/<platform>.ignore` (gitignore-style patterns) and writes `dist/simplify-med-<version>-<platform>.zip`. The claude-ai zip is rooted at the skill folder and excludes `agents/`. | One universal zip | Hosts differ in what they accept. Per-platform manifest generation is a future. |
| Stage prompts live once, in `skills/simplify-med/stages/*.md`. Agent definitions are thin and instruct the sub-agent to read the stage file under the plugin root. | Inline prompts into each agent file at build | One file, no generation step, identical content on the in-context fallback path. |
| Every JSON output carries `plugin_version` and `schema_version`. | — | Auditability across versions. |
| Design docs live in `docs/agent_files/2026-09-22-simplify-med-plugin-brief/`; excluded from packages. | — | Follows the simplify-med convention. |

## 3. Design

### 3.1 Repository layout

```
simplify-med-plugin/
  plugin.meta.json
  .claude-plugin/plugin.json
  README.md
  .gitignore                      (dist/, simplify-runs/, __pycache__/)
  skills/simplify-med/
    SKILL.md                      orchestration: the stage list, file handoffs, parallel groups, fallback
    stages/                       ground.md, glossary.md, assemble.md, review_fidelity.md,
                                  review_coverage.md, assemble_missing.md, correct.md
    scripts/                      unitize.py, validate.py, anchor_check.py, merge_facts.py,
                                  cite_check.py, numeric_parity.py, sanitize_review.py,
                                  diff_guard.py, finalize.py, render_md.py, render_html.py,
                                  render_audit.py, readability.py, runlog.py (shared helper)
    schema/                       units.schema.json, facts_raw.schema.json, facts.schema.json,
                                  glossary.schema.json, care_plan.schema.json, review.schema.json,
                                  coverage.schema.json, additions.schema.json, run.schema.json
    reference/                    style_rules.md, categories.md, abbreviations.json,
                                  ahrq_plain_language.json
    templates/report.html
  agents/                         ground.md, glossary.md, assemble.md, review-fidelity.md,
                                  review-coverage.md, assemble-missing.md, correct.md
  packaging/                      build.py, claude-code.ignore, claude-ai.ignore
  tests/                          unittest modules per script; fixtures/
  docs/agent_files/2026-09-22-simplify-med-plugin-brief/
  dist/                           gitignored
```

### 3.2 Stage graph

Arrows are file handoffs inside `simplify-runs/<run-id>/`. `‖` marks a parallel group.

```
unitize (script)          inputs → 00_input/<file>.txt, 00_input/manifest.json
                          → 01_units.json (all units + chunk ranges), 01_units.<k>.txt (one "[id] text" line per unit, per chunk)
ground[k] (agent)         01_units.<k>.txt + reference/categories.md + abbreviations → 02_facts.<k>.raw.json
  ‖ glossary (agent)      01_units.*.txt → 02_glossary.raw.json
anchor_check + merge_facts (scripts)   02_facts.*.raw.json → 02_facts.json (verified, renumbered, quotes and offsets kept, drops recorded)
assemble (agent)          02_facts.json + style rules → 03_plan.raw.json
cite_check + numeric_parity (scripts)  → 03_plan.draft.json (uncited items dropped), 03_flags.json (parity and thin-field hints)
review-fidelity (agent)   02_facts.json + 03_plan.draft.json + 03_flags.json → 04_review.raw.json
  ‖ review-coverage (agent) 02_facts.json + 03_plan.draft.json → 04_coverage.raw.json
sanitize_review (script)  → 04_review.json (paths resolve, ops valid, remove wins), 04_coverage.json (backfilled to every fact id, missing list)
correct (agent, skipped if no corrections)        03_plan.draft.json + 04_review.json → 05_plan.corrected.raw.json
  ‖ assemble-missing (agent, skipped if no misses) 03_plan.draft.json + missing facts → 05_additions.raw.json
diff_guard (script)       → 05_plan.corrected.json, or falls back to the draft with a notice
cite_check on additions (script)   → 05_additions.json (items must cite only missing facts)
finalize (script)         merges additions; citation existence on every item; glossary re-detect; PII sweep;
                          readability before/after; assembles meta, notices, score
                          → 06_plan.final.json, report.md, report.html, run.json
render_audit (script, on request)  → report.audit.md
```

### 3.3 Data contracts

All files are UTF-8 JSON with `schema_version` and `plugin_version` at the top level unless noted.

- **`00_input/manifest.json`**: `{run_id, created_at, level: "standard", inputs: [{file, extraction_method, pages}]}`.
- **`01_units.json`**: `{units: [{id, file, page, line, text, extraction_method}], chunks: [{k, first_id, last_id}]}`. Unitize splits each file on `\f` into pages, each page on `\n` into lines; blank lines emit no unit but still count toward `line`; `id` is sequential across files in the order given, starting at 1; chunks are consecutive id ranges of at most 150 units, never splitting a file's page across chunks unless a page alone exceeds the limit.
- **`02_facts.<k>.raw.json`** (agent output): `{facts: [{category, unit_id, quote, text}]}`. Categories are exactly `reason_for_visit | diagnosis | medications | tests | procedures | other | follow_up | warning_signs`.
- **`02_facts.json`**: `{facts: [{id, category, unit_id, quote, char_start, char_end, text}], dropped: [{chunk, reason, fact}]}`. Anchor check: cited unit id exists; normalized quote (NFKD, case-folded, whitespace-collapsed) is a substring of the normalized unit text; quote passes the informativeness floor (contains a digit, or a word of 7+ characters, or is 12+ characters). Offsets are located in the raw unit text. Surviving facts are renumbered 1..N in chunk order.
- **`02_glossary.raw.json`** / **`02_glossary.json`**: `{terms: [{term, matched_term, definition, source: "llm_proposed"}]}`.
- **`03_plan.raw.json`**, **`03_plan.draft.json`**, **`05_plan.corrected.json`**, **`06_plan.final.json`**: the care plan. Fields, verbatim from simplify-med's `backend/models/care_plan/care_plan.py` at `e0e1dce`: `summary`, `summary_fact_ids`, `reason_for_visit[] {reason, description, source_fact_ids}`, `diagnosis {changed_since_last_visit, changed_since_last_visit_fact_ids, details[] {title, plain_name, description, what_it_means_for_you, severity: high|medium|low|null, source_fact_ids}}`, `medications[] {title, plain_name, why: string|null, dosage, frequency, timing, duration, instructions, side_effects_to_watch, change, status: to_do|done, source_fact_ids}`, `tests[] {title, plain_name, why, description, preparation, status, source_fact_ids}`, `procedures[] {title, plain_name, why, what_to_expect, timeframe, status, source_fact_ids}`, `other[] {title, why, steps[], description, frequency, duration, status, source_fact_ids}`, `follow_up[] {time_frame, description, status, source_fact_ids}`, `warning_signs[] {symptom, what_it_might_mean, what_to_do, urgency: emergency|call_doctor|monitor|normal_side_effect|null, related_to, source_fact_ids}`, `questions[]` (max 3), `low_priority[]`, `terms: {matched_term: {definition, source}}`. Plugin additions at top level: `meta {run_id, plugin_version, schema_version, level, created_at}`, `notices[]`, `score {before_grade, after_grade}`. The agent-facing schema for assemble excludes `meta`, `notices`, `score`, `terms`. An empty string `why` is normalized to `null`.
- **`03_flags.json`**: `{numeric_parity: [{path, tokens_in_field, tokens_in_facts}], thin_fields: [{path, value}]}`. Numeric parity ports simplify-med's `_extract_number_tokens` / `_check_numeric_parity` (pipeline.py at `e0e1dce`), including the date and time-of-day exclusions and the unit-word bound of 15.
- **`04_review.raw.json`** / **`04_review.json`**: `{verdict: pass|needs_correction, corrections: [{op: correct|not_stated|remove, path, value?}]}`. Sanitize: path must resolve against the draft; `not_stated` only on `medications[N].why`, `tests[N].why`, `procedures[N].why`, `other[N].why`; `correct` needs a value; `remove` wins over other ops on the same item; `summary` may only be removed.
- **`04_coverage.raw.json`** / **`04_coverage.json`**: `{coverage: [{fact_id, present}]}`; sanitized file adds `missing: [fact ids]` and backfills any fact the agent skipped as `present: false`.
- **`05_additions.raw.json`** / **`05_additions.json`**: `{reason_for_visit[], diagnosis_details[], medications[], tests[], procedures[], other[], follow_up[], warning_signs[], low_priority[]}` with the same item shapes as the care plan. Every item must cite only ids from `missing`.
- **`run.json`**: `{run_id, plugin_version, schema_version, created_at, level, inputs, stages: {<stage>: {status: ok|degraded|failed|skipped, attempts, started_at, finished_at, checks: {...}}}, notices: [...]}`. `runlog.py` exposes `record(run_dir, stage, status, checks)` and every script calls it; agents do not write `run.json`.

### 3.4 Stage prompts

Ported from simplify-med's `backend/care_plan/prompts/` at `e0e1dce` with these changes: file I/O replaces API I/O (each stage says which file to read and which to write, and that the output is the JSON document alone); `ground.md` adds a rule that billing codes, insurance and administrative text are not facts; `review.txt` becomes two files, `review_fidelity.md` (JOB 1 plus a section that reads `03_flags.json` as hints to verify, never as automatic corrections) and `review_coverage.md` (JOB 2, enumerate-then-check every fact id in order); `assemble_missing.md` is new and bounded: given the draft plan and the list of missing facts, emit only new items built from those facts, in the care-plan item shapes, citing only those ids, and never touch existing items; `curate_glossary.txt` becomes `glossary.md`, propose-only (there is no dictionary hit list to filter), with the criterion, the 25 soft cap, the definition style examples, and the requirement that `matched_term` appear verbatim in the source. `reference/style_rules.md` carries simplify-med's `_style_rules.txt` (PII, NUMERACY, LANGUAGE RULES) plus one line: "Aim for about a 6th-grade reading level." `reference/categories.md` carries the category checklist table with criteria and boundary rules.

### 3.5 SKILL.md

Standard frontmatter only (`name: simplify-med`, `description`). Body: what the plugin does and the input contract; the run folder convention; the stage list in order with, for each stage, the script command or the agent to dispatch, its input files and its output file; which stages form a parallel group; the retry rule; the failure rule per stage; the finalize command and what to tell the user (where `report.html` and `report.md` are, the one-line reading-level result, and the notice if any); how to produce the audit view on request. A short "hosts without sub-agents" paragraph: perform each stage in the current context by reading the stage file and writing the output file, one stage at a time, in the same order.

### 3.6 Agents

Seven files under `agents/`, each with `name`, `description`, and a body of the form: read `${CLAUDE_PLUGIN_ROOT}/skills/simplify-med/stages/<stage>.md` and follow it exactly; the input and output paths are given in the dispatch message; write only the output file; reply with one line stating the output path and item count.

### 3.7 Rendering

`render_html.py` fills `templates/report.html` (Python `string.Template`) with HTML-escaped content and emits one file with inline CSS and JS. JS: checkbox state in `localStorage` under the run id; section collapse toggles; glossary term spans with a click-to-reveal definition; nothing else. Print stylesheet: sections expanded, checkboxes empty, no interactive affordances. `render_md.py` emits the same sections. Both omit `low_priority`, fact ids, and any provenance. The notice, when present, renders once at the top. The score renders as one line: "Reading level: grade X before, grade Y after."

### 3.8 Packaging

`build.py` reads `plugin.meta.json`, asserts `.claude-plugin/plugin.json` has the same version, walks the repo applying `packaging/<platform>.ignore`, and writes `dist/simplify-med-<version>-<platform>.zip`. `claude-code.ignore` excludes `docs/`, `tests/`, `dist/`, `packaging/`, `simplify-runs/`, `.git/`, `__pycache__/`. `claude-ai.ignore` excludes the same plus `agents/`, `.claude-plugin/`, `plugin.meta.json`, and roots the archive at `skills/simplify-med/`.

## 4. Non-goals

- No file parsing, OCR, or image handling; the host does it.
- No translation, audio, external resource links, follow-up conversation, memory, history across runs, caregiver view, visual aids, colour coding, multiple simplification levels, host-specific rendering, or health-literacy calculator. All are listed in `futures.md`.
- No LLM API calls from scripts. No network access anywhere.
- No dependencies outside the Python standard library.
- No versioned schema migration; 0.x may change the schema in place.

## 5. Uncalibrated constants

| Constant | Value | Where | Why this value | How it would be calibrated |
|---|---|---|---|---|
| Ground chunk size | 150 units | `unitize.py` | Fits a typical note in one agent; long documents scale by agent count | Run on long documents; measure recall against a hand-annotated ledger at 100/150/250 |
| Quote informativeness floor | 12 chars, or a 7+ char word, or a digit | `anchor_check.py` | Inherited from simplify-med PRD 03 | Same protocol as simplify-med's register |
| PII substitution token delta | 4 tokens | `diff_guard.py` | Inherited from simplify-med PRD 05 | Same |
| Numeric unit-word length | 15 | `numeric_parity.py` | Inherited from simplify-med PRD 10 | Same |
| Glossary soft cap | 25 | `stages/glossary.md` | Fewer than simplify-med's 40 backstop; the report should not speckle | Read glossaries on 10 real documents |
| Target reading level | grade 6 | `reference/style_rules.md` | AHRQ/CDC recommendation for patient materials | Compare after-grade across documents; adjust the rule wording |

## 6. Open risks

| Risk | Cheapest test |
|---|---|
| A host does not run bundled scripts or spawn agents reliably. | Sub-project 1: unitize, ground, anchor check on three documents, on Claude Code and on claude.ai. |
| Extraction recall from a single ground agent on raw text is too low. | Same test; hand-score the ledger. Chunk size is the lever. |
| Additions from assemble-missing are not LLM-reviewed. | Inject a fabricated addition in a fixture; assert cite_check drops it. Revisit if real runs show drift in added items. |
| The corrector reintroduces drift. | The diff guard is mechanical; a fixture with an out-of-scope edit must fall back to the draft with a notice. |
| Prose orchestration skips or reorders a stage on some host. | Every script records to `run.json`; `finalize.py` refuses to run if a fatal stage's record is missing and reports which. |
| The PII regex sweep changes a non-name. | Bounded pattern; count is recorded; a fixture with "Dr." in a drug name context asserts no change. |
| The single readability score is misread as a quality guarantee. | Report wording states it is a reading-level estimate only. |

## 7. Sub-projects

Implemented directly from this brief, in this order, one commit each. Parallel where marked.

1. **Skeleton**: `plugin.meta.json`, `.claude-plugin/plugin.json`, `README.md`, `.gitignore`, `packaging/`, `schema/*.json`, `scripts/validate.py`, `scripts/runlog.py`, `tests/` scaffold.
2. **Ground path** ‖ 3: `unitize.py`, `anchor_check.py`, `merge_facts.py`, `stages/ground.md`, `stages/glossary.md`, `reference/categories.md`, `reference/abbreviations.json`, `agents/ground.md`, `agents/glossary.md`, tests.
3. **Assemble path** ‖ 2: `stages/assemble.md`, `reference/style_rules.md`, `reference/ahrq_plain_language.json`, `cite_check.py`, `numeric_parity.py`, `agents/assemble.md`, tests.
4. **Review and correct** ‖ 5: `stages/review_fidelity.md`, `stages/review_coverage.md`, `stages/assemble_missing.md`, `stages/correct.md`, `sanitize_review.py`, `diff_guard.py`, the four agents, tests.
5. **Finalize and render** ‖ 4: `finalize.py`, `readability.py`, `render_md.py`, `render_html.py`, `templates/report.html`, `render_audit.py`, tests.
6. **Orchestration**: `SKILL.md`, end-to-end deterministic test through the whole script chain on a synthetic fixture with hand-written agent outputs, `build.py` run for both platforms.
7. **Kill test**: a sub-agent acting as the host runs the skill end to end on fixture documents and reports every friction point; fixes follow.
8. Fixes from kill test 1 and a harder two-file fixture (done); 9. Kill test 2 on the discharge summary plus lab report.

Owner-only: drop de-identified documents into `tests/fixtures/documents/` when available. Synthetic documents are used until then and are labelled synthetic.
