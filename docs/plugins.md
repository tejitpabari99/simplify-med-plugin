# Adding a platform

For an engineer or agent adding support for a platform other than Claude
Code, claude.ai, or OpenAI (Gemini, Cursor, a custom harness). Read
[architecture.md](architecture.md) first if you need the pipeline itself;
this document is about packaging and running the same pipeline somewhere
else.

## What a plugin is here

One Agent Skill, `skills/simplify-med/` — `SKILL.md` plus `stages/`,
`scripts/`, `schema/`, `reference/`, `templates/` — is the portable core.
Everything a platform needs to run the pipeline is inside that folder.
`SKILL.md`'s frontmatter carries exactly two fields, verified by
`tests/test_skill_consistency.py`'s `TestSkillFrontmatter`:

```yaml
name: simplify-med
description: >
  Turn a clinical document ... into a plain-language, fact-checked
  care plan with an audit trail. ...
```

Everything else in this repository is a **per-platform wrapper** around
that folder: `.claude-plugin/plugin.json` and `agents/*.md` are Claude
Code's wrapper; the root portable manifest, staged OpenAI dependency and
final handoff instructions are the OpenAI wrapper. A new platform gets its
own wrapper, not a fork of the skill folder.

## The Agent Skills standard

The Agent Skills format defines a broader set of optional frontmatter
fields beyond `name` and `description` (for example, tool restrictions or
free-form metadata) — this repository does not use or document any of
them; `SKILL.md`'s own design brief entry says exactly why: "the same
skill folder uploads to claude.ai unchanged. Claude Code-specific
frontmatter fields would break packaging elsewhere, so SKILL.md uses only
`name` and `description`" (`brainstorm.v1.md`, "Platform and shape"). If
you need the full current list of standard fields for whatever platform
you're targeting, check that platform's own Agent Skills documentation
before adding anything to `SKILL.md`'s frontmatter — this repo's own
source of truth stops at the two fields above, enforced by
`test_skill_consistency.py`.

For reference, the standard Agent Skills frontmatter has six fields:

| Field | Meaning |
|---|---|
| `name` | required; max 64 chars; lowercase letters, digits, hyphens |
| `description` | required; what the skill does and when to use it; this is what triggers it |
| `allowed-tools` | optional; tools the skill may use |
| `license` | optional; license identifier or file |
| `compatibility` | optional; runtime or platform requirements |
| `metadata` | optional; free-form key/value map |

Any other field (for example Claude Code's `context`, `agent`, `model`,
`disable-model-invocation`) is platform-specific and must not be added to
this skill's `SKILL.md`, because packaging for other platforms either
fails or ignores it; put such settings in the platform wrapper instead.
Source: the [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
and Claude Code's [skills reference](https://code.claude.com/docs/en/skills.md).

**What must not be added to `SKILL.md`:** anything platform-specific
(a Claude Code tool-permission field, a host-specific directive). Doing so
would make the skill folder stop uploading cleanly to a plain Agent Skills
host. Platform-specific behavior belongs in that platform's wrapper, never
in `SKILL.md` itself.

## Single source of truth for metadata

`plugin.meta.json` (repo root):

| Field | Meaning |
|---|---|
| `name` | plugin id, `"simplify-med"` |
| `version` | semver, currently `"0.1.0"` |
| `schema_version` | the version every run's JSON files declare in their own `schema_version` field, currently `"1.0"` |
| `description` | one-line description, reused as the Claude Code manifest's description |
| `tags` | category tags |
| `author` | `{name}` |
| `homepage` | repo URL |
| `skills` | array of skill folder names under `skills/`, currently `["simplify-med"]` |

**Sync rule.** `.claude-plugin/plugin.json`'s `version` and
`skills/simplify-med/scripts/_version.py`'s `PLUGIN_VERSION` constant must
both equal `plugin.meta.json`'s `version`. `packaging/build.py`'s
`check_versions()` reads all three (`load_meta`, `load_manifest`,
`load_version_constant` — the last execs `_version.py`'s source directly
rather than importing it, to stay import-order independent) and calls
`raise SystemExit(2)` with a message naming the mismatch, before writing
anything, on any disagreement. This is enforced by
`tests/test_build.py`'s `TestBuildVersionMismatch` (two cases: manifest
version wrong, `_version.py` wrong).

## The runtime a platform must provide

- Python 3, standard library only — no pip installs, ever.
- Ability to run shell commands and read/write files in a working
  directory (every script is invoked as
  `python3 <skill>/scripts/<name>.py --run-dir <run> ...`).
- Ability to read the skill's own bundled files (`stages/`, `reference/`,
  `schema/`, `templates/`).
- Optionally, the ability to dispatch sub-agents. If absent, per the
  current `SKILL.md`: "read the stage file yourself and perform the stage
  in the current context, writing the output file, one stage at a time, in
  the same order as below." The pipeline degrades to sequential in-context
  execution, not a missing feature.
- The portable medical pipeline never needs network access. A platform may add a
  separate integration after finalization: the OpenAI package, for example, uses a
  presentation-only MCP endpoint and a browser-side file download. That integration
  must not introduce network access into the pipeline scripts or generated HTML.

## What a platform wrapper must provide

1. **A manifest in the platform's format**, generated from
   `plugin.meta.json`'s fields (see the table above) — the way
   `.claude-plugin/plugin.json` is Claude Code's manifest today (written
   by hand, kept in sync by `build.py`'s version check, not yet
   auto-generated; see Known gaps in `architecture.md` and the "Platform
   packaging customization" entry in `futures.md`).
2. **A way to register or emulate the seven stage agents**, named exactly
   as `agents/*.md` names them: `simplify-med-ground`,
   `simplify-med-glossary`, `simplify-med-assemble`,
   `simplify-med-review-fidelity`, `simplify-med-review-coverage`,
   `simplify-med-assemble-missing`, `simplify-med-correct`. Each is, per
   every `agents/*.md` file's own body: read the named stage file under
   `<skill>/stages/`, read the input files the dispatch message names,
   write the one named output file, reply with exactly one line (`<output
   path> — <N> items written`). If the platform has no sub-agent concept,
   document that it uses the in-context fallback path instead — do not
   invent a sub-agent registration mechanism that isn't there.
3. **A packaging profile** — see below. Platform-specific instruction files are
   applied to a temporary staged copy; do not edit the source skill during a build.

OpenAI uses the sequential in-context fallback for the seven medical LLM stages when
the host does not expose a matching sub-agent mechanism. Its staged
`agents/openai.yaml` declares the presentation dependency; it does not replace the
medical stage agents or turn the MCP server into a processing service. See
[openai.md](openai.md).

## How the build works today

The preferred entry point is the root dispatcher:

```bash
python3 build.py claude-code
python3 build.py claude-ai
python3 build.py openai
```

`packaging/build.py --platform <name> --out <dir>` remains a compatibility entry point.
Shared code verifies version consistency, creates a temporary staging tree, installs
blank default `custom_start.md` and `custom_end.md`, applies the selected platform's
overrides and ignores, then writes `dist/<name>-<version>-<platform>.zip`. Platform
profiles own archive layout, manifests, exclusions, and platform instructions.

The source skill is read-only from the builder's point of view. All overlay work happens
in temporary staging, and tests check that a build does not mutate
`skills/simplify-med/`.

Claude Code packages the plugin wrapper and registered agents. Claude.ai packages the
standalone skill. OpenAI packages a portable root `plugin.json`, root `mcp.json`, the
staged skill and its `agents/openai.yaml`, and any manifest-referenced assets; it does
not package the MCP server source. See [openai.md](openai.md#build-and-package) for the
OpenAI archive and endpoint configuration.

## Adding a platform — step by step

1. Add `packaging/<platform>/` with its ignore rules, custom-file overrides, manifests,
   and assets as needed. Keep common behavior in the shared builder.
2. Register the platform with both the root dispatcher and compatibility entry point.
3. Build from a temporary stage. Start with blank defaults, apply only that platform's
   overlay, and keep the canonical skill unchanged.
4. Generate platform manifests from `plugin.meta.json` where possible. If two staged
   files carry the same endpoint or identifier, render them from one configuration
   source and add a drift test.
5. Add package tests covering name, archive root, expected entries, exclusions,
   referenced assets, version agreement, override precedence, and no source mutation.
6. Run `python3 build.py <platform>` and
   inspect the archive (`python3 -c "import zipfile;
   print('\n'.join(zipfile.ZipFile('dist/....zip').namelist()))"`) to
   confirm the entry set and internal layout are what the platform needs.

## Checklist for the platform agent

- Reproduce `SKILL.md`'s stages on the platform — same order, same file
  handoffs, same parallel groups (or fall back to the documented
  sequential path if the platform has no sub-agents).
- Verify the stage agents (or the in-context fallback) can read files by
  absolute path, exactly as every dispatch message and script invocation
  in `SKILL.md` assumes.
- Run the deterministic test suite (`python3 -m unittest discover -s
  tests`) inside that platform's sandbox — it needs nothing but Python 3
  stdlib and should be a faithful pre-check before trusting the platform
  with a real document.
- Run a kill test — a full pipeline run on one of `tests/fixtures/documents/`
  or a real document — the way `docs/agent_files/2026-09-22-simplify-med-plugin-brief/kill-test-1.md`
  and `kill-test-2.md` did for Claude Code.
- Record friction in a new
  `docs/agent_files/2026-09-22-simplify-med-plugin-brief/kill-test-<platform>.md`,
  in the same shape (outcome, timeline, friction, fidelity spot-check,
  ledger recall, verdict) so it's comparable to the two existing reports.

## More

- [architecture.md](architecture.md) — the pipeline itself.
- [overview.md](overview.md) — the patient-facing picture.
- [openai.md](openai.md) — the implemented OpenAI wrapper, MCP viewer, deployment, and
  privacy boundary.
- `agent_files/` — the original design brief and both kill tests.
