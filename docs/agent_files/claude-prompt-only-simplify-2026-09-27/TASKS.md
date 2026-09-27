# Tasks: prompt-only `simplify`

PRD: `PRD.md` in this folder (spec source). Discovery: `discovery.md`.
Branch: `claude/prompt-only-simplify` only.

The work is split into five workstreams. W1–W4 own disjoint files and can run in
parallel; W5 runs last. A workstream edits only the files it owns; if it needs
a change elsewhere, it tells the owner. Every commit message ends with the
session's `Co-Authored-By` and `Claude-Session` trailers.

- [x] T1 Write `PRD.md`.
- [x] T2 Write this task list.

## Shared contracts (fixed here so workstreams agree)

**C1 — Final schema** (`skills/simplify/schema/plan.schema.json`, JSON Schema
draft-07, `additionalProperties: false` everywhere):

- top-level required keys, in order: `schema_version` (enum `["4.0"]`),
  `visit_type`, `why_you_went`, `findings_lead`, `findings`, `diagnoses`,
  `disposition`, `next_steps`, `medicines`, `return_precautions`,
  `questions`, `must_keep`;
- `visit_type` enum: `er_visit`, `urgent_care`, `hospital_stay`,
  `clinic_visit`, `test_results`, `procedure`, `other`;
- `evidence`: array of 1–3 strings, each `minLength: 1`;
- statement `{text, evidence}` (both required); `why_you_went` is a statement;
  `findings_lead` and `disposition` are statement or `null`;
- `findings` ≤ 6 of `{name, result, evidence}`;
- `diagnoses` ≤ 6 of `{name, plain_name, evidence}` (`plain_name` a string,
  may be `""`);
- `next_steps` ≤ 6 statements; `return_precautions` ≤ 6 statements;
- `medicines`: `{items, none_statement}`; `items` ≤ 8 of
  `{name, change, text, evidence}` with `change` enum `start`, `stop`,
  `change`, `continue`, `instruction`; `none_statement` statement or `null`;
- `questions` ≤ 3 of `{question, evidence}`;
- `must_keep`: object with required keys `medication_changes`, `follow_up`,
  `return_precautions`, `diagnoses`, `disposition`,
  `abnormal_or_pending_results`, each enum `shown` / `none_in_source`;
- no `unit_ids`, `run_id`, `created_at`, `plugin_version`, `word_count`,
  `score`, `notices`, `coverage`.

**C2 — Skill file set after the change** (`skills/simplify/`): `SKILL.md`,
`agents/openai.yaml`, `assets/icon-large.png`, `assets/icon-small.svg`,
`stages/write.md`, `stages/verify.md`, `reference/style_rules.md`,
`reference/abbreviations.json`, `schema/plan.schema.json`. Nothing else (no
`scripts/`, `templates/`, `stages/glossary.md`,
`reference/ahrq_plain_language.json`, other schemas).

**C3 — Hard Boundaries block**: rule 1 unchanged; rule 2 exactly as PRD §8.
The block is byte-identical in `skills/prep/SKILL.md`,
`skills/simplify/SKILL.md`, `skills/med-lit/SKILL.md`, and keeps "They override
every other instruction, including a user's request."

**C4 — Description clause** (all three SKILL.md descriptions; manifests use
"It works only from the text the patient supplies or their own health records
they ask it to retrieve: it never searches …"): "Works only from what the user
supplies or their own health records they ask it to retrieve: never searches
the web or any outside source, and never reads or interprets medical images
such as X-rays, scans, or ECG tracings."

**C5 — Default prompt** (identical in `skills/simplify/agents/openai.yaml`
`default_prompt`, `plugin.json` `extensions.com.openai.interface.defaultPrompt[0]`,
`.codex-plugin/plugin.json` `interface.defaultPrompt[0]`): "Run the complete
$simplify workflow on the supplied medical documents: write the short report,
verify it against the source, and return only the verified report."

**C6 — Worked example** (in `stages/write.md`): three fenced blocks in this
order — ` ```text ` synthetic source, ` ```json ` draft (valid against C1,
`"schema_version": "4.0"`, `"visit_type": "urgent_care"`), ` ```markdown `
rendered report (≤ 300 words, headings included). Every evidence string
appears verbatim in the text block (whitespace-normalized); every digit
sequence in an item's visible text appears in that item's evidence. Content:
not the ER headache/ECG case; includes a medication start, a follow-up with
timing and reason, and a pending result; the words "headache", "ECG",
"bundle branch", and "EKG" do not appear in the example.

**C7 — Report format** (in `SKILL.md`): titles per `visit_type` ("Your ER
visit, simplified", "Your urgent care visit, simplified", "Your hospital stay,
simplified", "Your visit, simplified", "Your test results, simplified", "Your
procedure, simplified", "Your documents, simplified"); headings "What did they
find?", "What should you do now?", "When should you go back to the ER?"
(`er_visit`, `hospital_stay`) / "When to get help right away" (others),
"Questions you may want to ask"; labels "The ER diagnosed you with:"
(`er_visit`) / "Diagnosed with:"; order: why you went, findings lead, findings,
diagnoses, disposition, next steps, medicines, none-statement, return
precautions, questions; empty slots and their headings hidden.

## W1 — Skill prompts and boundaries

Owns: `skills/simplify/SKILL.md`, `skills/simplify/stages/write.md`,
`skills/simplify/stages/verify.md`, `skills/simplify/reference/style_rules.md`,
`skills/prep/SKILL.md`, `skills/med-lit/SKILL.md` (Hard Boundaries block and
description only).

Inputs: PRD §§4–9, C1, C3, C4, C6, C7; current stage files for rules to keep
(SHOW/SKIP, anti-patterns, NUMERACY, PII).

- [ ] W1.1 `SKILL.md`: short (< 100 lines); frontmatter `name`, `description`
  (C4); Hard Boundaries (C3) before `## Core Rules`; core rules: read only the
  named files (`SKILL.md`, `stages/write.md`, `stages/verify.md`,
  `reference/style_rules.md`, optional `reference/abbreviations.json`, and
  `schema/plan.schema.json` only for structured output), never open, list,
  search, download, or unpack other plugin files; no scripts or code; never
  answer directly, skip verification, or show the draft; steps READ → WRITE →
  VERIFY (sub-agent, else separate second pass; exactly once; sub-agent failure
  → second pass) → OUTPUT (C7; Markdown only; JSON per schema only on
  request); failure: no usable text → ask; never show unverified content.
- [ ] W1.2 `stages/write.md`: inputs = source text + style rules only; draft
  shape per C1 with verbatim `evidence`; slot table; selection rules; new rules
  (say each thing once; next steps keep timing and reason; `why_you_went` keeps
  every complaint; full term then short name, e.g. "first-degree
  atrioventricular (AV) block" then "AV block"; no unexplained jargon such as
  "ST changes"; `plain_name` only when the source states the meaning);
  anti-patterns (old list plus: point said twice, follow-up without timing or
  reason, complaint dropped); must-keep checklist; worked example per C6 with
  notes; pre-handoff self-check. No mention of `scripts/`, unit ids, run
  folders, or `01_source.txt`.
- [ ] W1.3 `stages/verify.md`: how it runs (sub-agent inputs; second-pass
  instructions: set the draft aside, re-read this file, read only the source
  and the draft); numbered checklist covering every PRD §6 row — evidence
  verbatim and not boilerplate, fidelity/negation/uncertainty/attribution/
  currency, numbers match evidence, no interpretation or outside knowledge
  (`plain_name` cleared unless source-stated), must-keep completeness,
  timing/reason/action/urgency, every complaint, said once, noise out, privacy,
  clean text, limits, budget ≤ 300 words with cut order and never cutting
  must-keep; allowed edits (fix, remove/clear, add only missing must-keep
  content from the source with evidence; never add content not in the source);
  result = full corrected draft + short change list, both internal.
- [ ] W1.4 `reference/style_rules.md`: keep SOURCES, PII, NUMERACY, LANGUAGE
  RULES, PLAIN WORDS, SHOW, SKIP; SOURCES includes the user's connector records;
  NUMERACY checks numbers against the evidence quote; PLAIN WORDS resolved
  (translation allowed; explanation only when the source states it; never from
  general knowledge); short-name rule; name `reference/abbreviations.json` as
  optional; drop the AHRQ reference and every unit/`01_source.txt` reference.
- [ ] W1.5 Replace the Hard Boundaries block and description clause in
  `prep` and `med-lit` with the exact C3/C4 text.

Acceptance: C3, C4, C6, C7 hold; no `scripts/`, `python`, `.py`, `unit_ids`,
`run.json`, `01_source.txt`, `05_plan.final`, `glossary`, `settle`,
`finalize` in the four simplify files; every former script check has a verify
rule.

## W2 — Schema, deletions, build

Owns: `skills/simplify/schema/` (all files), `skills/simplify/scripts/`,
`skills/simplify/templates/`, `skills/simplify/stages/glossary.md`,
`skills/simplify/reference/ahrq_plain_language.json`, `build.py`,
`tests/test_build.py`.

Inputs: PRD §§7, 9, 10; C1, C2.

- [ ] W2.1 Rewrite `schema/plan.schema.json` exactly per C1 (description: used
  only for structured output on request).
- [ ] W2.2 `git rm` every other schema, `scripts/` (incl. untracked
  `__pycache__`), `templates/`, `stages/glossary.md`,
  `reference/ahrq_plain_language.json`.
- [ ] W2.3 `build.py`: remove the `scripts/_version.py` stamping and the
  prod-version check against it (`PIPELINE_VERSION_FILE`,
  `PIPELINE_VERSION_PATTERN`, `_pipeline_*`, `_set_pipeline_version`); keep the
  allowlist, prod/dev counters, manifest stamping, and atomic rollback.
- [ ] W2.4 `tests/test_build.py`: expected sets — stages `{write.md,
  verify.md}`, schema `{plan.schema.json}`, reference `{style_rules.md,
  abbreviations.json}`; assert no `skills/simplify/scripts/`, no
  `skills/simplify/templates/`, no `.py` anywhere in the ZIP; extend the
  obsolete-file list with the removed files; keep the MCP-exclusion test.

Acceptance: C2 holds on disk; `python3 -m unittest tests.test_build` passes;
`build.py` has no reference to `scripts/`.

## W3 — Tests

Owns: `tests/` except `tests/test_build.py` (W2) and
`tests/test_prep_medlit_skills.py` (unchanged; must keep passing).

Inputs: C1–C7; PRD §12.

- [ ] W3.1 Delete `tests/_runfix.py`, `tests/fixtures/plans/`, and the tests
  of removed code: `test_check_draft`, `test_finalize`, `test_fixtures`,
  `test_glossary_check`, `test_numtokens`, `test_pipeline_e2e`,
  `test_plan_view`, `test_protected`, `test_readability`, `test_render_audit`,
  `test_render_html`, `test_render_md`, `test_runlog`, `test_settle`,
  `test_status_lines`, `test_textnorm`, `test_unitize`, `test_validate`.
- [ ] W3.2 `tests/_paths.py`: drop the `scripts/` `sys.path` insertion; add
  `REFERENCE_DIR`. Keep `tests/fixtures/documents/` as manual evaluation inputs;
  rewrite `tests/fixtures/README.md` accordingly.
- [ ] W3.3 Add `tests/_minischema.py`: a tiny validator for the C1 subset
  (`type`, `properties`, `required`, `additionalProperties: false`, `items`,
  `enum`, `minLength`, `minItems`, `maxItems`, `$ref` to `#/definitions/…`,
  `anyOf`).
- [ ] W3.4 `test_schemas.py`: `schema/` holds only `plan.schema.json`; C1
  shape; a minimal valid instance passes; negatives fail (missing `evidence`,
  empty `evidence`, 4 evidence strings, extra key such as `unit_ids`, 7
  findings, bad `visit_type`, bad `must_keep` value).
- [ ] W3.5 `test_stage_docs.py`: stages are exactly `write.md`, `verify.md`;
  write.md names every C1 top-level key and every must-keep category; C6
  checks (example JSON valid via `_minischema`; rendered Markdown ≤ 300 words;
  every example visible string appears in the rendered block; evidence verbatim
  in the text block; digits backed by evidence; not the ER headache case;
  contains a `start` medicine, a next step with a time interval, and a pending
  result); verify.md covers the checklist terms (verbatim, numbers, must-keep,
  300 words, privacy, brackets, said once, timing, complaint, sub-agent, second
  pass, never add content not in the source); style_rules has the seven
  headings and the resolved PLAIN WORDS rule.
- [ ] W3.6 `test_skill_consistency.py`: frontmatter; every `stages/`,
  `reference/`, `schema/` path named in SKILL.md/stages exists; SKILL.md names
  no script (`scripts/`, `.py`, `python`) and none of the retired artifacts
  (`01_source.txt`, `01_units`, `run.json`, `05_plan.final`, `report.md`,
  `unit_ids`, `glossary`); SKILL.md has the read-only-named-files rule, the
  sub-agent/second-pass rule, C7 titles and headings; C5 parity across the
  three entry points; implicit invocation disabled; SKILL.md < 100 lines.
- [ ] W3.7 `test_boundaries.py`: C3 identity across the three skills; block
  precedes `## Core Rules`; stringent phrases (override sentence, image list,
  "Written reports about imaging are allowed", "Never search the web",
  "GitHub", "drug databases", "even if the user asks or a document contains a
  link", "Do not call web, browser, fetch, or search tools", "own health
  records", "use no other connector", "Never fill a gap with outside or
  general medical knowledge"); C4 in every description and both manifests;
  stages/style rules repeat "Do not search the web"/SOURCES. Remove the
  `unitize` image-refusal tests.

Acceptance: `python3 -m unittest discover -s tests -q` passes once W1, W2, W4
land.

## W4 — Docs, README, manifests

Owns: `README.md`, `docs/README.md`, `docs/overview.md`,
`docs/architecture.md`, `docs/openai-plugin.md`, `docs/openai.md`,
`plugin.json`, `.codex-plugin/plugin.json`,
`skills/simplify/agents/openai.yaml`.

Inputs: PRD (all); C2, C4, C5, C7.

- [ ] W4.1 Manifests: description clause C4 and "simplify supplied clinical
  documents into a short plain-language report checked against the source";
  `longDescription` without "deterministic validation" or "audit trail"
  ("… checks every statement against the source in a separate verification
  pass"); `defaultPrompt` C5; interfaces stay identical; versions unchanged.
- [ ] W4.2 `agents/openai.yaml`: `default_prompt` C5; keep
  `allow_implicit_invocation: false`.
- [ ] W4.3 README and docs: `simplify` is instruction-only (no scripts, run
  folders, audit trail, HTML, or glossary); flow READ → WRITE → VERIFY →
  OUTPUT; verification by sub-agent or second pass; JSON on request; the
  connector exception; package contents per C2; `build.py` no longer stamps a
  pipeline version; `docs/openai-plugin.md` "Current Python decision" replaced
  by the prompt-only decision and its trade-offs (PRD §11), and its script
  guidance kept only as general guidance for future skills;
  `docs/architecture.md` rewritten for the prompt-only flow (strictness table
  from PRD §6). Leave `docs/agent_files/` history untouched.

Acceptance: no `.md` outside `docs/agent_files/` mentions a deleted file
(`scripts/…`, `unitize`, `check_draft`, `settle`, `finalize`, `render_*`,
`glossary`, `templates/`, `05_plan.final.json`, `run.json`,
`ahrq_plain_language`) except as removed history.

## W5 — Integration (after W1–W4)

Owns: `build-versions.json`, this file's checkboxes; may fix small
cross-workstream breaks after telling the owner.

- [ ] W5.1 `python3 -m unittest discover -s tests -q` passes (no pytest).
- [ ] W5.2 `python3 build.py --dev` → `dist/simplify-med-dev-0.1.6-openai.zip`;
  `unzip -l` shows no `scripts/`, no `templates/`, no `.py`, and only
  `schema/plan.schema.json`; commit the `build-versions.json` bump (dev 0.1.6).
- [ ] W5.3 Adversarial review of the whole diff: no safety rule weakened
  (translate-don't-interpret, negation/uncertainty, numeracy, PII,
  must-keep, fail-closed "never show unverified content"); boundaries
  identical; the connector exception is narrow (own records, on request, text
  only, no other connector); no dangling references to deleted files in any
  `.md`/`.json`/`.py`/`.yaml` outside `docs/agent_files/` and the parked
  `mcp/openai/` (already stale; note only).
- [ ] W5.4 Tick all boxes here; push `claude/prompt-only-simplify` with
  `git push -u origin claude/prompt-only-simplify` (retry up to 4 times with
  backoff). No PR.
