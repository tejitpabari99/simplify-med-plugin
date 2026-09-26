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

1. **A plugin packages capabilities; a skill defines one workflow.** The current plugin packages skills and assets only. MCP source is retained outside the distributable package.
2. **Keep each skill focused on one job.** Add a new skill when a future workflow has a different trigger, outcome, or safety boundary. Do not grow one universal medical skill.
3. **Prefer instructions over code.** Add scripts only for deterministic behavior, repeatable transformations, validation, or external tooling.
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
- Production builds synchronize root `plugin.json`, `.codex-plugin/plugin.json`, and the pipeline's embedded version constant.
- Development builds stamp `simplify-med-dev` and the dev version into both packaged manifests and the packaged version constant without changing production source metadata.

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

The existing `simplify` skill predates the `references/` naming convention and retains `stages/`, `reference/`, `schema/`, and `templates/` because they are stable pipeline resources. New skills should use the conventional directories above. Do not copy the legacy layout unless the new skill truly needs a staged, schema-validated pipeline.

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
- Define retry, bounded repair, and terminal failure behavior. Required stages must fail closed rather than silently skip or degrade.
- Do not require users or agents to run `python3 --version`, resolve an absolute skill path up front, or read empty platform hook files.
- If a required command cannot run, report the concrete failure. Do not add speculative prerequisite checks.
- Keep one `SKILL.md`; do not create packaging overlays or platform-specific copies.

### `agents/openai.yaml` rules

- Use it for user-facing skill metadata, implicit-invocation policy, icons, and the default prompt.
- Keep workflow instructions in `SKILL.md`, not in `openai.yaml`.
- Use skill-relative asset paths.
- Do not declare an MCP dependency in the current skills-only plugin.

## When a script is justified

A script is justified when at least one of these is true:

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

## Current Python decision

The existing Python is retained because it implements deterministic safeguards and rendering, not medical reasoning.

| Files | Decision | Reason |
|---|---|---|
| `unitize.py`, `textnorm.py` | Keep | Stable line numbering, chunking, normalized matching, and source offsets are foundational to traceability. |
| `anchor_check.py`, `merge_facts.py` | Keep | Independently verify source quotes and combine checked facts without asking the model to validate itself. |
| `glossary_check.py`, `cite_check.py`, `numeric_parity.py` | Keep | Enforce schema, valid citations, bounded fields, and preservation of clinically important numbers. |
| `settle_review.py` | Keep | Validate exhaustive independent review, apply exact bounded operations, require numeric resolutions, and prevent unsupported edits. |
| `validate.py`, `runlog.py`, `_version.py` | Keep as internal helpers | Shared schema validation, atomic audit logging, and version fields are reused across the pipeline. They are not separate model workflow steps. |
| `finalize.py`, `plan_view.py`, `readability.py` | Keep | Assert complete current-run state, construct the patient view, calculate reading level, and publish only validated final artifacts. |
| `render_md.py`, `render_html.py`, `render_audit.py` | Keep | Produce repeatable downloadable artifacts from validated JSON without a new model rewrite. |

Do not add another Python file unless its deterministic responsibility cannot fit cleanly in an existing module. Revisit consolidation only when two modules have the same responsibility or are never reused independently; file size alone is not a reason to move logic into the model.

The model owns language judgment: complete-clause fact extraction, concise critical-first assembly, and one independent semantic review. Python owns repeatable enforcement: source anchoring, schemas, citation and omission accounting, numeric parity, exact settlement, run identity, rendering, and final publication gates. Do not move medical-language judgment into Python merely to reduce model calls, and do not move deterministic safeguards into prompts merely to reduce file count.

## Medical workflow boundaries

- The plugin explains supplied records; it does not diagnose, prescribe, triage beyond directing urgent concerns to appropriate care, or create facts absent from the documents.
- Source anchoring and numeric preservation are product requirements, not optional implementation details.
- Critical patient-specific content remains visible; generic education, technical mechanics, duplicate facts, and routine non-actionable detail may be omitted only with an audited disposition reviewed independently.
- Required clinical stages fail closed. A missing, failed, degraded, stale, or invalid core stage cannot produce a report.
- Completed legacy reports may remain renderable, but an in-progress run must not cross a schema boundary.
- Source documents, fact ledgers, and audit artifacts remain local to the skill run unless the user explicitly moves or shares them.

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
- Are all scripts deterministic or tool-facing?
- Is any host-specific bootstrapping leaking into `SKILL.md`?
- Is there one canonical OpenAI workflow with no packaging copies?
- Are manifest paths relative and package contents real?
- Do both packaged manifests have the selected build name and version?
- Is `build-versions.json` absent from the package?
- Does the package contain only manifests and skills?
- Are medical claims source-bound and independently checked?
- Does explicit invocation complete every required stage before presenting clinical content?
- Is every verified fact visible or covered by an independently reviewed omission disposition?
- Do bounded repairs receive a fresh review whenever they add patient-facing prose?
- Are tests checking behavior rather than prose formatting?

## Anti-patterns

- “Resolve `<skill>` to an absolute path and use it in every command.”
- “Confirm `python3 --version` runs” before attempting a required command.
- Empty `custom_start.md` or `custom_end.md` files used as extension points.
- A second platform-specific `SKILL.md` that copies the same workflow.
- Exact sub-agent dispatch message templates in a portable skill.
- Adding a script for a one-off language judgment the model can perform directly.
- Removing citation, numeric, schema, or correction guards because the model can usually self-check.
- Letting a host satisfy a staged skill by returning the requested outcome directly.
- Publishing a draft after a missing review, degraded core check, or failed finalization.
