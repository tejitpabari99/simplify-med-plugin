# Futures

Ideas deliberately cut from the first version. Each was discussed and set aside, not forgotten. Nothing here is scheduled.

## Simplification levels

Two or three presets (`simple`, `standard`, `detailed`) mapping to target reading grades, defined in one reference file: target grade, maximum sentence length, whether the medical term is kept alongside the plain word, how much "what it means for you" explanation is written. Only the assemble and correct stages would read the preset; ground and review never see it. `meta.level` and `run.json.level` already exist so this needs no schema change. The after-score would be checked against the preset's target and a miss reported, not gated.

## Report based on level

Rendering the same final JSON at different levels of detail (for example, hiding expanders by default at the simplest level) without re-running the pipeline.

## Platform packaging customization

`build.py` currently zips per platform using an ignore file. Later: generate each platform's manifest (Claude Code `plugin.json`, other hosts' equivalents) from `plugin.meta.json`, and allow per-platform overrides (frontmatter fields, file renames) declared in a `packaging/<platform>.json`.

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
