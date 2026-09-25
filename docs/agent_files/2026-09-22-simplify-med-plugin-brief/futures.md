# Futures

Ideas deliberately cut from the first version. Each was discussed and set aside, not forgotten. Nothing here is scheduled.

## Simplification levels

Two or three presets (`simple`, `standard`, `detailed`) mapping to target reading grades, defined in one reference file: target grade, maximum sentence length, whether the medical term is kept alongside the plain word, how much "what it means for you" explanation is written. Only the assemble and correct stages would read the preset; ground and review never see it. `meta.level` and `run.json.level` already exist so this needs no schema change. The after-score would be checked against the preset's target and a miss reported, not gated.

## Report based on level

Rendering the same final JSON at different levels of detail (for example, hiding expanders by default at the simplest level) without re-running the pipeline.

## Platform packaging customization

After the baseline platform-directory build system is implemented, consider generating
shared manifest fields from `plugin.meta.json` and adding declarative per-platform
overrides for frontmatter and file renames. The initial OpenAI work should first use the
explicit `packaging/<platform>/` layout and platform build scripts described in
`openai.md`; this future item is further consolidation, not a blocker for that design.

## Follow-up conversation guidance

After a report exists, a scoped follow-up mode where the model answers questions only from the fact ledger and the final plan, refuses anything the documents do not say, and points to the specific section of the report. Scoping conversation to specific links or sections only.

## History and memory

Hosts have memory. A future version could write a short structured record of each run (date, document type, run folder) to host memory so a later session can find previous reports, and could read prior runs to answer "what changed since last time" with evidence instead of inference.

## Caregiver view

A second rendering that highlights what the patient may need help with: to-do items, appointments, medication changes.

## Visual aids

Diagrams or icons per section, timelines for follow-ups, medication schedules as a grid.

## Colour coding of results

Green, amber, red for stated normal, borderline, abnormal values, only when the source itself labels them. Requires a decision on whether it counts as interpretation.

## Host-specific rendering

Claude Code and claude.ai artifacts, or any host's native interactive surface, generated from the same final JSON. The HTML file remains the portable baseline.

## Health literacy calculator

A separate tool that scores an arbitrary document with the same reading-level method, independent of a simplification run.

## External resources

Links to vetted sources (for example MedlinePlus) attached to diagnoses or medications. Deliberately excluded because it adds information the document does not contain; would need its own fidelity rule.

## Translation

Rendering the final JSON in another language, as a render-stage concern over already-verified facts.

## Reviewed additions

Route the assemble-missing agent's additions through a bounded fidelity review before merging, once real runs show whether the deterministic checks are enough.

## Evaluation harness

Fixture documents with hand-annotated ledgers and expected plans; injected-error catch-rate protocol for the reviewer; recall measurement per chunk size.

## Agent reply discipline

In both kill tests, some stage agents replied with more than the single line their agent file asks for (kill test 1 and kill test 2 both saw this recur in `ground` and `assemble`: a validation-summary sentence before the required status line). This is harmless -- the host only consumes the files the agent writes, never parses the reply for content -- but a host parsing agent replies programmatically would still need to defend against it. A host-level fix would be to have the orchestrator ignore agent replies entirely and read status only from the deterministic check scripts' stdout, which is already effectively what SKILL.md's driving procedure does.

## Cross-document duplicate merging backstop

Kill test 2's two-file bundle (a discharge summary and a standalone lab report covering some of the same analytes) showed cross-file duplicate lab facts merged correctly by the assemble agent's MERGE rule alone -- `merge_facts.py`'s dedupe key is `(unit_id, normalized quote, category)`, so two facts from different source files can never collide there even when they describe the identical value. This worked in kill test 2, but rests entirely on one LLM call's judgment with no deterministic check backing it up the way `cite_check` backs up citation presence. A deterministic backstop -- flag items whose source facts come from different files but have identical normalized text -- would make this checkable rather than trusted.

## Cross-report and longitudinal understanding

Compare multiple reports or visits over time while preserving source provenance. Useful
views include a dated visit timeline, medication additions/removals/dose changes, test
progression, pending follow-ups, unresolved contradictions, and "what changed since the
last report." This requires explicit rules for record identity, dates, duplicate facts,
conflicts, retention, and whether prior reports may be remembered across conversations.
No longitudinal conclusion should be produced without linking it to the contributing
documents and dates.

## Multi-page report navigation

For long documents, provide section navigation, source-page jumps, progress through the
report, print-friendly layout, and stable deep links to report sections. This would
extend the initial ChatGPT fullscreen report with source-page-aware navigation; the
self-contained HTML report remains the portable full-window fallback.

## Medical-term explorer

Let a user select a medical term to see its plain-language meaning, why it matters in
this document, confidence, and source location. This should remain separate from the
first report layout so the initial experience stays focused. Any general explanation
that goes beyond the uploaded document must be visibly distinguished from document facts.

## Original-excerpt explorer

Add an optional synchronized view of the exact source excerpt beside the simplified
explanation, with page or section anchors and visible distinctions among extracted fact,
restatement, and inference. This is valuable for trust and review but adds substantial
layout, OCR-location, and accessibility complexity, so it is deferred from the first
OpenAI report.

## Alternate interactive layouts

The initial OpenAI package publishes one report layout only. Possible later layouts
include a caregiver-focused view, compact mobile summary, clinician-review view, and
cross-report timeline. All should render from the same verified final data rather than
re-running the medical simplification pipeline.
