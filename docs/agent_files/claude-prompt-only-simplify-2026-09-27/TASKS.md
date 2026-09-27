# Tasks: prompt-only `simplify`

PRD: `PRD.md` in this folder.

## Docs
- [x] T1 Write `PRD.md` (problem, goals, flow, strictness table, verification modes, schema contract, boundaries, removed/kept, risks, acceptance).
- [x] T2 Write this task list.

## Skill
- [ ] T3 Rewrite `skills/simplify/SKILL.md`: short; READ → WRITE → VERIFY → OUTPUT; read only named files; no scripts, run dirs, retries; output format; structured output on request.
- [ ] T4 Rewrite `stages/write.md`: internal draft with evidence quotes and must-keep checklist; quality rules (said once, timing and reason, every complaint, short names, plain meaning from source); new synthetic urgent-care worked example (medication change, timed follow-up, pending result).
- [ ] T5 Rewrite `stages/verify.md`: sub-agent or second pass; full checklist from PRD §6; bounded edits; returns corrected draft.
- [ ] T6 Rewrite `reference/style_rules.md`: resolve PLAIN WORDS vs SOURCES; connector records as source; evidence-based numeracy; short-name rule.
- [ ] T7 Slim `schema/plan.schema.json` (schema 4.0, evidence quotes, must_keep, urgent_care; no unit ids or run metadata).
- [ ] T8 Delete `scripts/`, `templates/`, every other schema, `stages/glossary.md`, `reference/ahrq_plain_language.json`.
- [ ] T9 Update Hard Boundaries (identical) and descriptions in `prep`, `simplify`, `med-lit`; update `agents/openai.yaml` default prompt.

## Repository
- [ ] T10 `build.py`: drop the `scripts/_version.py` dependency.
- [ ] T11 Manifests: long description and default prompt (no deterministic validation / audit trail).
- [ ] T12 README.md, docs/overview.md, docs/architecture.md, docs/openai-plugin.md, docs/openai.md, docs/README.md.

## Tests
- [ ] T13 Delete tests for removed scripts/schemas, `_runfix.py`, obsolete fixture plan; slim `_paths.py`; keep synthetic documents with an updated README.
- [ ] T14 Add `tests/_minischema.py` (tiny validator).
- [ ] T15 Rewrite `test_boundaries`, `test_skill_consistency`, `test_stage_docs`, `test_schemas`, `test_build` for the new contract (example valid, ≤ 300 words, not the ER headache case, SKILL.md names no script).

## Validate and ship
- [ ] T16 `python3 -m unittest discover -s tests -q` passes.
- [ ] T17 `python3 build.py --dev` → 0.1.6; ZIP has no `scripts/` and only `plan.schema.json`; commit `build-versions.json`.
- [ ] T18 Adversarial diff review (safety rules, identical boundaries, no dangling references).
- [ ] T19 Commit in logical commits; push `claude/prompt-only-simplify`.
