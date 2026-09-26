# Tasks: lean `simplify`

Spec: `PRD.md` (this folder). Evidence: `research.md`. Tests run with
`python3 -m unittest discover -s tests -q` (no pytest in the environment).

Contracts written up front so work can run in parallel (done, T0):
`schema/draft.schema.json`, `schema/draft_checked.schema.json`,
`schema/plan.schema.json`, `schema/protected.schema.json`,
`schema/verify_raw.schema.json`, `scripts/plan_paths.py`,
`tests/fixtures/documents/synthetic-er-visit.txt`.

Each workstream owns its files exclusively. Nobody edits a file owned by
another workstream; request contract changes through the orchestrator.

## T0 — Contracts and plan (orchestrator) — done

- [x] Research synthesis, PRD, tasks.
- [x] Model and shared schemas, `plan_paths.py`, synthetic ER fixture.

## T1 — Source preparation (agent: unitize)

Owns: `scripts/unitize.py`, `scripts/protected.py` (new), `schema/units.schema.json`,
`tests/test_unitize.py`, `tests/test_protected.py` (new), `tests/test_fixtures.py`,
`tests/fixtures/README.md`.

- [ ] Boilerplate suppression (URL-only lines, page counters, exact repeats ≥ 8
      chars) → `skip` reason on the unit; skipped units excluded from
      `01_source.txt`.
- [ ] `01_source.txt` with `=== <file> page <n> ===` headers.
- [ ] Remove chunking (`chunks`, `01_units.<k>.txt`, `--chunk-size`).
- [ ] `protected.py` scan + `01_protected.json` (schema `protected`).
- [ ] New stdout line `unitize: ok | files= units= skipped= protected=`.
- [ ] `SCHEMA_VERSION`-tagged outputs ("3.0"; `_version.py` owned by T2).
- [ ] Tests incl. the synthetic ER fixture: portal headers/URLs/page counters
      skipped; follow-up, return precaution, disposition, discharge diagnosis,
      "(H)" lab lines appear as protected candidates.

## T2 — Check, settle, finalize, run log (agent: pipeline)

Owns: `scripts/check_draft.py` (new), `scripts/numbers.py` (new, tokenizer moved
from `numeric_parity.py`), `scripts/settle.py` (new), `scripts/finalize.py`,
`scripts/runlog.py`, `scripts/_version.py`, `schema/check.schema.json` (new),
`schema/verify.schema.json` (new), `schema/run.schema.json`; deletes
`scripts/anchor_check.py`, `merge_facts.py`, `cite_check.py`,
`numeric_parity.py`, `settle_review.py` and schemas `facts_raw`, `facts`,
`care_plan_agent`, `care_plan`, `flags`, `review_raw`, `review` and their tests
(`test_anchor_check.py`, `test_merge_facts.py`, `test_cite_check.py`,
`test_numeric_parity.py`, `test_settle_review.py`). Owns tests
`test_check_draft.py`, `test_settle.py`, `test_numbers.py`, `test_finalize.py`,
`test_runlog.py`, `test_schemas.py`, `test_validate.py`, `test_status_lines.py`,
`test_pipeline_e2e.py`, `tests/_runfix.py`, `test_textnorm.py`.

- [ ] `numbers.py` tokenizer (behavior-preserving move) + tests.
- [ ] `check_draft.py` per PRD §4.4 (+ `--round 2`, attempt archiving).
- [ ] `settle.py` per PRD §4.6 (exit 0 / 1 / 3; `04_repair.json`).
- [ ] `finalize.py` per PRD §4.7 (uses `render_md.render`, `readability`).
- [ ] `runlog.py` core stages `unitize, write, check, verify, settle, finalize`;
      `repair_requested` status for `settle`; `run.schema.json` updated.
- [ ] `_version.py` `SCHEMA_VERSION = "3.0"`.
- [ ] E2E test on the synthetic ER fixture: unitize → hand-written draft →
      check → hand-written verify → settle → finalize; asserts report ≤ 300
      words, contains the target sections, and excludes noise (contrast agent,
      lab inventory, vitals, "no current outpatient medications", "ordering
      provider"). Plus repair-round and failure-path tests.

## T3 — Renderers (agent: render)

Owns: `scripts/plan_view.py`, `scripts/render_md.py`, `scripts/render_html.py`,
`templates/report.html`, `scripts/render_audit.py`, `scripts/glossary_check.py`,
`scripts/readability.py`, `schema/glossary*.schema.json`, tests
`test_plan_view.py`, `test_render_md.py`, `test_render_html.py`,
`test_render_audit.py`, `test_glossary_check.py`, `test_readability.py`, and a
new plan fixture `tests/fixtures/plans/er_visit.final.json`.

- [ ] `plan_view.build_view` for the §3 sections and headings by `visit_type`;
      `visible_text` built on `plan_paths.visible_strings`.
- [ ] `render_md` output matches PRD §3 for the ER fixture plan (golden test).
- [ ] `render_html` + template for the new sections.
- [ ] `render_audit`: each visible item then its cited unit lines
      (file/page/line/text) from `01_units.json`; stage table from `run.json`.
- [ ] `glossary_check` on new visible text.
- [ ] Fix: no stray type labels, no duplicated `(plain_name)`, no empty dashes,
      no "Already done".

## T4 — Prompts, skill, and docs (agent: prompts)

Owns: `SKILL.md`, `stages/write.md` (new), `stages/verify.md` (new),
`stages/glossary.md`, deletes `stages/ground.md`, `assemble.md`, `review.md`,
`reference/style_rules.md`, deletes `reference/categories.md`,
`agents/openai.yaml`, `README.md`, `docs/overview.md`, `docs/architecture.md`,
`docs/openai-plugin.md`, `docs/openai.md`, tests `test_skill_consistency.py`,
`test_stage_docs.py`.

- [ ] `SKILL.md`: short execution contract for the PRD §4 graph, retries,
      repair round, fail-closed rules, presentation rules. Never tells the host
      to read `01_units.json`.
- [ ] `stages/write.md`: selection rules (§4.2), slot rules (§3), coverage,
      unit-id citation, repair mode, retry mode. Includes the ER target as the
      worked example of shape (not content to copy).
- [ ] `stages/verify.md`: claims, operations, numeric flags, protected units,
      budget trimming (§4.5).
- [ ] `reference/style_rules.md` rewrite (PII, NUMERACY, LANGUAGE, SHOW/SKIP).
- [ ] Docs updated to the new pipeline.
- [ ] Consistency tests: every script/stage/schema/reference named in SKILL.md
      and stages exists; obsolete names are absent.

## T5 — Integration (orchestrator)

- [ ] Full test suite green; `python3 build.py` produces a ZIP containing only
      the new files (`test_build.py`).
- [ ] Walk the synthetic ER case end to end; compare `report.md` to PRD §3.
- [ ] Adversarial review of the diff; commit and push.

## Follow-ups (not in this change)

- Update or retire the parked `mcp/openai/` widget for the new plan shape.
- Long-packet map pre-pass if a packet exceeds one call's context.
- Offline PDSQI-9 judge on the Drive seed cases.
