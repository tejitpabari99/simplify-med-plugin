# Tasks: OpenAI package as a plain skills-only plugin

Design: [`DESIGN.md`](./DESIGN.md) (read first — D1-D8 are authoritative; tasks below
only summarize). Tests: `python3 -m unittest discover -s tests`. Rule: **one commit per
task**, committed once its done-when checks pass.

## T1 — build.py / packaging/build.py: `--no-mcp` staging + flag validation

Goal: true skills-only staged tree; reject `--app-id`+`--no-mcp` (D1, D2).
Files: `build.py` (root), `packaging/build.py`.
- Rename `build()`'s `include_mcp` param to `no_mcp: bool = False`; after `--app-id`
  validation, `SystemExit` if `app_id is not None and no_mcp`, else `app_id` still forces
  `no_mcp = True`; derive `include_mcp = not no_mcp`.
- Update both CLI callers (root `build.py`, `packaging/build.py main()`) to pass
  `no_mcp=args.no_mcp`.
- `_stage_openai()`: gate `custom_start.md`/`custom_end.md` staging and the root
  `plugin.json` copy behind `if include_mcp:`; keep skill copy, `agents/`/assets/
  `.codex-plugin/` overlays unconditional.
- In the `if not include_mcp:` block: trim `compat_manifest["interface"]["capabilities"]`
  to `["Read", "Write"]`; copy `packaging/openai/skills/simplify-med/SKILL.md` (T2) over
  staged `skill_destination/SKILL.md`.
- Add `"render_simplify_med_report"` to `_NO_MCP_FORBIDDEN_STRINGS`.
- Leave `_stage_platform()`'s guard and claude-code/claude-ai paths untouched.

Done-when: `--app-id`+`--no-mcp` exits non-zero naming both flags in stderr; `--no-mcp`
alone (once T2 exists) stages no root `plugin.json`, no `custom_start.md`/`custom_end.md`,
capabilities `== ["Read", "Write"]`; default (no-flag) build output unchanged.
Depends-on: none. Parallelizable-with: T2 (disjoint files).

## T2 — OpenAI-specific orchestrator `SKILL.md`

Goal: single self-contained orchestrator, no hook/dispatch indirection (D3).
Files (new): `packaging/openai/skills/simplify-med/SKILL.md`.
- Write per DESIGN.md's outline: frontmatter (`name`+`description` only), Prerequisites,
  Inputs, Running a script, Performing an LLM stage, Stages 0-5 (same order/scripts/
  stage-files/output-filenames as canonical `skills/simplify-med/SKILL.md`), Present
  results, Failure table, Run folder.
- "Present results" inlines `packaging/openai/custom_end.md` points 1, 2, 5 (native
  summary, attach/link outputs, audit-on-request); drops points 3-4 (render-tool call and
  file-handling restrictions).
- No `custom_start.md`/`custom_end.md`, no `agents/*.md` dispatch, no render-tool wording.
- Target: as short as complete, aiming ≤ ~180 lines.

Done-when: only `name`+`description` frontmatter; `grep -E
"agents/|custom_start|custom_end|render_simplify_med_report"` on the file is empty;
scripts/stages appear in canonical order (fully checked by T5).
Depends-on: none. Parallelizable-with: T1.

## T3 — Verify skill-level `agents/openai.yaml` needs no source change

Goal: confirm D5's `--no-mcp` shape (interface+policy only) is already produced by the
existing `_strip_yaml_top_level_key` removal.
Files: `packaging/openai/agents/openai.yaml` (edit only if drift found).
- Build `--no-mcp` (T1) and inspect the staged file.
- Confirm: `interface.{display_name, short_description, icon_small, icon_large,
  default_prompt}` + `policy.allow_implicit_invocation: true`, no `dependencies:` key.
- Fix minimally only if drift is found; otherwise no edit.

Done-when: staged `--no-mcp` `agents/openai.yaml` matches D5 exactly.
Depends-on: T1. Parallelizable-with: T2.

## T4 — Update `tests/test_build.py`

Files: `tests/test_build.py`.
- Rewrite `test_no_mcp_build_omits_all_mcp_connection_info`: also assert no root
  `plugin.json`; capabilities `== ["Read", "Write"]`; no `custom_start.md`/
  `custom_end.md`; staged `SKILL.md` differs from canonical and has none of `agents/`,
  `custom_start.md`, `custom_end.md`, `render_simplify_med_report`.
- Remove `test_app_id_with_no_mcp_is_redundant_but_allowed`; add
  `test_app_id_rejects_no_mcp_combination` (non-zero exit, stderr names both flags).
- Add a `--no-mcp` variant of `test_icons_exist_at_referenced_paths_and_interfaces_match`
  resolving icons via `.codex-plugin/plugin.json` + `agents/openai.yaml` only.
- Leave all MCP-only tests unchanged.

Done-when: `python3 -m unittest discover -s tests` passes in full.
Depends-on: T1, T2. Parallelizable-with: T5 (disjoint files).

## T5 — New drift-guard test

Files (new): `tests/test_openai_skill_consistency.py`.
- Parse `skills/simplify-med/SKILL.md` and `packaging/openai/skills/simplify-med/
  SKILL.md` with `test_skill_consistency.py`'s existing regexes
  (`scripts/([A-Za-z_]+\.py)`, `stages/([A-Za-z_]+\.md)`).
- Assert the two ordered, deduplicated match-lists are equal (D3's drift check).

Done-when: passes against T2's file; a manual (uncommitted) reorder/removal in either
file makes it fail.
Depends-on: T2. Parallelizable-with: T4.

## T6 — README OpenAI section update

Files: `README.md`.
- Rewrite the "What it is" OpenAI paragraph (~L13-15) for both build modes.
- Adjust Layout wording (~L46-47) if it implies MCP is always present.
- Update Packaging section (~L127, L130-137): document `--no-mcp` and both install paths
  — configure the MCP endpoint (existing) vs. drop the skills-only zip under
  `~/plugins/<name>/` or a marketplace.json entry (D8, finding 6).

Done-when: README accurately describes both build modes and installs; no remaining claim
that the OpenAI package always needs an MCP endpoint.
Depends-on: T1. Parallelizable-with: T7.

## T7 — `docs/openai.md` staleness pointer

Files: `docs/openai.md`.
- Add a short note near the top pointing to the `--no-mcp` skills-only mode: what it
  omits (MCP viewer, connector wiring), where to read more (README, DESIGN.md).
- Do not rewrite the rest of the document (out of scope; D8 / Open question 4).

Done-when: short, accurate, additive pointer note exists; diff is small.
Depends-on: T1. Parallelizable-with: T6.

## T8 — Final verification: build, inspect, host-simulated e2e

Goal: prove the shipped package is trace-free and `SKILL.md` alone drives a full run.
Files: none (build/inspection only, scratch output).
- `python3 build.py openai --no-mcp --out dist`; unzip to a scratch directory.
- Inspect: confirm no root `plugin.json`, `mcp.json`, `.mcp.json`, `.app.json`,
  `custom_start.md`, `custom_end.md`, repo-root `agents/*.md`; grep the tree
  case-insensitively for `mcp` / `render_simplify_med_report`.
- Launch a fresh sub-agent (Read/Write/Bash only, no other repo context) as the host,
  using DESIGN.md's exact prompt: read the unzipped `skills/simplify-med/SKILL.md` top to
  bottom and follow it against `tests/fixtures/documents/synthetic-visit-note.txt` copied
  in as input, performing every LLM stage itself with no dispatch mechanism.
- Verify it produces `report.html`/`report.md` under `simplify-runs/<run-id>/`, never
  references `agents/`, `custom_start.md`, `custom_end.md`, or a render tool, and follows
  the stage order and validation/retry contract.
- Record any `SKILL.md` clarity gaps as follow-up notes; exploratory verification, not a
  new permanent automated test.

Done-when: zip inspection shows zero MCP traces; sub-agent host run completes, producing
both report files using only `SKILL.md`, no hook/dispatch references.
Depends-on: T1, T2, T3, T4, T5. Parallelizable-with: none (final gate).

## Owner-only (not for agents)

- Upload and test the `--no-mcp` package in ChatGPT personal (Chat) and a Work/business
  workspace; confirm behavior matches the design's Work-vs-Chat findings.
- Workspace admin approval / install-policy configuration for the imported plugin.
- Manual re-read of the full OpenAI content-policy guidelines page before submission
  (prescription-medication restriction reading is AI-summarized and UNVERIFIED).
- Real logo/composer-icon/skill-icon artwork (current assets are placeholders).
- Deciding whether to rewrite `docs/openai.md` beyond T7's pointer note.

## Open questions

See DESIGN.md "Open questions / risks" (1-6): root `plugin.json` omission is a judgment
call; `Interactive` capability removal is inferential; `disable-model-invocation` vs.
`policy.allow_implicit_invocation` is moot here (only the latter used); `docs/openai.md`
staleness beyond T7 is deferred; zip layout/size limits for submission are undocumented;
script sandbox/network behavior per host surface is unverified (irrelevant while the
pipeline stays offline/stdlib-only).
