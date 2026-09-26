# Tasks: Faster, Fail-Closed Simplify Workflow

Source of truth: `docs/agent_files/prep-medlit-skills/DESIGN.md` (approved). Implement only the behavior specified there. Tasks are dependency-ordered; a task may start only after all listed dependencies are complete.

### Task 1 — Move retained research files and remove the obsolete preference file

- **Files:** `agent_files/ask-research.md`, `agent_files/decisions.md`, `agent_files/futures.md`, `agent_files/med-lit-patient-research.md`, `agent_files/med-lit-research.md`, `agent_files/prep-direction.md`, `agent_files/prep-research.md`, `agent_files/agent-model-preferences.md`, `docs/agent_files/prep-medlit-skills/ask-research.md`, `docs/agent_files/prep-medlit-skills/decisions.md`, `docs/agent_files/prep-medlit-skills/futures.md`, `docs/agent_files/prep-medlit-skills/med-lit-patient-research.md`, `docs/agent_files/prep-medlit-skills/med-lit-research.md`, `docs/agent_files/prep-medlit-skills/prep-direction.md`, `docs/agent_files/prep-medlit-skills/prep-research.md`
- **Depends on:** Nothing.
- **Parallelization / write set:** Independent repository-cleanup write set; may run in parallel with Tasks 2–5. Do not edit `DESIGN.md` or `TASKS.md` while moving files.
- **Changes:** Move the seven retained Markdown files from top-level `agent_files/` into `docs/agent_files/prep-medlit-skills/` without content changes. Delete `agent_files/agent-model-preferences.md`. Remove the empty top-level directory only if no files remain.
- **Focused tests:** Use `git diff --summary` and content comparison against the pre-move blobs to verify seven renames with unchanged contents and one deletion.
- **Acceptance criteria:** All seven retained files exist only under `docs/agent_files/prep-medlit-skills/`; `agent_files/agent-model-preferences.md` is absent; no retained research content changed.

### Task 2 — Establish schema-v2 contracts and version metadata

- **Files:** `skills/simplify/scripts/_version.py`, `skills/simplify/schema/units.schema.json`, `skills/simplify/schema/facts_raw.schema.json`, `skills/simplify/schema/facts.schema.json`, `skills/simplify/schema/care_plan_agent.schema.json`, `skills/simplify/schema/care_plan.schema.json`, `skills/simplify/schema/flags.schema.json`, `skills/simplify/schema/review_raw.schema.json`, `skills/simplify/schema/review.schema.json`, `skills/simplify/schema/run.schema.json`, `skills/simplify/schema/glossary_raw.schema.json`, `skills/simplify/schema/glossary.schema.json`, `skills/simplify/schema/manifest.schema.json`, `skills/simplify/schema/coverage_raw.schema.json`, `skills/simplify/schema/coverage.schema.json`, `skills/simplify/schema/additions_raw.schema.json`, `skills/simplify/schema/additions.schema.json`, `skills/simplify/scripts/validate.py`, `tests/test_schemas.py`, `tests/test_validate.py`
- **Depends on:** Nothing.
- **Parallelization / write set:** Foundation schema write set; may run in parallel with Task 1, but must finish before Tasks 3–10. No other task edits schema files or `_version.py`.
- **Changes:** Set `SCHEMA_VERSION` to `2.0` while leaving plugin versioning release-managed. Implement the nine core schemas and two optional glossary schemas exactly as specified in the design: structured `omitted_facts`; cited question objects; stable numeric `flag_id`; combined raw/sanitized review contracts; constrained run stages with artifacts and optional skip reasons; current-run/schema/plugin metadata where allowed. Delete the manifest, coverage, and additions schema pairs. Change `validate.py` only if the new schemas use unsupported validation keywords.
- **Focused tests:** Replace schema-v1 plan/review fixtures in `tests/test_schemas.py` with schema-v2 disposition, cited-question, numeric-resolution, and combined-review fixtures. Add rejection cases for invalid omission reasons, duplicate/unknown shapes, uncited questions, incomplete review structures, invalid stage names/statuses, and malformed artifact records. Keep validator tests passing if `validate.py` changes.
- **Acceptance criteria:** Exactly nine core and two optional glossary schemas remain; obsolete schemas are absent; valid schema-v2 artifacts pass; old `low_priority`, coverage, additions, and manifest fixtures fail or are removed as appropriate; `_version.py` reports schema `2.0`.

### Task 3 — Make run preparation and grounding aggregation fail closed

- **Files:** `skills/simplify/scripts/unitize.py`, `skills/simplify/scripts/anchor_check.py`, `skills/simplify/scripts/merge_facts.py`, `skills/simplify/scripts/runlog.py`, `tests/test_unitize.py`, `tests/test_anchor_check.py`, `tests/test_merge_facts.py`, `tests/test_runlog.py`
- **Depends on:** Task 2.
- **Parallelization / write set:** Deterministic input/grounding write set; may run in parallel with Tasks 4 and 5 after Task 2. Do not edit plan, review, settlement, rendering, or entry-point files.
- **Changes:** Remove duplicate `00_input/manifest.json` generation; create a fresh run identity for each prepared run while retaining copied inputs, extraction metadata, units/chunks, and input digest. Strengthen anchoring so evidence must preserve the complete clinical clause, including negation, uncertainty, conditions, numbers/units, body site, timing, and status. Require every chunk declared by `01_units.json`; fail after the allowed retry on missing/invalid chunk output or rejected fact; stop producing `02_facts.txt`; record one aggregate ground result only after parallel outputs and deterministic checks complete. Constrain `runlog.py` to recognized stages, real attempt counts, timestamps/checks/artifacts, optional skip reasons, current-run identity, and no concurrent read-modify-write logging.
- **Focused tests:** Add insufficient-clause, negation, uncertainty, conditional, and numeric-evidence anchor failures. Change merge tests so missing/invalid expected chunks and rejected facts are fatal and text-ledger output is absent. Test fresh run IDs, stable input digests, no generated-artifact inheritance, constrained stage names, exact attempt increments, artifact records, skip reasons, and current-run ownership.
- **Acceptance criteria:** Facts merge only after every declared chunk passes anchoring; no degraded grounding success exists; each new execution has a fresh `run_id`; `run.json` is the sole input manifest; `02_facts.txt` is never written; aggregate ground logging is race-free and tied to the current run.

### Task 4 — Enforce exhaustive plan dispositions and numeric parity

- **Files:** `skills/simplify/scripts/cite_check.py`, `skills/simplify/scripts/numeric_parity.py`, `tests/test_cite_check.py`, `tests/test_numeric_parity.py`
- **Depends on:** Task 2.
- **Parallelization / write set:** Deterministic plan-validation write set; may run in parallel with Tasks 3 and 5 after Task 2. Its exported assertion APIs are consumed by Tasks 6 and 7.
- **Changes:** Narrow `cite_check.py` to plan validation and remove additions mode. Validate citations for every visible clinical field, summary, changed-since field, and cited question. Require every verified fact ID to be visible or appear exactly once in `omitted_facts`; reject unknown IDs, duplicate omissions, visible-and-omitted facts, uncovered facts, unsupported summary content, invalid omission reasons, and silent dropping. Preserve the critical-versus-supporting policy, including rejection of generic advice presented as patient-specific. Add reusable in-memory assertion helpers for settlement/finalization. Add stable `flag_id` values in `numeric_parity.py`, preserve initial `03_flags.json` CLI output, and expose a strict in-memory post-settlement check that rejects unresolved, contradictory, or newly introduced numeric content.
- **Focused tests:** Add exhaustive disposition, cited-question, unsupported-summary, unknown-ID, duplicate-omission, visible-and-omitted, critical generic-advice, and no-silent-drop cases; remove additions-mode cases. Test stable flag IDs, one valid review resolution per flag, exact corrected/removed operation linkage, post-settlement strict checks, and newly introduced numeric mismatches.
- **Acceptance criteria:** Every verified fact is accounted for exactly as designed; every patient-facing question is cited or absent; no validator silently repairs or drops content; every numeric flag has a stable ID and must be resolved before publication.

### Task 5 — Rewrite model-stage contracts around ground, assemble, and review

- **Files:** `skills/simplify/reference/style_rules.md`, `skills/simplify/stages/ground.md`, `skills/simplify/stages/assemble.md`, `skills/simplify/stages/review_fidelity.md`, `skills/simplify/stages/review.md`, `skills/simplify/stages/review_coverage.md`, `skills/simplify/stages/correct.md`, `skills/simplify/stages/assemble_missing.md`, `skills/simplify/stages/glossary.md`, `tests/test_stage_docs.py`
- **Depends on:** Task 2.
- **Parallelization / write set:** Prompt/stage-document write set; may run in parallel with Tasks 3 and 4 after Task 2. No other task edits these stage files or `style_rules.md`.
- **Changes:** Make the critical-versus-supporting patient-relevance policy canonical in `style_rules.md` while preserving the `4e53e8e` PII, numeracy, plain-language, action-first, no-filler, and no-generic-advice rules. Strengthen `ground.md` for complete-clause extraction. Update `assemble.md` to read `02_facts.json`, produce concise patient content, cited questions, and complete structured omissions, and keep generic education out unless patient-specific. Rename `review_fidelity.md` to `review.md` and rewrite it as the independent exhaustive fact/omission/numeric review that emits only bounded operations and `reassemble_fact_ids`. Delete `review_coverage.md`, `correct.md`, and `assemble_missing.md` only after their required rules are incorporated. Retain `glossary.md` as optional post-finalization enrichment over visible finalized content, capped at five terms and using `07_glossary*.json` names.
- **Focused tests:** Update `tests/test_stage_docs.py` to require the relevance policy in `assemble.md`, `review.md`, and `style_rules.md`; require complete-clause grounding, complete dispositions, combined-review fields, bounded operations, reassembly followed by new review, direct-summary prohibition, and optional post-finalization glossary behavior. Assert no deleted stage is referenced.
- **Acceptance criteria:** The only core model responsibilities are ground, assemble, and one independent review; the `4e53e8e` critical-first policy remains explicit; deleted stages are absent; no model stage performs deterministic settlement or finalization.

### Task 6 — Replace review sanitization and diff guarding with exact settlement

- **Files:** `skills/simplify/scripts/sanitize_review.py`, `skills/simplify/scripts/settle_review.py`, `skills/simplify/scripts/diff_guard.py`, `tests/test_sanitize_review.py`, `tests/test_settle_review.py`, `tests/test_diff_guard.py`
- **Depends on:** Tasks 4 and 5.
- **Parallelization / write set:** Review-settlement write set; cannot start until validator APIs and the combined review contract are stable. After completion, Task 7 may start; Task 8 may proceed independently from Task 2 until it needs final artifact behavior.
- **Changes:** Rename `sanitize_review.py` to `settle_review.py`. Validate exhaustive `reviewed_fact_ids`, one `fact_reviews` result per fact, all omissions, all numeric resolutions, and valid path syntax. Accept only bounded `replace`, `clear`, and `remove` operations; protect system fields; apply the exact requested value exactly once; reject unknown paths/operations, extra edits, partial application, array reordering, unnamed changes, and new uncited clinical claims. Derive aggregate counts/verdict in Python and record dropped invalid operations as defined by schema. Refuse settlement when `reassemble_fact_ids` is non-empty. Rerun citation/disposition and numeric assertions in memory, then write `04_review.json` and `05_plan.settled.json` only on success. Delete `diff_guard.py` after all relevant protections move into settlement.
- **Focused tests:** Rename `tests/test_sanitize_review.py` to `tests/test_settle_review.py`, retain useful path tests, and add exact replacement value, apply-once, complete application, protected path, array order, unknown operation, unnamed change, uncited claim, unresolved flag, incomplete fact review, and non-empty reassembly failures. Delete `tests/test_diff_guard.py` only after its PII-substitution, array-removal, and unnamed-change protections are represented.
- **Acceptance criteria:** Settlement cannot introduce prose; only named exact operations change the plan; all facts/omissions/flags are exhaustively reviewed; failed or reassembly-requesting reviews produce neither settled plan nor publishable output; old sanitizer/diff-guard files are absent.

### Task 7 — Make finalization assertion-only and fail closed

- **Files:** `skills/simplify/scripts/finalize.py`, `tests/test_finalize.py`
- **Depends on:** Tasks 3, 4, and 6.
- **Parallelization / write set:** Finalization write set; no other task edits `finalize.py` or `tests/test_finalize.py`. Blocks Tasks 8–10.
- **Changes:** Load only `05_plan.settled.json`; remove draft fallback, additions merge, silent citation dropping, clinical repair, and fail-open notices. Require current-run artifacts and exact `ok` statuses for `unitize`, `ground`, `assemble`, `plan_check`, `numeric_parity`, `review`, and `settle_review`; reject `failed`, `degraded`, `skipped`, missing, stale, or wrong-version core state. Rerun plan schema, citation/disposition, numeric, run-ID, schema-version, and plugin-version assertions. Preserve only bounded PII substitution and readability telemetry, then validate before writing `06_plan.final.json` and `report.md`. Detect schema-v1 intermediate artifacts and return a clear non-clinical migration error without rewriting the run.
- **Focused tests:** Require all core statuses and artifacts. Add no-draft-fallback, no-additions-merge, no-silent-drop, missing-review, failed/degraded/skipped stage, stale run ID, stale schema/plugin version, missing artifact, unresolved numeric flag, v1-partial migration, and no-output-on-failure cases. Verify the successful path writes both current-run final artifacts.
- **Acceptance criteria:** No clinical output exists before every core gate passes; finalization reads only the settled plan; all final artifacts identify the current run/schema/plugin; any required-stage failure returns only a workflow error.

### Task 8 — Preserve safe rendering compatibility and optional post-finalization outputs

- **Files:** `skills/simplify/scripts/plan_view.py`, `skills/simplify/scripts/render_md.py`, `skills/simplify/scripts/render_html.py`, `skills/simplify/scripts/render_audit.py`, `skills/simplify/scripts/glossary_check.py`, `skills/simplify/templates/report.html`, `tests/test_plan_view.py`, `tests/test_render_md.py`, `tests/test_render_html.py`, `tests/test_render_audit.py`, `tests/test_glossary_check.py`
- **Depends on:** Tasks 2 and 7.
- **Parallelization / write set:** Rendering/enrichment write set; may run in parallel with Task 9 only after final artifact behavior is stable. Do not edit finalization, stage prompts, schemas, or workflow metadata.
- **Changes:** Render schema-v2 cited questions while never exposing `omitted_facts`, raw model output, technical checks, notices, or readability telemetry in patient views. Keep `report.md` concise and default. Preserve render-only support for completed schema-v1 final reports, including legacy string questions/`low_priority`, without modifying old folders. Make HTML optional and able to consume optional glossary data without mutating `06_plan.final.json`. Update audit rendering to resolve v2 omissions through facts and combined review, showing source location, quote, extraction method, omission reason, and reviewer result, while retaining completed-v1 `04_coverage.json` support. Validate optional glossary terms only against visible finalized content and write `07_glossary.json`; glossary-aware output is separate from immutable core artifacts.
- **Focused tests:** Test v2 cited questions, hidden omissions, concise output, no telemetry/notices/generic education leakage, optional glossary behavior, and schema-v1 compatibility in plan/Markdown/HTML views. Test v2 audit traceability and v1 coverage compatibility. Test finalized-visible-content glossary matching and post-finalization artifact names.
- **Acceptance criteria:** Default patient output is only `report.md`; optional glossary/HTML/audit outputs cannot alter the final plan; completed v1 reports still render; partial v1 runs do not enter this render-only compatibility path.

### Task 9 — Enforce mandatory complete-workflow invocation at every entry point

- **Files:** `skills/simplify/SKILL.md`, `skills/simplify/agents/openai.yaml`, `plugin.json`, `.codex-plugin/plugin.json`, `tests/test_skill_consistency.py`
- **Depends on:** Tasks 5, 6, and 7.
- **Parallelization / write set:** Invocation/metadata write set; disjoint from Task 8 and may run in parallel once all referenced stage/artifact names are final. Blocks package-level Task 10.
- **Changes:** Put the non-negotiable execution contract near the top of `SKILL.md`: explicit selection runs the complete workflow; no direct clinical response; no clinical content before validated `06_plan.final.json` and `report.md`; all grounding chunks, deterministic checks, independent review, settlement, and final validation are mandatory; one retry per model stage; terminal failures return only a workflow error; present only `report.md`; optional outputs occur after finalization. Replace the old seven-stage instructions with the `ground[1..K] -> assemble -> review` core graph, bounded reassembly-once path, fail-closed status/artifact gates, and approximately 13-artifact clean contract. Set `allow_implicit_invocation: false`. Use the exact synchronized complete-workflow prompt from the design in all three metadata entry points.
- **Focused tests:** Update `tests/test_skill_consistency.py` to require identical default prompts, disabled implicit invocation, prominent execution/failure/presentation contracts, current stage/script/schema existence, absence of deleted references, and plugin-manifest parity.
- **Acceptance criteria:** Explicit invocation cannot be satisfied by an ad hoc summary; all entry points demand the complete workflow; implicit invocation is disabled; the skill tells the host to return only the validated finalized report and requested artifacts.

### Task 10 — Rebuild shared fixtures and end-to-end/package assertions for the v2 graph

- **Files:** `tests/_runfix.py`, `tests/_paths.py`, `tests/fixtures/README.md`, affected files under `tests/fixtures/`, `tests/test_pipeline_e2e.py`, `tests/test_build.py`, `tests/test_fixtures.py`, `tests/test_status_lines.py`
- **Depends on:** Tasks 2–9.
- **Parallelization / write set:** Integration-fixture/package-test write set. May run in parallel with Task 11 because their write sets are disjoint. Do not edit implementation files to make fixtures pass; route implementation defects back to the owning task.
- **Changes:** Update shared run builders, paths, fixtures, and status expectations to schema v2 and the new artifact names. Model the clean pipeline as `K` grounding calls plus one assembly and one review, with deterministic checks between stages. Cover one allowed retry per model stage and the bounded critical-omission path: reassemble only relevant facts, rerun deterministic checks, require a fresh review, and fail if a second review still requests reassembly. Replace the artifact matrix with the approximately 13-file one-chunk core set; exclude copied sources and optional outputs. Update package tests so new stage/script/schema files are included and obsolete coverage/correction/additions/sanitizer/diff-guard/manifest files are absent.
- **Focused tests:** In `tests/test_pipeline_e2e.py`, assert complete chunk validation, exhaustive fact dispositions, exhaustive review and numeric resolutions, exact settlement, all required stage statuses/artifacts, current identities/versions, no publication on every failure class, three conceptual model calls for one chunk, `K + 2` for `K` chunks, and approximately 13 clean core artifacts. Verify new prose from reassembly receives a second independent review. Run fixture, status-line, and package-content tests alongside the e2e test.
- **Acceptance criteria:** The deterministic integration suite represents only the schema-v2 workflow; clean and repair paths match the design; package contents have exact new/obsolete parity; no fixture preserves a direct-summary or fail-open route.

### Task 11 — Update user and architecture documentation

- **Files:** `README.md`, `docs/overview.md`, `docs/architecture.md`, `docs/openai-plugin.md`
- **Depends on:** Task 9.
- **Parallelization / write set:** Documentation-only write set; may run in parallel with Task 10. Edit `docs/openai-plugin.md` only if a short generally reusable fail-closed skill convention is warranted by the implementation.
- **Changes:** Document explicit invocation, complete-workflow enforcement, concise critical-first output, audited omissions, the three model responsibilities, deterministic safety boundaries, bounded reassembly, exact settlement, fail-closed finalization, `report.md` as the only default output, optional glossary/HTML/audit outputs, schema-v1 completed-report rendering, schema-v1 partial-run rejection, and the approximately 13-artifact clean target. Replace obsolete graphs, stage descriptions, artifact tables, review split, repair stages, and core glossary behavior. Preserve the model-versus-Python boundary already documented in `docs/openai-plugin.md`.
- **Focused tests:** Run documentation consistency checks from `tests/test_skill_consistency.py`, `tests/test_stage_docs.py`, and `tests/test_build.py`; search docs for deleted stage/script/schema names and old normal-call/artifact counts.
- **Acceptance criteria:** Documentation matches implemented names and behavior, never promises fail-open output, preserves the critical-versus-supporting policy, and distinguishes measured benchmark outcomes from hypotheses.

### Task 12 — Run deterministic verification and inspect the development package

- **Files:** `build.py`, `build-versions.json`, `dist/`, and the files exercised by `tests/test_*.py`; no source file is intentionally changed in this verification task.
- **Depends on:** Tasks 1–11.
- **Parallelization / write set:** Verification gate; run after all implementation and documentation tasks. Any failure returns to the task that owns the affected write set.
- **Changes:** Run the most focused tests listed in each task first, then the complete deterministic unit/integration suite. Build a development plugin archive with the existing build process. Inspect archive contents for required new files and absence of obsolete stages, scripts, schemas, and top-level research files. Do not bump the release version at this gate.
- **Focused tests:** Run the repository’s complete test command and package build command. At minimum, include all `tests/test_*.py` tests and the archive-content assertions in `tests/test_build.py`.
- **Acceptance criteria:** The full deterministic suite passes; the package builds; archive contents match the v2 manifests; the repository has no unintended generated artifacts or unrelated changes.

### Task 13 — Validate installed-host behavior, benchmark quality, and release only after gates pass

- **Files:** Host run directories chosen for the validation session, benchmark records in the project’s existing approved output location, `build.py`, `build-versions.json`, `plugin.json`, `.codex-plugin/plugin.json`, `skills/simplify/scripts/_version.py`, and the resulting `dist/simplify-med-<version>-openai.zip`; version-bearing files change only when all measured gates pass. Do not add a migration utility or new production feature.
- **Depends on:** Task 12.
- **Parallelization / write set:** Human/host validation and release gate. Host scenarios may be divided by corpus, but each worker must use separate run directories; benchmark aggregation and release-version edits remain single-owner.
- **Changes:** Install the development package in a clean Codex/OpenAI host. Run explicit short-document, long multi-chunk, explicit “quick summary,” prompt-injection source text, missing attachment, unavailable Python, failed grounding, failed review, unresolved reassembly, and education-heavy discharge scenarios. Verify failures return only workflow errors and successes return finalized `report.md`. Benchmark baseline `4e53e8e` versus schema v2 with the same corpus/model settings, recording model calls/waves/tokens, retries, p50/p95 latency, artifact count, critical recall, unsupported claims, numeric/negation/uncertainty/status/urgency errors, generic education, duplicates, report lengths, and direct-response bypass rate. Manually inspect at least one education-heavy packet and its audit. Use the existing release build to update package versions only after all required gates pass.
- **Focused tests:** Confirm exactly three calls for a clean one-chunk run and `K + 2` for clean `K`-chunk runs; approximately 13 core one-chunk artifacts; 100% critical-fact visibility; 100% visible-or-dispositioned facts; zero unsupported claims, unresolved numeric flags, lost negation/uncertainty, urgency escalation, non-patient-specific generic education, required-stage publications, or explicit-invocation bypasses; and no completed-v1 rendering regression.
- **Acceptance criteria:** Installed-host scenarios prove mandatory fail-closed invocation; benchmark records all design metrics; manual review confirms concise critical patient content plus complete audited omissions; release versions change only after every acceptance gate passes.

## Dependency and Parallelization Summary

- Task 1 is independent and may run beside Tasks 2–5.
- Task 2 is the schema/version foundation.
- Tasks 3, 4, and 5 have disjoint write sets and may run in parallel after Task 2.
- Task 6 requires Tasks 4–5; Task 7 requires Tasks 3, 4, and 6.
- Task 8 requires finalization; Task 9 requires all final stage/artifact behavior and may overlap Task 8 only after those interfaces are fixed.
- Tasks 10 and 11 have disjoint integration-test and documentation write sets and may run in parallel after Task 9.
- Tasks 12 and 13 are sequential verification, installed-host, benchmark, and release gates.

## Summary of What Requires You (Not a Dev Agent)

- Provide access to a clean Codex/OpenAI host for installed-skill invocation tests.
- Provide or approve the representative benchmark corpus and equivalent baseline/v2 model settings.
- Review the education-heavy patient report and audit for clinical relevance and omission quality.
- Approve release version updates only after deterministic, host-level, and benchmark gates pass.
