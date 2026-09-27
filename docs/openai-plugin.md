# OpenAI plugin guidance

This is the defining authoring guide for `simplify-med`. Use it when changing the existing plugin or adding skills later.

It is based on OpenAI's current plugin and skill documentation and the public Figma, Notion, and Build Web Apps examples:

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Build skills](https://developers.openai.com/codex/skills)
- [OpenAI plugins examples](https://github.com/openai/plugins)
- [Figma plugin](https://github.com/openai/plugins/tree/main/plugins/figma)
- [Notion skills](https://github.com/openai/plugins/tree/main/plugins/notion/skills)
- [Frontend App Builder skill](https://github.com/openai/plugins/blob/main/plugins/build-web-apps/skills/frontend-app-builder/SKILL.md)

## Principles

1. **A plugin packages capabilities; a skill defines one workflow.** The current plugin packages skills and assets only. MCP source (`mcp/openai/`) is parked outside the distributable package and is not yet updated to the current plan shape.
2. **Keep each skill focused on one job.** Add a new skill when a future workflow has a different trigger, outcome, or safety boundary. Do not grow one universal medical skill.
3. **Prefer instructions over code.** Add scripts only for deterministic behavior, repeatable transformations, validation, or external tooling, and only when every target host can run them. ChatGPT regular chat cannot run skill scripts or sub-agents; ChatGPT Work and Codex can.
4. **Use progressive disclosure.** Put trigger and core workflow guidance in `SKILL.md`. Put detailed rules, schemas, examples, and specialized modes in supporting files that are read only when needed.
5. **Describe outcomes, not host internals.** Skills should not begin with path-resolution ceremonies, interpreter version checks, custom start/end hooks, or exact sub-agent dispatch message formats.
6. **Use relative bundled paths.** Paths in a skill are relative to the skill directory. Paths in plugin manifests are relative to the plugin root and start with `./` where the manifest schema requires it.
7. **Keep one canonical workflow.** The repository is an OpenAI plugin, not a shared cross-platform source tree.

## Plugin structure

The repository root is a directly recognizable plugin:

```text
plugin.json                    portable Agent Plugins manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build-versions.json            repository-only prod/dev version counters
skills/                        bundled workflows
```

The distributable ZIP contains only the manifests and `skills/`. Repository-only source such as `mcp/`, tests, and docs must remain outside the package.

### Manifest rules

- Keep production name `simplify-med`; development packages use `simplify-med-dev`.
- Use root `plugin.json` as the portable identity.
- Keep `.codex-plugin/plugin.json` only as a compatibility fallback.
- Keep descriptions concrete and user-facing. State what the plugin helps accomplish, not how the implementation is arranged.
- Declare only components that exist in the package.
- Keep OpenAI presentation metadata in the supported OpenAI manifest fields.
- Before public submission, provide real `privacyPolicyURL` and `termsOfServiceURL` values owned by the plugin publisher. Never invent placeholder legal URLs.
- Treat `build-versions.json` as the prod/dev version ledger and never package it.
- Increment only the selected patch version for each successful build; validation failures must not consume a version.
- Production builds synchronize root `plugin.json` and `.codex-plugin/plugin.json`. No skill carries an embedded version constant.
- Development builds stamp `simplify-med-dev` and the dev version into both packaged manifests without changing production source metadata.

## Skill structure

Every future skill uses this shape unless it has a demonstrated need for another resource type:

```text
skills/<skill-name>/
  SKILL.md
  agents/openai.yaml           optional OpenAI UI metadata
  references/                  optional detailed guidance loaded on demand
  scripts/                     optional deterministic helpers
  assets/                      optional templates or media
```

The existing `simplify` skill predates the `references/` naming convention and keeps `stages/` (`write.md`, `verify.md`), `reference/` (`style_rules.md`, `abbreviations.json`), and `schema/` (only `plan.schema.json`, for structured output on request). It has no `scripts/` or `templates/`. New skills should use the conventional directories above.

`prep` and `med-lit` are the reference examples of this convention: `SKILL.md`, `agents/openai.yaml`, `assets/` icons, and on-demand `references/`, with no scripts. Their language judgments (question drafting, requirement extraction, faithful instrument administration) belong to the model, and their outputs are conversational Markdown rather than validated run artifacts.

### `SKILL.md` rules

- Frontmatter must include a lowercase hyphenated `name` and a concise `description`.
- Front-load the trigger in the description because hosts may shorten descriptions in the initial skills list.
- Include a meaningful boundary when adjacent requests should not invoke the skill.
- Use imperative instructions with explicit inputs and outputs.
- Keep core safety constraints near the top.
- Link to supporting files rather than copying their full contents into `SKILL.md`.
- Read only the supporting files needed for the current stage or mode.
- Allow the host to choose its normal execution and delegation mechanisms. State what may run in parallel, but do not prescribe internal dispatch payloads.
- For a multi-stage, safety-sensitive workflow, state whether invocation must be explicit and put the complete-workflow contract near the top.
- If partial execution is unsafe, prohibit direct outcome substitution and require validated terminal artifacts before user-facing content is presented.
- Define terminal failure behavior. Required stages must fail closed rather than silently skip or degrade.
- Name the only supporting files the host may read and tell it never to open, list, download, or unpack other plugin files. Hosts that cannot apply a skill are told to "pick the next-best approach and continue", so a skill that depends on something the host lacks invites an improvised imitation.
- Do not require users or agents to run `python3 --version`, resolve an absolute skill path up front, or read empty platform hook files.
- If a skill does use a required command, report the concrete failure when it cannot run. Do not add speculative prerequisite checks.
- Keep one `SKILL.md`; do not create packaging overlays or platform-specific copies.

### `agents/openai.yaml` rules

- Use it for user-facing skill metadata, implicit-invocation policy, icons, and the default prompt.
- Keep workflow instructions in `SKILL.md`, not in `openai.yaml`.
- Use skill-relative asset paths.
- Do not declare an MCP dependency in the current skills-only plugin.

## When a script is justified (future skills)

This is general guidance for future skills; no current skill ships scripts. A script must first be runnable on every host the skill targets (it is not in ChatGPT regular chat). Given that, a script is justified when at least one of these is true:

- The result must be deterministic across model runs.
- The operation validates or constrains model output.
- The operation transforms files or structured data more reliably than prose instructions.
- The operation provides security, privacy, citation, or numeric safeguards.
- The operation is reused by multiple stages and duplicating it in prompts would be error-prone.
- The operation invokes an external tool or format parser.

A script is not justified merely because a step can be automated. Prefer model instructions for summarization, classification, drafting, reviewing meaning, and other language judgments.

### Rules for script design

- Keep scripts standard-library-only where practical.
- Give each user-invoked script a clear input/output contract and actionable errors.
- Keep internal helper modules private to the script layer; do not mention them in `SKILL.md` unless the agent invokes them directly.
- Do not split a helper into its own file solely to make the tree look modular. Split when it is reused, independently testable, or isolates a safety-critical algorithm.
- Do not replace deterministic checks with “the model can inspect this.” The model produces the content; an independent check is valuable specifically because it is not the same reasoning pass.
- Test observable behavior and safety invariants. Avoid tests that only lock wording or heading order in `SKILL.md`.

## Current decision: prompt-only `simplify`

Builds up to 0.1.5 ran `simplify` as a write-then-verify pipeline driven by Python scripts and eleven JSON schemas. In a field test in ChatGPT regular chat, which cannot run skill scripts or sub-agents, the host read every script and schema (about 190 KB, about 50k tokens), failed to download the plugin into its sandbox, then hand-built its own units, draft, and checks while its progress messages implied the pipeline ran. None of it executed. Evidence and decisions: `agent_files/claude-prompt-only-simplify-2026-09-27/` (`discovery.md`, `PRD.md`).

Decision (owner, 2026-09-27):

- `simplify` has no scripts, templates, run folders, run logs, repair round, glossary, HTML report, or audit file. Its flow is READ → WRITE → VERIFY → OUTPUT.
- Every former script check is a named rule in the verify checklist (`stages/verify.md`); the mapping is in [architecture.md](architecture.md#strictness-moved-from-scripts-into-prompts). Each visible item carries 1-3 verbatim evidence quotes so each claim is checkable.
- Verification runs exactly once in a fresh sub-agent where available (ChatGPT Work, Codex), otherwise as a separate second pass reading only the source and the draft. No environment probe.
- One schema remains, `schema/plan.schema.json`, used only when the user asks for structured output.
- `build.py` no longer stamps a pipeline version into the skill.

Trade-offs accepted:

| Lost deterministic guarantee | Mitigation |
|---|---|
| Citations mechanically checked | Verbatim evidence quotes per item; the verifier checks each quote against the source; quotes are easy for a human to audit in the structured output. |
| Numbers mechanically matched | The verifier compares every number with the item's quote. |
| Protected content scanned by regex; missing content forced a repair | Writer and verifier each fill the must-keep checklist from a full read of the source; the verifier adds missing must-keep content itself. Recall now depends on the model. |
| Word budget counted by script | The verifier counts the rendered report; the limit is small enough to count. |
| Fail-closed publication gate | The report is rendered only from the verified draft; verification is never skipped. There is no mechanical gate, so a host could ignore the rule, as with any prompt instruction. |
| Verification independence | Fresh sub-agent where available. In regular chat the second pass is the same model in the same context; weaker, but the only option there. |
| Reproducibility and audit trail | No run folder. The structured output (with evidence quotes) is the audit view on request. |

Gains: identical behavior in chat, Work, and Codex; no hidden imitation pipeline; two model passes and about four small file reads instead of about 50k tokens of scripts.

Revisit scripts only if every target host can run them and a deterministic check proves materially better than its prompt rule on representative documents.

## Medical workflow boundaries

- The plugin explains supplied records; it does not diagnose, prescribe, triage beyond directing urgent concerns to appropriate care, or create facts absent from the documents.
- Source anchoring (verbatim evidence quotes) and numeric preservation are product requirements, not optional implementation details.
- Protected patient-specific content (medication changes, follow-up, return precautions, diagnoses, disposition, abnormal or pending results) is shown or confirmed absent from the source by the verifier; generic education, technical mechanics, duplicates, and routine detail stay out of the report.
- Required clinical stages fail closed. Verification is never skipped, and unverified content is never shown.
- The only outside input allowed is the user's own health records, retrieved on the user's request from a connected health-records app, as text. No web, public references, or other connectors.
- Source documents and the internal draft stay within the conversation unless the user explicitly moves or shares them.

### Enforcing "no web search" (host settings)

The plugin cannot switch off web search by itself; the rules in each skill are the plugin's only lever. Verified against the Codex source (openai/codex, 2026-09):

- Codex web search is a hosted tool that hooks never see, so a plugin `PreToolUse` hook cannot block it. A plugin manifest has no config or permissions field.
- To turn web search off, the user sets `web_search = "disabled"` in `~/.codex/config.toml`; a workspace admin can require it with `allowed_web_search_modes = ["disabled"]` in `requirements.toml`.
- Shell network access stays off with the default `[sandbox_workspace_write] network_access = false`.
- Plugin hooks run only after the user trusts them and then apply to every session, not just these skills, so this plugin ships none.
- In ChatGPT chat there are no plugin hooks; the user's own search and connector toggles apply. The Hard Boundaries allow only the user's own health-records connector, used on request to read their records.

## Adding a skill

1. Define one user outcome, trigger, and non-trigger boundary.
2. Start instruction-only. Add resources only after identifying a concrete repeated need.
3. Put the minimal workflow in `SKILL.md`; move detailed guidance to `references/`.
4. Add `agents/openai.yaml` only for OpenAI metadata, invocation policy, and icons.
5. Add scripts only for deterministic or external-tool work and document why each exists.
6. Add behavior-focused tests for the new capability and its safety constraints.
7. Validate the skill and plugin manifests, build the OpenAI package, and inspect the archive contents.
8. Test representative prompts that should and should not trigger the skill.
9. Update `README.md`, `docs/README.md`, and this guide if the new skill establishes a reusable convention.

## Review checklist

- Is the skill one focused job?
- Is the description concise, discriminating, and front-loaded?
- Can supporting material be loaded only when needed?
- Are all scripts (if any) deterministic or tool-facing, and runnable on every target host?
- Is any host-specific bootstrapping leaking into `SKILL.md`?
- Is there one canonical OpenAI workflow with no packaging copies?
- Are manifest paths relative and package contents real?
- Do both packaged manifests have the selected build name and version?
- Is `build-versions.json` absent from the package?
- Does the package contain only manifests and skills?
- Are medical claims source-bound and independently checked?
- Does explicit invocation complete every required stage before presenting clinical content?
- Is every must-keep category shown or confirmed absent from the source by the verifier?
- Does the skill name the only files the host may read?
- Are tests checking behavior rather than prose formatting?

## Anti-patterns

- “Resolve `<skill>` to an absolute path and use it in every command.”
- “Confirm `python3 --version` runs” before attempting a required command.
- Empty `custom_start.md` or `custom_end.md` files used as extension points.
- A second platform-specific `SKILL.md` that copies the same workflow.
- Exact sub-agent dispatch message templates in a portable skill.
- Adding a script for a one-off language judgment the model can perform directly.
- Removing evidence, numeric, or verification guards because the model can usually self-check. (Moving a guard from a script into an explicit verify rule is different: the rule stays, and a separate pass enforces it.)
- Shipping scripts to a host that cannot run them, so the model imitates the pipeline.
- Letting a host satisfy a staged skill by returning the requested outcome directly.
- Showing a draft, or anything not verified.
