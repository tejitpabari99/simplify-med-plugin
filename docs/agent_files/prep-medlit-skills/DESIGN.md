# Design: Faster, Fail-Closed Simplify Workflow

Status: approved for implementation.

Baseline: branch `users/tejitpabari/add-med-skills`, HEAD `4e53e8e` (`fix: prioritize critical patient summary content`).

This design combines two previously separate concerns:

1. reduce model calls, duplicated context, artifacts, and repair stages; and
2. make explicit skill invocation execute the complete pipeline instead of returning an ad hoc simplification.

The redesign preserves the patient-relevance work introduced at `4e53e8e`. Critical facts remain visible. Supporting facts remain traceable but do not enter the patient report merely because they appeared in source paperwork.

## Problem

The current workflow is rigorous but unnecessarily expensive and still permits incomplete execution.

For `K` source chunks, a normal run uses `K + 4` model calls:

- `K` grounding calls;
- one full-source glossary call;
- one assembly call;
- one fidelity review call; and
- one coverage review call.

Correction and missing-fact repair can raise the total to `K + 6`. A one-chunk run therefore needs five model calls normally and up to seven when both repair branches run. It also creates roughly 20 core artifacts when copied source files are counted.

The model stages duplicate work:

- glossary rereads the entire source before the visible report is known;
- fidelity and coverage independently reread the same fact ledger and draft;
- correction rewrites the entire care plan to change a bounded set of fields;
- assemble-missing generates a second set of plan items that finalization later merges;
- several deterministic scripts accept missing outputs, degraded states, silently dropped content, or draft fallbacks.

The invocation contract is also weak. `SKILL.md` explains the workflow but does not state prominently that the workflow must finish before any clinical answer is shown. The three default prompts ask for a simplified care plan rather than explicitly requiring the pipeline. `allow_implicit_invocation` is enabled. As a result, a host can satisfy the apparent user outcome by writing a basic summary directly from the source.

Finally, the complete fact ledger can still exert pressure toward an overlong report. Commit `4e53e8e` correctly changed assembly and coverage guidance so that patient-critical facts are shown while generic education, technical mechanics, repeated details, and non-actionable background may be omitted. The new architecture must preserve and strengthen that distinction rather than returning to “one visible item per fact.”

## Goals

- Reduce the normal model workflow to `ground[1..K] -> assemble -> review`, or `K + 2` calls.
- Preserve deterministic source anchoring, schema validation, citation validation, numeric parity, exact bounded settlement, audit logging, rendering, and finalization.
- Require every verified fact to be either represented in visible patient content or assigned one audited omission disposition.
- Preserve all critical-vs-supporting relevance rules introduced by `4e53e8e`.
- Omit generic education and wellness advice unless the source makes it specific to this patient’s documented plan.
- Replace model-authored whole-plan correction with exact deterministic operations.
- Replace separate fidelity and coverage calls with one independent combined review.
- Make required stages fail closed. No patient report may be produced from missing, failed, degraded, stale, or silently skipped core stages.
- Make explicit invocation execute the complete workflow and return only the finalized report.
- Reduce a normal one-chunk run to approximately 13 core artifacts, excluding copied source documents and optional outputs.
- Keep old completed schema-v1 reports renderable without allowing schema-v1 in-progress runs to resume through the schema-v2 workflow.

## Non-Goals

- Removing grounding, independent semantic review, source citations, numeric checks, or auditability.
- Combining grounding and assembly into one model call.
- Replacing semantic review with a fact-ID set difference.
- Diagnosing, prescribing, adding generic medical advice, or changing the skill’s clinical scope.
- Making HTML, audit Markdown, or a glossary mandatory core outputs.
- Optimizing Python runtime. Existing deterministic tests complete in seconds; model calls and repeated context dominate latency and cost.
- Supporting automatic migration or continuation of partially completed schema-v1 run folders.
- Moving `agent_files/` or deleting `agent_files/agent-model-preferences.md` while writing this design. That repository cleanup is an implementation task, not part of this document-only change.

## Preserved Patient-Relevance Policy

This policy is locked and must remain explicit in `reference/style_rules.md`, `stages/assemble.md`, and the combined review stage.

### Critical facts normally visible

- medication starts, stops, changes, doses, frequencies, timing, duration, and home-use instructions;
- pending tests, referrals, appointments, monitoring, and follow-up timing;
- explicit warning signs, the required action, and the documented urgency;
- documented diagnoses, main clinician conclusions, and important abnormal or unresolved findings;
- results that directly explain the disposition, reassurance, or next step;
- uncertainty, conflicts, or conditional instructions that could change an action;
- the concise reason for the visit and the minimum context needed to understand the outcome.

### Supporting facts normally omitted from the patient view

- technical mechanics of a completed test, including contrast names, contrast doses, sequences, and device details;
- raw normal values and incidental findings that do not change the plan;
- repeated facts already represented by a clearer item;
- rejected differential diagnoses that do not change the main explanation or next action;
- broad education-sheet or wellness advice not made patient-specific in the documented plan;
- stable background history and unchanged medicines;
- completed-test details when the patient-relevant result is already represented;
- administrative and scheduling metadata that is not itself a clinical instruction.

Supporting facts are not discarded. Each is retained in the fact ledger and receives an audited omission disposition. The independent reviewer checks every omission and can require reassembly when a supposedly supporting fact is actually critical.

## Non-Negotiable Invocation Contract

The following meaning must appear prominently near the top of `skills/simplify/SKILL.md`:

```text
When this skill is selected or explicitly invoked, execute the complete
workflow. Never simplify, summarize, or answer directly from the supplied
documents.

Do not present clinical content until finalization succeeds and the current
run contains validated 06_plan.final.json and report.md artifacts.

Every expected grounding chunk, deterministic plan check, independent
semantic review, bounded settlement, and final validation is required. A
required stage may not be silently skipped, degraded, or replaced with an
ordinary response.

If a required stage still fails after its allowed retry, stop and report the
workflow failure without providing a substitute medical summary.

Present only report.md. Do not create a second summary from the source,
fact ledger, draft, or review artifacts.
```

All three metadata entry points use the same prompt text:

```text
Run the complete $simplify workflow on the supplied medical documents.
Return only the validated final report and requested artifacts. Do not
summarize the documents directly.
```

`skills/simplify/agents/openai.yaml` sets `allow_implicit_invocation: false`. Invocation policy reduces accidental activation of an expensive medical workflow; it does not replace the pipeline’s own fail-closed enforcement.

## Current Call Graph

`||` marks model work that may run concurrently.

```text
UNITIZE
  -> ground[1..K] || glossary
  -> ANCHOR_CHECK + MERGE_FACTS + GLOSSARY_CHECK
  -> assemble
  -> CITE_CHECK + NUMERIC_PARITY
  -> review-fidelity || review-coverage
  -> SANITIZE_REVIEW
  -> correct? || assemble-missing?
  -> DIFF_GUARD + CITE_CHECK --additions
  -> FINALIZE
```

Normal calls: `K + 4`.

Maximum calls with both repair branches: `K + 6`.

## Proposed Call Graph

```text
UNITIZE
  -> ground[1..K] in parallel
  -> ANCHOR_CHECK for every expected chunk
  -> MERGE_FACTS
  -> assemble
  -> CITE_AND_DISPOSITION_CHECK + NUMERIC_PARITY
  -> review
       - fidelity, negation, uncertainty, status, urgency
       - critical-vs-supporting omission review
       - every fact reviewed
       - every numeric flag resolved
       - bounded operations only
  -> SETTLE_REVIEW
       - validate exhaustive review
       - apply exact operations deterministically
       - rerun citation/disposition and numeric assertions
  -> FINALIZE
  -> optional glossary, HTML, or audit rendering
```

Normal calls: `K + 2`.

For a one-chunk document, the clean path is exactly three model calls: ground, assemble, review.

There are three model latency waves on a clean run. The primary gains are fewer calls, fewer tokens, less repeated context, no full-plan correction rewrite, and less queue/capacity pressure. Wall-clock improvement must be benchmarked rather than inferred from call count alone.

## Retry and Repair Policy

- Each model stage receives one retry for invalid JSON, schema failure, or deterministic validation failure.
- A failed grounding chunk is retried independently. All expected chunks must pass before merge.
- If assembly fails schema, citation, or disposition validation, retry assembly once with the exact validator errors.
- If review identifies a critical omitted fact, it emits `reassemble_fact_ids`. Settlement stops without producing a settled plan.
- Reassembly receives only the accepted draft, relevant facts, and required fact IDs. It rewrites the plan once, after which deterministic checks and a fresh independent review run again.
- New patient-facing prose can never bypass independent review.
- A second review that still requests reassembly fails the run. There is no unbounded repair loop.
- Failed raw outputs are retained under attempt-suffixed filenames for auditability. The clean path keeps the unsuffixed artifact names listed below.

The issue path therefore adds one assembly and one review call only when semantic repair is required. For one chunk, the maximum designed path is five model calls rather than the current seven.

## Locked Architecture Decisions

### 1. Three model responsibilities

1. `ground`: extract complete, atomic, source-anchored facts per chunk.
2. `assemble`: create a concise patient-facing plan and explicitly classify omitted facts.
3. `review`: independently inspect the complete fact set, visible plan, omissions, and numeric flags.

No other core stage uses a model.

### 2. Complete-clause grounding

Grounding remains exhaustive within the eight clinical categories. Quotes must include enough of the source clause to preserve negation, uncertainty, conditions, dose, units, frequency, timing, body site, and status. A tiny matching quote may not support contradictory or richer free-form `text`.

`anchor_check.py` remains separate from `merge_facts.py` so exact source matching remains independently testable. Any rejected fact or missing expected chunk is fatal after the one allowed retry.

### 3. Explicit fact dispositions

`low_priority: [string]` is replaced by structured `omitted_facts`:

```json
{
  "omitted_facts": [
    {
      "fact_id": 17,
      "reason": "generic_not_patient_specific"
    }
  ]
}
```

Allowed reasons are fixed:

- `duplicate_or_already_represented`
- `technical_detail`
- `routine_non_actionable`
- `rejected_non_actionable_differential`
- `generic_not_patient_specific`
- `stable_unchanged_background`

Every verified fact ID must appear exactly once in one of two sets:

- the union of `source_fact_ids` attached to visible content; or
- `omitted_facts`.

A fact may be cited by more than one visible field when safety requires repetition, but it may not also be marked omitted. The deterministic plan check rejects unknown fact IDs, duplicate omission entries, uncovered facts, and facts that are both visible and omitted.

### 4. Questions become cited content

The current `questions: [string]` shape allows unsupported assumptions. It becomes:

```json
{
  "question": "Do I need another heart tracing?",
  "source_fact_ids": [12]
}
```

Questions remain optional and capped at three. They are rendered only when they help the patient ask about documented uncertainty, follow-up, or an unresolved finding. Generic “questions to ask” filler is omitted.

### 5. One independent combined review

The combined review reads `02_facts.json`, `03_plan.draft.json`, and `03_flags.json`. It does not see or rewrite the original source documents. It emits a compact review contract rather than another care plan.

The raw review contains:

- `reviewed_fact_ids`: every verified fact ID exactly once;
- `fact_reviews`: one result per fact, using `visible_accurate`, `visible_needs_correction`, `omission_acceptable`, or `must_include`;
- `corrections`: bounded `replace`, `clear`, or `remove` operations;
- `numeric_resolutions`: one resolution for every numeric flag;
- `reassemble_fact_ids`: critical omitted facts that require new patient-facing prose.

The model does not author aggregate verdicts or counts. Python derives them.

### 6. Exact bounded settlement

`sanitize_review.py` and `diff_guard.py` are replaced by `settle_review.py`.

Settlement:

- validates review completeness and path syntax;
- rejects unknown paths and protected system fields;
- permits only `replace`, `clear`, and `remove`;
- applies the exact requested replacement value, not merely any changed value;
- requires every accepted operation to be applied exactly once;
- rejects unnamed changes, array reordering, partial application, and extra edits;
- prevents a correction from adding a new uncited clinical claim;
- refuses to settle while `reassemble_fact_ids` is non-empty;
- reruns citation/disposition and numeric checks in assertion mode;
- writes `04_review.json` and `05_plan.settled.json` only after all checks pass.

New content is never introduced by settlement. Missing critical content returns to assembly and then receives another independent review.

### 7. Numeric parity remains independent

`numeric_parity.py` remains a separate safety boundary and still creates `03_flags.json` after draft assembly. Each flag receives a stable `flag_id`.

The review must resolve every flag as:

- `equivalent`: source-faithful formatting only;
- `corrected`: an exact correction operation fixes it; or
- `removed`: a remove or clear operation removes the unsupported numeric content.

`settle_review.py` imports the numeric checker and runs it against the settled plan without creating another core artifact. Unresolved, newly introduced, or contradictory numeric content fails settlement.

### 8. Finalization is assertion-only for clinical content

`finalize.py` loads only `05_plan.settled.json`. It does not fall back to the draft, merge additions, drop uncited items, or silently repair clinical fields.

Before publication it requires exact `ok` statuses and current-run artifacts for:

- `unitize`
- `ground`
- `assemble`
- `plan_check`
- `numeric_parity`
- `review`
- `settle_review`

Finalization reruns schema, citation/disposition, numeric, run-ID, and version assertions. It may perform the existing bounded PII substitution and calculate readability telemetry, then validates the resulting final plan before writing `06_plan.final.json` and `report.md`.

Required core stages may never be `skipped` or `degraded`. Optional enrichment and optional render stages may be absent or explicitly skipped with a reason.

### 9. Glossary becomes optional post-finalization enrichment

Glossary generation is removed from the normal call graph. When explicitly requested, it reads only patient-visible finalized content, proposes no more than five relevant terms, and writes optional `07_glossary.raw.json` and `07_glossary.json` artifacts.

The immutable core `06_plan.final.json` and `report.md` are not changed. Optional glossary-aware output may be rendered as `report.glossary.md` or incorporated into requested HTML. A glossary definition never changes or interprets the patient’s result.

### 10. Audit and presentation remain separate

`report.md` is the only default patient-facing output. `report.html`, `report.glossary.md`, and `report.audit.md` are optional.

The patient report never renders `omitted_facts`, raw model output, internal checks, reading-level telemetry, or technical notices. The audit report resolves omitted fact IDs back to source quotes and shows the omission reason and review result.

## Core Artifact Contract

Normal one-chunk core artifacts, excluding copied source documents:

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

This is approximately 13 core artifacts and three model-authored raw artifacts.

Changes from the current artifact set:

- remove duplicate `00_input/manifest.json`; input metadata remains in `run.json`;
- remove `02_facts.txt`; assembly and review use `02_facts.json`;
- remove core glossary artifacts;
- remove separate fidelity and coverage artifacts;
- remove corrected-plan raw/full rewrite artifacts;
- remove additions artifacts;
- add one combined review artifact;
- replace `05_plan.corrected.json` with `05_plan.settled.json`.

Copied source documents under `00_input/` remain local and are not included in the 13-artifact target.

## Schema Migration

The pipeline schema version changes from `1.0` to `2.0`.

### Core schemas retained and changed

- `units.schema.json`: retain; add input digest/run identity fields only if needed by the unitization implementation.
- `facts_raw.schema.json`: retain; preserve the compact model output and validate chunk identity from the command/file contract.
- `facts.schema.json`: retain; remove dependence on `02_facts.txt` and keep complete source metadata.
- `care_plan_agent.schema.json`: replace `low_priority` with structured `omitted_facts`; replace string questions with cited question objects.
- `care_plan.schema.json`: mirror the new patient-content contract and system-owned metadata; remove core glossary terms.
- `flags.schema.json`: retain; add stable `flag_id` values.
- `review_raw.schema.json`: expand to the combined fact, omission, correction, and numeric review contract.
- `review.schema.json`: store sanitized operations, per-fact decisions, numeric resolutions, dropped-invalid-operation records, and Python-derived counts/verdict.
- `run.schema.json`: constrain recognized stage names and add produced-artifact and skip-reason fields.

### Optional schemas retained

- `glossary_raw.schema.json`
- `glossary.schema.json`

These validate the post-finalization optional glossary only.

### Schemas removed

- `manifest.schema.json`
- `coverage_raw.schema.json`
- `coverage.schema.json`
- `additions_raw.schema.json`
- `additions.schema.json`

The core schema count falls from 16 to 9, with two optional glossary schemas retained.

## Backward Compatibility

- Completed schema-v1 `06_plan.final.json` files remain renderable.
- `render_md.py` and `render_html.py` detect schema version and support both legacy string questions/`low_priority` and schema-v2 cited questions/`omitted_facts`.
- `render_audit.py` supports legacy `04_coverage.json` when rendering a completed v1 run and combined `04_review.json` for v2.
- Schema-v1 in-progress runs cannot resume, settle, or finalize through schema-v2 code.
- `finalize.py` fails with a clear non-clinical migration message when given v1 intermediate artifacts.
- Old run folders are never rewritten in place by render-only compatibility paths.
- No general v1-to-v2 conversion script is added. Regenerating from the original local source is the supported path.
- `_version.py` changes `SCHEMA_VERSION` to `2.0`. Plugin package versioning remains controlled by the existing release build; the next release must record the behavioral change.

## Run Identity and Stage Logging

- A newly prepared run may not inherit generated artifacts from an older attempt.
- `unitize.py` creates a fresh run directory identity for each execution while retaining an input content digest in `run.json` for comparison.
- `runlog.py` records recognized stage names only, increments real attempt counts, and records every produced artifact.
- A stage entry includes `status`, `attempts`, timestamps, checks, artifacts, and an optional `skip_reason`.
- Core stage status is exactly `ok` or `failed`. `degraded` is reserved for optional non-clinical enrichment only.
- Grounding model calls may run in parallel, but deterministic anchor checks and aggregate ground logging run after the model outputs are present. This avoids concurrent read-modify-write updates to `run.json`.
- Every artifact carrying structured data includes the current `run_id`, schema version, and plugin version where the schema permits system-owned metadata.

## Exact File-by-File Changes

### Repository organization

- `agent_files/agent-model-preferences.md`: delete during implementation.
- `agent_files/ask-research.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/decisions.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/futures.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/med-lit-patient-research.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/med-lit-research.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/prep-direction.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `agent_files/prep-research.md`: move to `docs/agent_files/prep-medlit-skills/`.
- `docs/agent_files/prep-medlit-skills/TASKS.md`: create after this design, with implementation tasks in dependency order.

### Skill entry points and instructions

- `skills/simplify/SKILL.md`: add the non-negotiable execution contract; replace the seven-stage workflow with the three-model-stage graph; define retries, fail-closed behavior, artifact gates, presentation-only-from-`report.md`, and optional post-finalization outputs.
- `skills/simplify/agents/openai.yaml`: synchronize the complete-workflow prompt and set `allow_implicit_invocation: false`.
- `plugin.json`: synchronize the complete-workflow default prompt.
- `.codex-plugin/plugin.json`: synchronize the complete-workflow default prompt.
- `skills/simplify/reference/style_rules.md`: make the critical-vs-supporting relevance policy canonical while preserving the current PII, numeracy, plain-language, action-first, no-filler, and no-generic-advice rules from `4e53e8e`.

### Model stages

- `skills/simplify/stages/ground.md`: retain; strengthen complete-clause evidence and preservation of negation, uncertainty, conditions, numbers, units, and status.
- `skills/simplify/stages/assemble.md`: retain; read `02_facts.json`; preserve the `4e53e8e` relevance rules; emit cited questions and a complete `omitted_facts` disposition list; keep summary to two or three short sentences; never add generic education merely because it was attached to discharge paperwork.
- `skills/simplify/stages/review_fidelity.md`: rename to `skills/simplify/stages/review.md` and rewrite as the independent combined review.
- `skills/simplify/stages/review_coverage.md`: delete after its enumerate-every-fact and critical-coverage rules are incorporated into `review.md`.
- `skills/simplify/stages/correct.md`: delete; exact operations are applied by `settle_review.py`.
- `skills/simplify/stages/assemble_missing.md`: delete; critical omissions trigger bounded reassembly followed by a new review.
- `skills/simplify/stages/glossary.md`: retain as optional; change input from all source chunks to finalized visible content and use post-finalization artifact names.

### Deterministic scripts

- `skills/simplify/scripts/_version.py`: bump schema version to `2.0`; keep plugin version release-managed.
- `skills/simplify/scripts/unitize.py`: remove duplicate input manifest generation; create fresh run identity; keep copied local inputs, units, chunk files, extraction metadata, and input digest.
- `skills/simplify/scripts/anchor_check.py`: retain as a separate exact-anchor boundary; reject unsupported or insufficient evidence and return failure for retry.
- `skills/simplify/scripts/merge_facts.py`: require every chunk declared by `01_units.json`; fail on missing/invalid chunks or rejected facts; stop writing `02_facts.txt`; record one aggregate ground result.
- `skills/simplify/scripts/cite_check.py`: retain and narrow to plan validation; remove additions mode; validate all visible citations, cited questions, summary and changed-since fields, and complete visible-or-omitted fact disposition; never silently drop content; expose assertion helpers for settlement/finalization.
- `skills/simplify/scripts/numeric_parity.py`: retain; add stable flag IDs and an in-memory strict post-settlement API while preserving the initial `03_flags.json` CLI output.
- `skills/simplify/scripts/sanitize_review.py`: rename to `skills/simplify/scripts/settle_review.py`; replace split review sanitization with exhaustive combined-review validation and exact deterministic operation application.
- `skills/simplify/scripts/diff_guard.py`: delete after path, operation, PII-substitution, array-removal, and unnamed-change protections move into `settle_review.py` and its tests.
- `skills/simplify/scripts/finalize.py`: require every core stage and artifact; load only `05_plan.settled.json`; remove draft fallback, additions merge, silent citation dropping, and fail-open notices; rerun final assertions; keep bounded PII sweep, readability telemetry, final schema validation, JSON output, and Markdown rendering.
- `skills/simplify/scripts/runlog.py`: constrain stage names; record attempts, artifacts, skip reasons, and current-run identity; avoid parallel writers.
- `skills/simplify/scripts/plan_view.py`: render cited schema-v2 questions; never render omitted facts; retain schema-v1 compatibility.
- `skills/simplify/scripts/render_md.py`: retain concise patient view; support schema-v1 and schema-v2 question shapes; do not render internal telemetry or omissions.
- `skills/simplify/scripts/render_html.py`: retain as optional; support schema-v1 and schema-v2; accept optional glossary data without mutating the final plan.
- `skills/simplify/scripts/render_audit.py`: read combined review and dispositions for v2; retain legacy v1 coverage rendering; show source location, quote, extraction method, omission reason, and reviewer resolution.
- `skills/simplify/scripts/glossary_check.py`: validate optional post-finalization glossary against terms that actually appear in visible final content; write `07_glossary.json`.
- `skills/simplify/scripts/validate.py`: retain unchanged unless new schema keywords require support.
- `skills/simplify/scripts/textnorm.py`: retain unchanged.
- `skills/simplify/scripts/readability.py`: retain unchanged.

### Schemas

- Update the nine core and two optional schemas exactly as described in “Schema Migration.”
- Delete the five obsolete schemas listed there.

### Documentation

- `README.md`: update the workflow summary, default output, explicit invocation behavior, optional outputs, and artifact count.
- `docs/overview.md`: explain concise critical-first output, audited omissions, and the three-stage model workflow.
- `docs/architecture.md`: replace the current graph, artifact table, stage descriptions, failure policy, review split rationale, and glossary behavior; retain the Python-vs-model boundary described by `docs/openai-plugin.md`.
- `docs/openai-plugin.md`: no behavioral rewrite required; only add a short reusable note if implementation introduces a generally applicable fail-closed skill convention.

### Tests

- `tests/test_anchor_check.py`: add insufficient-clause, negation, uncertainty, conditional, and numeric-evidence failures.
- `tests/test_merge_facts.py`: change missing or invalid expected chunks and rejected facts from degraded success to failure; remove text-ledger expectations.
- `tests/test_cite_check.py`: add exhaustive disposition, cited-question, unsupported-summary, unknown-ID, duplicate-omission, critical generic-advice, and no-silent-drop cases; remove additions-mode cases.
- `tests/test_numeric_parity.py`: add stable flag IDs, exhaustive review resolution, post-settlement strict checks, and newly introduced numeric mismatch cases.
- `tests/test_sanitize_review.py`: replace with `tests/test_settle_review.py`; migrate useful path tests and add exact value, complete application, protected path, array order, unknown operation, reassembly, and unresolved-flag failures.
- `tests/test_diff_guard.py`: delete after all relevant protections move to `test_settle_review.py`.
- `tests/test_finalize.py`: require all core statuses and artifacts; assert no draft fallback, no degraded core stage, no additions merge, no missing review, no stale run ID, and no output on failure.
- `tests/test_runlog.py`: test constrained names, real attempt counts, artifact records, skip reasons, and current-run identity.
- `tests/test_plan_view.py`: test schema-v2 cited questions, hidden omissions, and schema-v1 compatibility.
- `tests/test_render_md.py`: test concise output, cited questions, no omission leakage, no telemetry, no generic education, and v1 compatibility.
- `tests/test_render_html.py`: mirror Markdown compatibility and optional glossary behavior.
- `tests/test_render_audit.py`: test v2 omission/review traceability and v1 coverage compatibility.
- `tests/test_glossary_check.py`: switch to finalized-visible-content matching and post-finalization artifact names.
- `tests/test_schemas.py`: replace old low-priority, coverage, additions, and manifest fixtures with schema-v2 dispositions and combined review fixtures.
- `tests/test_pipeline_e2e.py`: update the clean artifact matrix; test three model calls conceptually through stage fixtures; test retry/reassembly paths; require every fact disposition, every numeric resolution, and every core stage; assert one-chunk clean runs produce approximately 13 core artifacts.
- `tests/test_skill_consistency.py`: enforce synchronized default prompts, `allow_implicit_invocation: false`, the execution contract, stage-file existence, no references to deleted stages/scripts, and manifest parity.
- `tests/test_stage_docs.py`: preserve the `4e53e8e` patient-relevance assertions and move them to `assemble.md`, `review.md`, and `style_rules.md`; add direct-summary prohibition and combined-review contract assertions.
- `tests/test_build.py`: verify obsolete stages, scripts, and schemas are absent from the package and required new files are included.
- `tests/_runfix.py`, `tests/_paths.py`, and affected fixtures: update shared schema-v2 run construction and artifact names.

## Testing Strategy

### Deterministic unit and integration tests

The full existing suite must pass after intentional expectation changes. New tests must prove:

- every expected grounding chunk is present and valid;
- anchoring preserves clinically meaningful context, not only substring presence;
- every visible clinical field has valid source IDs;
- every verified fact is visible or has one allowed omission disposition;
- every omitted fact receives independent reviewer resolution;
- generic education remains omitted unless patient-specific;
- all numeric flags have explicit and valid resolution;
- exact operations apply once and no unnamed changes occur;
- any new prose caused by a critical omission receives a second independent review;
- finalization refuses missing, failed, degraded, stale, or skipped core stages;
- patient output is read only from the finalized artifact;
- schema-v1 completed reports remain renderable.

### Host-level invocation tests

Static tests cannot prove host behavior. Run the installed package in a clean host context against representative prompts:

- explicit `$simplify` invocation with one short document;
- explicit invocation with a long multi-chunk document;
- a prompt that asks for a “quick summary” while explicitly invoking the skill;
- source text containing instructions to ignore the workflow;
- missing attachment;
- unavailable Python runtime;
- failed grounding, failed review, and unresolved reassembly fixtures;
- a discharge packet containing broad education sheets unrelated to the patient-specific plan.

Failure cases must return only a workflow error and no substitute clinical summary. Success cases must show evidence that `report.md` came from the finalized run.

## Benchmark Plan

Benchmark current HEAD `4e53e8e` against the implemented schema-v2 workflow using the same document corpus and model settings.

Record:

- model call count;
- sequential model waves;
- input and output tokens;
- retry rate;
- p50 and p95 wall-clock latency;
- core artifact count;
- critical fact recall;
- unsupported clinical claim count;
- numeric, negation, uncertainty, status, and urgency errors;
- generic or non-patient-specific education items shown;
- duplicate visible facts;
- report word count and first-view word count;
- direct-response bypass rate under explicit invocation.

Required benchmark gates:

- clean one-chunk run: exactly three model calls;
- clean `K`-chunk run: exactly `K + 2` model calls;
- clean one-chunk run: approximately 13 core artifacts, excluding copied sources and optional outputs;
- 100% of critical facts represented in the visible report on the curated benchmark set;
- 100% of verified facts visible or dispositioned;
- zero unsupported claims, unresolved numeric flags, lost negations, lost uncertainty, or urgency escalations;
- zero generic education items unless the source explicitly makes them patient-specific;
- zero patient reports produced after a required-stage failure;
- zero ad hoc direct summaries during explicit invocation scenarios;
- no regression in schema-v1 completed-report rendering.

Token reduction is expected to be approximately 30–50% on normal runs, with model-call reduction of 40% for one chunk and larger savings on former correction-heavy paths. These are benchmark hypotheses, not acceptance criteria unless measured.

## Acceptance Criteria

- Explicit skill invocation never produces clinical prose before successful finalization.
- The only default response content is the validated `report.md` plus a minimal artifact-location note when appropriate.
- `allow_implicit_invocation` is false and all default prompts require the complete workflow.
- The core model workflow contains only ground, assemble, and one independent review.
- A clean one-chunk run uses exactly three model calls.
- Every declared chunk passes anchor validation before facts merge.
- Missing chunks, rejected facts, absent reviews, invalid review output, unresolved numeric flags, unapplied corrections, stale run IDs, and missing artifacts prevent publication.
- Every verified fact is either represented by visible cited content or has exactly one allowed omission disposition.
- The reviewer evaluates every fact and every omission.
- Generic education, technical test mechanics, repeated normal details, and stable unchanged background remain out of the patient report unless they are patient-critical.
- Medication changes, pending work, follow-up timing, warning signs, urgency, main conclusions, important abnormal or unresolved findings, and disposition-driving results remain visible.
- All patient-facing questions are cited or absent.
- Settlement makes only named, exact, bounded changes and cannot introduce new prose.
- Reviewer-requested missing content returns to assembly and then receives a new independent review.
- Finalization reads only `05_plan.settled.json` and never falls back to a draft.
- Required core stages are all `ok`; `degraded` and `skipped` cannot satisfy finalization.
- `06_plan.final.json` and `report.md` validate against the current run, schema, and plugin versions.
- The normal one-chunk core artifact set is approximately 13 files.
- Optional glossary, HTML, and audit rendering do not alter the immutable core final plan.
- Completed schema-v1 reports remain renderable; schema-v1 partial runs fail with a clear migration message.
- The full deterministic test suite and package build pass.
- Installed-skill tests demonstrate no direct-summary bypass.

## Manual Steps

1. Move the seven retained top-level `agent_files/*.md` files into `docs/agent_files/prep-medlit-skills/` and delete `agent_files/agent-model-preferences.md`.
2. Create `docs/agent_files/prep-medlit-skills/TASKS.md` from this approved design.
3. Implement tasks in dependency order, with focused tests after each safety boundary.
4. Run the complete unit/integration suite.
5. Build a development plugin archive and inspect its contents for new/obsolete file parity.
6. Install the development package in a clean Codex/OpenAI host and run the host-level invocation scenarios.
7. Run the baseline-versus-v2 benchmark corpus and record the measured results.
8. Manually inspect at least one education-heavy discharge packet to confirm the patient report contains only critical patient-specific content while the audit retains omitted facts.
9. Use the existing release build process to update package versions when the measured quality gates pass.

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| D1 | Preserve the `4e53e8e` critical-vs-supporting relevance policy. | The main quality failure is excessive non-patient-specific detail, not missing generic education. |
| D2 | Use three core model responsibilities: ground, assemble, review. | This removes repeated reads and repair rewrites without removing independent semantic review. |
| D3 | Target `K + 2` normal calls. | It is the lowest call count that retains separate extraction, generation, and independent review. |
| D4 | Keep anchoring, citation/disposition checks, numeric parity, settlement, logging, rendering, and finalization deterministic. | These are exact, testable safety boundaries and are not suitable for prompt-only enforcement. |
| D5 | Replace `low_priority` with structured omitted-fact dispositions. | Every fact stays auditable without forcing supporting detail into the patient report. |
| D6 | Combine fidelity, critical coverage, omission review, and numeric resolution into one independent review. | The checks share the same ledger and draft; one exhaustive contract avoids duplicated context. |
| D7 | Apply corrections deterministically and exactly. | A model should not rewrite a complete plan to change a few fields, and “some change occurred” is not sufficient proof. |
| D8 | Send missing critical prose back to assembly and then review again. | Newly generated patient content must never bypass independent review. |
| D9 | Fail closed for every core stage. | A degraded or partial medical workflow must not silently become a publishable report. |
| D10 | Disable implicit invocation and synchronize complete-workflow prompts. | The skill is expensive and safety-sensitive; explicit activation and consistent entry-point intent reduce bypasses. |
| D11 | Present only finalized `report.md`. | A second host-authored summary would bypass the validated artifact and recreate the original adherence problem. |
| D12 | Make glossary, HTML, and audit rendering optional post-finalization outputs. | They are useful presentation features but should not add latency to the default clinical workflow. |
| D13 | Remove duplicate manifest, text ledger, coverage, correction, and additions artifacts. | They duplicate existing structured state or belong to deleted stages. |
| D14 | Bump the pipeline schema to v2 and reject partial v1 continuation. | The plan, review, run-log, and artifact contracts are intentionally breaking. |
| D15 | Keep completed v1 reports renderable. | Existing user artifacts remain useful without complicating the new core pipeline. |
| D16 | Do not merge anchor and numeric modules merely to reduce file count. | Independent, testable safety boundaries are more valuable than a cosmetically smaller script directory. |
| D17 | Treat call/token savings as measured outcomes, not assumed latency guarantees. | Parallel hosts may retain the same number of clean latency waves even with fewer calls. |
| D18 | Move the existing research files and delete `agent-model-preferences.md` during implementation, not during this design-only change. | Repository organization is approved but outside the single-file write constraint for this step. |

There are no open design questions. Implementation must follow the locked decisions and acceptance criteria above.
