# Design: OpenAI package as a plain skills-only plugin

Status: draft for review. Branch `users/tejitpabari/mcp-browser-response`.

## Goal & non-goals

**Goal.** Add a `--no-mcp` build mode to the existing OpenAI package that produces a
standard OpenAI/ChatGPT **skills-only plugin**: no MCP server, no UI widget, no
connector/app wiring, and a single self-contained `SKILL.md` that itself narrates the
whole pipeline (no hand-off to `agents/*.md`, `stages/*.md`-as-dispatch-target,
`custom_start.md`, or `custom_end.md`). The default (no-flag) OpenAI build, and the
Claude Code / claude.ai builds, are unchanged.

**Non-goals** (explicitly out of scope for this change):
- Deleting `mcp/` or any MCP code path. `mcp/openai/` and every MCP branch in
  `packaging/build.py` stay; `--no-mcp` is a build-time flag, not a deletion.
- Changing `skills/simplify-med/SKILL.md` (the canonical file) or the Claude Code /
  claude.ai packaging profiles.
- Rewriting `docs/openai.md` (flagged as follow-up debt in Open questions).
- Deploying, testing in a live ChatGPT workspace, or content-policy sign-off (owner-only).

## Background (current state, concise)

- `python3 build.py openai [--no-mcp] [--app-id ID] [--mcp-url URL] [--release]` builds
  the OpenAI zip via `packaging/build.py`. Today `--no-mcp` only strips the MCP
  *connection info* (`mcp.json`, `.mcp.json`, `mcpServers` key, `dependencies:` block);
  everything else — manifest shape, `SKILL.md`, the `agents/*.md` + `stages/*.md`
  indirection, `custom_end.md`'s `render_simplify_med_report` call — is untouched, so
  today's "`--no-mcp`" package is really "MCP-optional," not a plain skill plugin.
- The canonical `skills/simplify-med/SKILL.md` (248 lines) is the orchestrator for every
  platform. It hands off in three places: `custom_start.md` (L12-14, blank for OpenAI),
  the agent-dispatch mechanism naming `<plugin>/agents/<stage>.md` (L51-66, only usable
  on Claude Code — OpenAI never ships repo-root `agents/*.md`, so OpenAI already falls
  back to "read the stage file yourself" at L68-72), and `custom_end.md` (L206-208,
  OpenAI's copy calls `render_simplify_med_report`, the MCP render tool).
- `packaging/openai/` holds the OpenAI overlay: `plugin.json` (root, portable-format
  manifest with `extensions.com.openai.interface`), `agents/openai.yaml` (skill-level,
  `interface` + `policy.allow_implicit_invocation: true` + a `dependencies.tools[]` MCP
  entry), `.codex-plugin/plugin.json` (compat manifest, `mcpServers: "./.mcp.json"`),
  `custom_end.md` (the render-tool hook), `assets/` + `skill-assets/` (icons).
- 300 tests pass today (`python3 -m unittest discover -s tests`). Only
  `tests/test_build.py` references OpenAI/MCP; `tests/test_skill_consistency.py` and
  `tests/test_stage_docs.py` hard-assert the canonical `SKILL.md`'s agent/stage
  structure and are unaffected by this change (D4: canonical file untouched).

## Research findings that drive the design

Full notes: `research-openai-plugins.md` (scratchpad), backed by a local clone of
`github.com/openai/plugins`.

1. **Manifest location.** All 60+ example plugins use `.codex-plugin/plugin.json`, none
   use a bare root `plugin.json` — `developers.openai.com` calls the root-manifest
   "portable" format newer, but zero real plugins use it
   (`plugins/build-web-apps/.codex-plugin/plugin.json`,
   `plugins/notion/.codex-plugin/plugin.json`, `plugins/figma-plugin/.codex-plugin/plugin.json`).
2. **Skills-only shape.** `plugins/build-web-apps/.codex-plugin/plugin.json` has no
   `mcpServers`/`apps` key and `"skills": "./skills/"` — this is the literal template for
   `--no-mcp`. `.mcp.json`/`.app.json` are exactly the two files that wire a connector; a
   true skills-only plugin ships neither.
3. **`capabilities`.** Observed values across the repo: `Interactive`, `Read`, `Write`.
   `build-web-apps` (skills-only, no MCP, no widget) still declares
   `["Interactive", "Read", "Write"]` — so `Interactive` is not itself an MCP/UI-widget
   marker; it appears to track whatever a skill genuinely does (build-web-apps drives a
   real browser for UI testing). `simplify-med` reads text files and writes reports; it
   does not drive anything interactively. Decision D2 below drops `Interactive` for
   `--no-mcp` on that basis, not because the string is banned.
4. **Skill-level `agents/openai.yaml`** is present in effectively every example skill,
   with `interface.{display_name,short_description,icon_small,icon_large,default_prompt}`
   and, for router/specialist families, `policy.allow_implicit_invocation`.
   `dependencies.tools[]` is rare (2 hits repo-wide) and only used to declare an MCP/CLI
   dependency — confirms dropping it entirely for `--no-mcp` is correct, not a loss of a
   required field.
5. **SKILL.md conventions.** Required frontmatter is only `name` + `description`;
   "front-load the key use case and trigger words." Folder roles: `references/` for
   policy/schema/background, `scripts/` for deterministic computation, `assets/` for
   templates to copy. Median skill length 60-150 lines; richer orchestrator skills run
   400-530 lines. Script-invocation pattern
   (`life-science-research/skills/string-skill/SKILL.md`) documents an exact
   stdin/stdout or CLI contract and nothing more — closest structural analog to
   simplify-med's `python3 scripts/<name>.py --run-dir <run> ...` contract.
   Progressive disclosure ("load the stage file when you need it, don't inline it")
   is the dominant pattern and is why stage prompt files stay separate rather than being
   pasted into `SKILL.md` (D3).
6. **Submission categories.** `developers.openai.com/plugins/deploy/submission.md`
   explicitly lists "Skills-only" as one of three named, supported plugin configurations
   ("a skills-only plugin that packages reusable workflows") — direct first-party
   confirmation this rebuild targets a real, supported shape.
7. **Work vs Chat.** "Plugins declaring MCP servers work only in the ChatGPT desktop
   app" (implying a skills-only plugin is *not* desktop-restricted); workspace-imported
   plugins "start private" pending admin review. Sandbox/network/stdlib behavior for
   `scripts/` is **not documented anywhere** — inferred only from examples
   (`life-science-research` scripts make live HTTPS calls). See D6.
8. **Content policy.** The submission guidelines ban prescription-medication commerce
   ("Prescription medications and age-restricted pharmaceuticals") but the fetched page
   had no explicit medical-information-content restriction — flagged UNVERIFIED, owner
   to re-read before submission (Owner-only items).

## Decisions

### D1 — `--no-mcp` is the skills-only trigger; default build unchanged

`python3 build.py openai --no-mcp` (equivalently `python3 packaging/build.py --platform
openai --no-mcp`) produces the skills-only package. In that mode:
- No `mcp.json`, no `.mcp.json`, no `mcpServers` key anywhere.
- No `dependencies:` block in `agents/openai.yaml`.
- No MCP/render-tool wording anywhere in the staged tree (existing
  `_assert_no_mcp_traces` guard, extended — see "build.py/packaging changes").
- No `--mcp-url`/`--release` endpoint validation runs (these flags remain rejectable in
  combination with `--no-mcp` exactly as `--mcp-url` already is; `--release` alone with
  `--no-mcp` already succeeds today per `test_no_mcp_with_release_still_builds` and stays
  a no-op with `--no-mcp`, since there is no endpoint left to validate).
- **`--app-id` combined with `--no-mcp` is now a CLI error** (behavior change — see
  below). `--app-id` alone (without `--no-mcp`) is unchanged: it still implies
  MCP-free staging internally, the way it does today.

Rationale for the `--app-id`/`--no-mcp` rejection: `--app-id` exists to reference an
*existing ChatGPT dev-mode app* (a connector/app id) instead of shipping an MCP
endpoint — it is inherently about wiring a connector, which has no meaning once the
package has no app/connector concept at all. Today's `test_app_id_with_no_mcp_is_
redundant_but_allowed` treats the combination as silently accepted; this design treats
it as user error worth surfacing (a person invoking `--no-mcp` believing they get a
plain skill plugin, while also passing `--app-id`, has a self-contradictory request).

Default (no flag) OpenAI build, Claude Code build, and claude.ai build: byte-for-byte
unchanged behavior.

### D2 — Manifest: `.codex-plugin/plugin.json` only, trimmed capabilities

For `--no-mcp`:
- Ship **only** `.codex-plugin/plugin.json`, not the root `plugin.json`. Reasoning: zero
  real examples use the root portable-format manifest (finding 1); the root
  `plugin.json`'s current shape here (`extensions.com.openai.interface`, a repo-specific
  invention) doesn't match any example's field layout either, so dropping it for the
  skills-only build removes a manifest that would need reshaping just to match a format
  nothing else uses. The default (MCP) build keeps shipping root `plugin.json` unchanged
  (D1) — no example plugin was found for the *hybrid MCP-only* case either, but that is
  out of scope; not touching an already-shipping default build is the priority.
- `.codex-plugin/plugin.json` fields for `--no-mcp`: `name`, `version`, `description`,
  `author`, `homepage`, `skills: "./skills/"`, `interface` (`displayName`,
  `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`,
  `websiteURL`, `defaultPrompt`, `composerIcon`, `logo`). No `mcpServers`, no `apps`.
- `capabilities: ["Read", "Write"]` for `--no-mcp` (drops `"Interactive"` — finding 3).
  Default build keeps `["Interactive", "Write"]` unchanged.
- `defaultPrompt` stays the existing single string
  (`"Simplify this medical document into a plain-language care plan."`) — already
  within the documented ≤3 strings / ≤128 chars constraint.
- Version stays synced with `plugin.meta.json` via `check_versions()`; the
  `packaging/openai/.codex-plugin/plugin.json`-version-mismatch branch
  (`packaging/build.py` L104-116) keeps guarding the compat manifest regardless of
  `--no-mcp`, since that file is what actually ships in both modes.

### D3 — Self-contained OpenAI-specific `SKILL.md`, used only for `--no-mcp`

The default (MCP) OpenAI build keeps using the canonical `skills/simplify-med/SKILL.md`
exactly as staged today (unchanged, per D1/D4) — it still relies on `custom_end.md`'s
`render_simplify_med_report` call, which only makes sense when an MCP viewer exists.

The **`--no-mcp` build only** overlays a new, OpenAI-specific `SKILL.md` on top of the
staged canonical one. Source path: **`packaging/openai/skills/simplify-med/SKILL.md`**
— chosen because it mirrors the staged-tree path it overwrites
(`skill_destination/SKILL.md`), consistent with how `packaging/openai/agents/openai.yaml`
mirrors `skill_destination/agents/openai.yaml`; it sits naturally beside the other
per-platform override files already living under `packaging/openai/` rather than
inventing a new overlay convention.

This file is a single orchestrator: no `custom_start.md`/`custom_end.md` hooks, no
`agents/` dispatch, no repo-root `agents/*.md` references. Frontmatter is `name` +
`description` only (matches the documented minimal requirement and the canonical file's
own frontmatter shape). It reads `<skill>/stages/<stage>.md` directly and performs each
LLM stage in the current context, sequentially, in the same stage order as the canonical
file — `stages/*.md`, `reference/`, `schema/`, `scripts/`, `templates/` stay unchanged,
unmoved, and untouched; `SKILL.md` owns *flow*, those files own *per-stage detail*
(matches the progressive-disclosure pattern in finding 5).

Target length: as short as possible while complete, aiming **≤ ~180 lines** (the
canonical file is 248 lines; this version sheds the two hook sections and the
agent-dispatch/fallback branching in section 4, which together are roughly 35 of those
248 lines, and folds `custom_end.md`'s non-MCP content directly into the final section
instead of pointing at a separate file).

**Drift guard.** A new test parses both `SKILL.md` files with the same regexes
`test_skill_consistency.py` already uses (`scripts/([A-Za-z_]+\.py)`,
`stages/([A-Za-z_]+\.md)`) and asserts the OpenAI file's matches are the same *set*, in
the same *order*, as the canonical file's. This catches the two files drifting when a
stage or script is added/renamed/reordered in the canonical pipeline and someone forgets
the OpenAI copy.

### D4 — Canonical `SKILL.md` and Claude Code packaging: no changes

Confirmed unchanged in this work: `skills/simplify-med/SKILL.md`,
`agents/*.md` (repo root), `packaging/claude-code/`, `packaging/claude-ai/`,
`tests/test_skill_consistency.py`, `tests/test_stage_docs.py`. Nothing in this design
touches them.

### D5 — Skill-level `agents/openai.yaml` for `--no-mcp`

Same file, same location (`skills/simplify-med/agents/openai.yaml` in the staged tree),
with only `interface` (`display_name`, `short_description`, `icon_small`, `icon_large`,
`default_prompt`) and `policy.allow_implicit_invocation: true`. No `dependencies:` key
at all (today's `_strip_yaml_top_level_key` removal already produces exactly this —
reused unchanged, see build.py section).

### D6 — Work vs Chat

- Skills-only plugins are not documented as desktop-restricted (only MCP-declaring
  plugins are, per finding 7) — a point in favor of shipping `--no-mcp` widely.
- Workspace-imported plugins start private pending admin approval regardless of
  MCP/skills-only shape; this is an install-time/admin concern, not a build-time one.
- Script sandbox/network policy is undocumented for either surface. The simplify-med
  pipeline is stdlib-only and fully offline (no network calls in any `scripts/*.py`), so
  this gap does not block the design — there is nothing in the package that depends on
  network access working.
- Code-execution availability itself is UNVERIFIED per host surface (personal chat vs.
  workspace vs. Codex CLI). `SKILL.md`'s own "Prerequisites" step (D3) handles this
  generically: check `python3 --version`; if code execution is unavailable at all, stop
  and tell the user, rather than branching on Work vs. Chat. No research finding shows an
  actual behavioral difference between Work and Chat for a skills-only plugin, so the
  design adds no Work/Chat conditional anywhere in `SKILL.md`.

### D7 — Tests

See "Testing & verification" below for the full list of additions/removals.

### D8 — Docs

`README.md`'s OpenAI section (lines 13-15, 46-47, 127, 130-137) is rewritten to describe
both build modes: default (MCP-included, unchanged) and `--no-mcp` (skills-only). Install
instructions cover both: unzip and either configure the MCP endpoint (existing flow) or
drop the skills-only zip's contents under `~/plugins/<name>/` or a repo/team
`.agents/plugins/marketplace.json` entry (per finding 6's confirmed personal/team install
mechanism). `docs/openai.md` is explicitly **not** rewritten in this pass (Open
questions).

## Target package tree for `--no-mcp`

```
simplify-med/
  .codex-plugin/
    plugin.json                  # skills-only manifest; no mcpServers/apps; capabilities: [Read, Write]
  assets/
    logo.png
    composer-icon.png
    logo.svg                     # (kept: harmless, already shipped; not referenced by manifest)
  skills/
    simplify-med/
      SKILL.md                   # OpenAI-specific orchestrator (overlay, replaces canonical copy)
      agents/
        openai.yaml              # interface + policy only, no dependencies:
      assets/
        icon-large.png
        icon-small.svg
      stages/
        ground.md
        glossary.md
        assemble.md
        review_fidelity.md
        review_coverage.md
        correct.md
        assemble_missing.md
      scripts/
        unitize.py, merge_facts.py, anchor_check.py, glossary_check.py,
        cite_check.py, numeric_parity.py, sanitize_review.py, diff_guard.py,
        finalize.py, render_md.py, render_html.py, render_audit.py,
        readability.py, runlog.py, textnorm.py, plan_view.py, validate.py,
        _version.py
      reference/
        categories.md, abbreviations.json, style_rules.md, ahrq_plain_language.json
      schema/
        care_plan_agent.schema.json, additions_raw.schema.json, ... (all schema files)
      templates/
        report.html
```

Not present: root `plugin.json`, `mcp.json`, `.mcp.json`, `.app.json`,
`custom_start.md`, `custom_end.md`, any repo-root `agents/*.md`, `docs/`, `tests/`,
`packaging/`, `mcp/`.

## build.py / packaging/build.py changes

All changes are inside `packaging/build.py`; `build.py` (root) only needs its CLI wiring
updated to match.

1. **`build()` signature** (currently L464-472): rename `include_mcp: bool = True` to
   **`no_mcp: bool = False`** so the function itself knows whether `--no-mcp` was
   literally passed, independent of what `--app-id` implies. Immediately after the
   existing `--app-id` validation block (L476-490):
   ```python
   if app_id is not None:
       ...
       if no_mcp:
           raise SystemExit("--app-id cannot be combined with --no-mcp")
       no_mcp = True  # --app-id implies no-mcp staging, same as today
   include_mcp = not no_mcp
   ```
   Everything below this point in `build()` keeps using `include_mcp` exactly as today
   (L491-515 unchanged).

2. **CLI callers** — `build.py` root L44-52 and `packaging/build.py` `main()` L550-558:
   change `include_mcp=not args.no_mcp` to `no_mcp=args.no_mcp`.

3. **`_stage_openai()`** (L344-436): restructure so the steps that only make sense for
   an MCP-capable, hook-driven package become conditional, and the `--no-mcp` branch
   gains the SKILL.md overlay and manifest trimming:
   - Move the `custom_start.md`/`custom_end.md` staging (today's L351 default-copy call
     plus L353-355 overlay copy) so it runs **only when `include_mcp`**. The `--no-mcp`
     package ships neither file — D3 makes them unreferenced, so shipping blank/legacy
     copies would be inert clutter, not a hook mechanism to preserve.
   - Move the root `plugin.json` copy (today's L366) so it runs **only when
     `include_mcp`** (D2: no root manifest for `--no-mcp`).
   - Keep the skill copy (L347-350), `agents/` overlay (L356), `assets`/`skill-assets`
     overlay (L357-361), and `.codex-plugin/` overlay (L362-365) unconditional — all
     needed in both modes.
   - Inside the existing `if not include_mcp:` block (L370-410):
     - Add capability trimming right after loading `compat_manifest` (L377): set
       `compat_manifest["interface"]["capabilities"] = ["Read", "Write"]` before popping
       `mcpServers` (D2).
     - Add the new SKILL.md overlay: `_copy_if_present(os.path.join(overlay, "skills",
       "simplify-med", "SKILL.md"), os.path.join(skill_destination, "SKILL.md"))`
       (overwrites the canonical copy already staged at L347-350).
     - Keep the existing `dependencies:` strip (L390-394), `--app-id`/`.app.json`
       handling (L379-407, unchanged — `--app-id` without `--no-mcp` still reaches this
       branch exactly as today since `app_id` still forces `include_mcp = False`), and
       `_assert_no_mcp_traces(plugin_stage)` call (L409) — extend
       `_NO_MCP_FORBIDDEN_STRINGS` (L314) with `"render_simplify_med_report"` so a stray
       copy-paste of the old hook language into the new SKILL.md fails the build loudly.
   - The `include_mcp=True` branch (L412-436) is untouched.

4. **`_stage_platform()`** (L439-461): no signature change beyond passing `include_mcp`
   through as already happens; the `if not include_mcp: raise SystemExit("--no-mcp
   applies only to the OpenAI build")` guard (L447-448) stays, now fed by the
   `no_mcp`-derived `include_mcp` computed in `build()`.

5. **`_NO_MCP_FORBIDDEN_STRINGS`** (L314): add `"render_simplify_med_report"` (see
   above) — the one new forbidden string; the other three stay.

No changes to `_source_endpoint`, `_endpoint_error`, `_strip_yaml_top_level_key`,
`check_versions`, `parse_ignore_file`, `is_ignored`, `iter_included_files`, or any
claude-code/claude-ai code path.

## OpenAI SKILL.md outline (`packaging/openai/skills/simplify-med/SKILL.md`)

Section-by-section skeleton; stage list and script commands pulled directly from the
canonical file (same order, same scripts, same output filenames — required by the drift
guard):

```
---
name: simplify-med
description: <front-loaded trigger phrase — clinical document, plain language, care
  plan, fact-checked — trimmed to fit ChatGPT's ~8000-char skill-list budget; content
  equivalent to the canonical description, no MCP/viewer wording>
---

Resolve <skill> to this file's directory. Establish <run> at Stage 0.

## Prerequisites
- Confirm python3 is available and code execution works. If it does not, stop and
  tell the user their ChatGPT surface cannot run this skill's scripts.

## Inputs
(same as canonical §2: one .txt per source document, extract non-text yourself first,
 :ocr/:pasted suffixes, one run = everything given, no simplification-level question,
 tell the user you're starting)

## Running a script
(same contract as canonical §3: python3 <skill>/scripts/<name>.py --run-dir <run> ...;
 exit codes; status-line format; unitize's second-to-last-line exception)

## Performing an LLM stage
Read <skill>/stages/<stage>.md and follow it exactly, writing only the named output
file, in the current context — no sub-agent dispatch. Do every stage in the order
below; never skip one.
Validation and one retry: after each stage, run its check script; on validator failure,
redo the stage once with the check's stderr appended; on a second failure, follow the
failure table.

## Stage 0 -- unitize (script)
python3 <skill>/scripts/unitize.py --runs-dir <cwd>/simplify-runs --input <file> ...

## Stage 1 -- ground and glossary
- K x: read stages/ground.md -> 02_facts.<k>.raw.json; check anchor_check.py --chunk <k>
- read stages/glossary.md -> 02_glossary.raw.json; check glossary_check.py
- python3 <skill>/scripts/merge_facts.py --run-dir <run>

## Stage 2 -- assemble
- read stages/assemble.md -> 03_plan.raw.json; check cite_check.py (-> 03_plan.draft.json)
- python3 <skill>/scripts/numeric_parity.py --run-dir <run>  (-> 03_flags.json)

## Stage 3 -- review
- read stages/review_fidelity.md -> 04_review.raw.json; check sanitize_review.py --only review
- read stages/review_coverage.md -> 04_coverage.raw.json; check sanitize_review.py --only coverage

## Stage 4 -- correct and fill gaps
- if corrections > 0: read stages/correct.md -> 05_plan.corrected.raw.json;
  check diff_guard.py --strict (retry once), then diff_guard.py (settles) -> ...corrected.json
  else: diff_guard.py directly (records skipped)
- if missing > 0: read stages/assemble_missing.md -> 05_additions.raw.json;
  check cite_check.py --additions
  else: cite_check.py --additions directly (records skipped)

## Stage 5 -- finalize (script)
python3 <skill>/scripts/finalize.py --run-dir <run>

## Present results
(inlines packaging/openai/custom_end.md points 1, 2, 5 -- drop points 3-4, the
 render-tool call and its file-handling restrictions, entirely)
- Native summary: key next actions, medication changes/questions, tests, appointments,
  follow-up timing, uncertainty explicitly present in the report; state this is a
  reading aid, not a new diagnosis or treatment instruction.
- Attach/link 06_plan.final.json, report.md, report.html.
- Never paste the plan into chat; never mention fact ids/line numbers/run internals.
- On request for sources: python3 <skill>/scripts/render_audit.py --run-dir <run> ->
  point to report.audit.md.

## Failure table
(same table as canonical §12, verbatim)

## Run folder
(same as canonical §13, verbatim)
```

Estimated length at this density: ~150-175 lines.

## Work vs Chat

No branching logic added to `SKILL.md` (D6). Documented findings only:
- Skills-only plugins are not gated to the ChatGPT desktop app (only MCP-declaring ones
  are, per the fetched enterprise plugin-management page) — `--no-mcp` should work in
  personal Chat and Work/business workspaces alike, subject to workspace admin install
  policy (an install-time decision, not a build-time one).
- Workspace plugins import as private pending admin review regardless of shape.
- No documented or observed difference in script sandbox/network/stdlib availability
  between personal and workspace surfaces; irrelevant here since the pipeline is
  offline/stdlib-only.
- Code-execution availability itself is unverified per surface; handled generically by
  the Prerequisites step, not by a Work/Chat branch.

## Testing & verification

**Update `tests/test_build.py`:**
- Rewrite `test_no_mcp_build_omits_all_mcp_connection_info` to also assert: no root
  `plugin.json` in the archive; `.codex-plugin/plugin.json` has `capabilities ==
  ["Read", "Write"]`; no `custom_start.md`/`custom_end.md` under the staged skill; the
  staged `SKILL.md` differs from the canonical `skills/simplify-med/SKILL.md` (proves
  the overlay took effect) and contains no `agents/`, `custom_start.md`,
  `custom_end.md`, or `render_simplify_med_report` text.
- Remove `test_app_id_with_no_mcp_is_redundant_but_allowed`; add
  `test_app_id_rejects_no_mcp_combination` asserting a non-zero exit and a stderr
  message naming both flags.
- `test_icons_exist_at_referenced_paths_and_interfaces_match` currently reads root
  `plugin.json`'s interface and compares it to the compat manifest's — that comparison
  only applies to the default build. Add a parallel `--no-mcp` variant that checks icon
  paths resolve using only `.codex-plugin/plugin.json` and `agents/openai.yaml` (no root
  `plugin.json` to cross-check against).
- Leave every MCP-only test (`test_endpoint_override_...`, both `test_release_...`,
  `test_non_release_...`, `test_no_mcp_rejects_mcp_url`, the remaining `--app-id` tests)
  unchanged — they exercise the default/`include_mcp=True` path, which is unchanged
  behavior (D1).

**New drift-guard test** (new file, e.g. `tests/test_openai_skill_consistency.py`, or a
new test class in `test_skill_consistency.py`): read both
`skills/simplify-med/SKILL.md` and `packaging/openai/skills/simplify-med/SKILL.md`,
extract `scripts/([A-Za-z_]+\.py)` and `stages/([A-Za-z_]+\.md)` matches in file order
from each with the existing regexes, and assert the two ordered-and-deduplicated lists
are equal. This is the one drift check D3 requires.

**Full suite:** `python3 -m unittest discover -s tests` must still report all tests
passing after the above additions/removals (currently 300; expect roughly 300 minus 1
removed plus 2-3 added).

**Host-simulated end-to-end run (planned, post-implementation, via sub-agent).** Once
the build.py changes and new `SKILL.md` exist:
1. Run `python3 build.py openai --no-mcp --out dist` and unzip the result to a scratch
   directory.
2. Launch a fresh sub-agent (Read/Write/Bash only, no repo context beyond the unzipped
   package) with the prompt: "You are ChatGPT running this plugin's skill. Read
   `skills/simplify-med/SKILL.md` top to bottom and follow it exactly, using
   `tests/fixtures/documents/synthetic-visit-note.txt` (copy it in as the one input
   file) as the input. Perform every LLM stage yourself by reading the named stage file
   and writing the named output file — you are the model, there is no dispatch
   mechanism. Do not read any file this SKILL.md does not tell you to read." This
   mirrors how `tests/test_pipeline_e2e.py` already drives the deterministic scripts,
   but — unlike that test — has a real model perform the LLM stages instead of
   hand-written fixture JSON, which is the part unique to validating `SKILL.md` itself
   is executable end to end without agents/, custom_start.md, or custom_end.md.
3. Verify the sub-agent produces `report.html` and `report.md` in a
   `simplify-runs/<run-id>/` folder, that it never referenced `agents/`,
   `custom_start.md`, `custom_end.md`, or any render tool, and that it followed the
   stage order and validation/retry contract. Treat any deviation as a `SKILL.md`
   clarity bug, not a pipeline bug (the deterministic scripts are already covered by
   `test_pipeline_e2e.py`).
4. This run is exploratory verification of the design, not a new permanent automated
   test (it depends on live model behavior) — its purpose is to catch places where the
   new `SKILL.md`'s prose is ambiguous or under-specified compared to the canonical
   file's, before the package is submitted anywhere.

## Owner-only items

- Upload and test the `--no-mcp` package in ChatGPT personal (Chat) and a Work/business
  workspace; confirm real install/behavior matches this design's Work-vs-Chat findings.
- Workspace admin approval / install-policy configuration for the imported plugin.
- Manual re-read of the full OpenAI content-policy guidelines page before submission —
  the prescription-medication restriction is a commerce/procurement ban per this
  research, but that reading is AI-summarized and UNVERIFIED; the owner should confirm
  directly, given the domain sensitivity.
- Real logo/composer-icon/skill-icon artwork (current assets are placeholders per prior
  commits).
- Deciding whether to also rewrite `docs/openai.md` in a follow-up (not in this design's
  scope; see Open questions).

## Open questions / risks

1. **Root `plugin.json` omission is a judgment call, not a documented rule.** No example
   plugin was found in either the skills-only *or* MCP-only configuration that ships a
   root `plugin.json`; the recommendation to drop it for `--no-mcp` while keeping it for
   the default build is internally consistent (D1: don't touch the shipping default) but
   not independently verified against a real "hybrid" or "MCP-only" example.
2. **`Interactive` capability removal is inferential, not confirmed.** `build-web-apps`
   keeps `Interactive` while being skills-only, which shows the capability isn't an
   MCP-only marker, but nothing in the docs defines what `Interactive` formally gates —
   dropping it is a reasonable-but-unverified precision choice; easy to revert to
   `["Read", "Write", "Interactive"]` if it turns out to affect discoverability.
3. **`disable-model-invocation` vs `policy.allow_implicit_invocation`** (two competing
   self-trigger mechanisms found in the wild) — this design uses only the latter
   (dominant pattern, 18+ examples vs. 2), consistent with D5, but OpenAI's own docs
   don't state which wins if both are present. Not applicable here since we only set one.
4. **`docs/openai.md` (571 lines) goes stale.** It describes the MCP-based design in
   detail and is not touched by D8 (README-only). Recommend a follow-up pass once this
   design ships, so the doc doesn't actively mislead a reader about the `--no-mcp` mode
   that will now exist alongside the MCP mode it documents.
5. **Zip layout/size limits for submission are undocumented.** Nothing found bounds file
   count or byte size for a submitted skills-only package; not a blocker for build.py
   changes, but worth a sanity check against the actual submission portal when the owner
   uploads.
6. **Sandbox/network behavior for `scripts/` is unverified per host surface** (D6) —
   irrelevant today since the pipeline is offline, but would matter if a future stage
   needed network access.
