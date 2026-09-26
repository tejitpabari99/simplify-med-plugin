# simplify-med

## What it is

simplify-med is a portable Agent Skill, packaged for Claude Code, claude.ai, and OpenAI,
that turns a clinical document into a plain-language, fact-checked care plan. A
deterministic pipeline of scripts and LLM stages grounds every statement to a line of
the original document, assembles a structured care plan, reviews and corrects it for
fidelity and coverage, and renders it to Markdown and a single self-contained HTML
page. Every interim file the pipeline writes is schema-validated and logged, so a full
run leaves an auditable trail from source text to final output.

The OpenAI package can be built two ways. The default build (`python3 build.py openai`)
adds a presentation-only MCP viewer after finalization; medical processing still runs in
the host, and the developer-operated endpoint is designed not to download or process
document or report bytes — see [`docs/openai.md`](docs/openai.md) for the exact data
flow, privacy boundary, deployment requirements, and PHI limitations. `python3 build.py
openai --no-mcp` instead produces a plain skills-only plugin with no MCP server,
connector, or viewer at all — see the [Packaging](#packaging) section below and
[`docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md`](docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md).

## Documentation

- [`docs/README.md`](docs/README.md) — index of the documentation suite.
- [`docs/overview.md`](docs/overview.md) — what simplify-med is, how to install and run it, and what a report contains.
- [`docs/architecture.md`](docs/architecture.md) — a deep dive: the run folder, the stage graph, every deterministic check, the data contracts, and testing.
- [`docs/plugins.md`](docs/plugins.md) — for adding support for another platform.
- [`docs/openai.md`](docs/openai.md) — the OpenAI package, MCP viewer, data flow,
  security boundary, deployment, testing, and operator checklist.

## Layout

```
plugin.meta.json               source of truth for name/version/description
.claude-plugin/plugin.json     Claude Code manifest (version must match plugin.meta.json)
build.py                       root platform build dispatcher
skills/simplify/
  SKILL.md                     skill entry point
  stages/                      one prompt per LLM stage: ground, glossary, assemble,
                                review_fidelity, review_coverage, assemble_missing, correct
  scripts/                     stdlib-only Python: unitize, validate, anchor_check,
                                merge_facts, cite_check, numeric_parity, sanitize_review,
                                diff_guard, finalize, render_md, render_html, render_audit,
                                readability, runlog
  schema/                      JSON Schema for every interim and final file
  reference/                   style_rules.md, categories.md, abbreviations.json,
                                ahrq_plain_language.json
  templates/                   report.html
agents/                        thin Claude Code agent definitions, one per LLM stage
packaging/                     shared staging plus claude-code, claude-ai, openai profiles;
                                packaging/openai/skills/simplify/SKILL.md overlays a
                                self-contained orchestrator used only by `openai --no-mcp`
mcp/openai/                    presentation-only MCP server and report widget, used only by
                                the default OpenAI build (absent from `openai --no-mcp`)
tests/                         unittest modules and fixtures
docs/agent_files/...           design brief and futures list (excluded from packages)
```

## How a run works

`SKILL.md` (`skills/simplify/SKILL.md`) is the entry point: it walks the
model running the skill through unitizing the input, dispatching each LLM
stage to its `agents/simplify-med-<stage>` agent (or running the stage
in-context if sub-agents aren't available), and running the deterministic
check script after each one, with one retry on a validation failure.

1. **Unitize** (script) splits the input into numbered units and chunks.
2. **Ground** (one agent per chunk) `‖` **Glossary** (one agent) run in
   parallel, then `merge_facts` verifies and renumbers the surviving facts.
3. **Assemble** (one agent) turns the fact ledger into a typed care plan;
   `cite_check` drops anything uncited and `numeric_parity` flags number
   mismatches as hints for the next stage.
4. **Review: fidelity** `‖` **Review: coverage** run in parallel, then
   `sanitize_review` resolves both into a corrections list and a missing-facts
   list.
5. **Correct** (skipped if there are no corrections) `‖` **Assemble-missing**
   (skipped if nothing is missing) run in parallel; `diff_guard` and
   `cite_check --additions` verify their output stays inside its bounds.
6. **Finalize** (script) merges everything, re-checks citations, re-detects
   the glossary against the final text, sweeps for leaked names, scores
   readability, and renders `report.md` / `report.html`. `render_audit.py`
   builds `report.audit.md` on request, never automatically.

Every stage's outcome (`ok` / `degraded` / `skipped` / `failed`) is recorded
in `run.json`; ground and assemble failing stops the run, everything else
degrades gracefully and the report carries a plain-language notice.

## Install for local dev

```
claude --plugin-dir /path/to/simplify-med-plugin
```

Then invoke the `simplify` skill from within Claude Code.

## Try it

```
claude --plugin-dir /path/to/simplify-med-plugin
```

Then ask Claude to simplify a clinical document, e.g. "simplify this visit
note for me" with a `.txt` file attached or pasted. Each run is written to
`simplify-runs/<run-id>/` in the current working directory (gitignored) --
that folder is the full audit trail, from the numbered source units through
`report.html`. Ask "how was this verified?" or "show your sources" to get
`report.audit.md`, which pairs every statement in the plan with the exact
line of the original document it came from.

## Input contract

- One `.txt` file per source document.
- Insert a form-feed character (`\f`) between pages when page boundaries are known.
- Optionally suffix a file with `:native` (default), `:ocr`, or `:pasted` to label
  its extraction method in the audit trail.

## Run folder layout

Each run lives in `simplify-runs/<run-id>/` (gitignored) and contains:

- Numbered stage output files (e.g. `01_units.json`, `02_facts.json`, ... through
  the care plan, review, coverage, and additions stages), each schema-validated
  and each carrying top-level `schema_version` and `plugin_version` fields.
- `run.json` — the run's audit trail, written and updated by every stage through
  `runlog.py`: per-stage status, attempts, timestamps, checks, and run-level
  notices.
- `report.md` and `report.html` — the final rendered care plan.

## Packaging

```
python3 build.py claude-code
python3 build.py claude-ai
python3 build.py openai            # default: includes the presentation MCP viewer
python3 build.py openai --no-mcp   # skills-only plugin, no MCP server/connector
```

Claude Code and claude.ai packages preserve the existing host behavior. The default
OpenAI build adds portable root manifests, OpenAI-specific final handoff instructions,
and a dependency on the separately deployed presentation MCP endpoint; an OpenAI
production build needs that deployed HTTPS endpoint, which the ZIP itself does not
deploy — follow [`docs/openai.md`](docs/openai.md#deploy).

`python3 build.py openai --no-mcp` instead produces a plain skills-only plugin: no root
`plugin.json`, no `mcp.json`/`.mcp.json`, no connector wiring, and only
`.codex-plugin/plugin.json` as the manifest, with an OpenAI-specific self-contained
`SKILL.md` — there is no server to deploy for this mode. Install it either by unzipping
its contents under `~/plugins/<name>/` (or adding a repo/team
`.agents/plugins/marketplace.json` entry pointing at it), or by uploading/importing the
zip directly in ChatGPT. See
[`docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md`](docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md)
(D2, D8) for the exact package tree and rationale.

All modes write a zip to `dist/` (gitignored). The existing `python3 packaging/build.py
--platform <platform> --out dist` form remains available for compatibility.

## Versioning

`plugin.meta.json` is the source of truth for the plugin's version.
`.claude-plugin/plugin.json` must carry the same `version`, and
`skills/simplify/scripts/_version.py`'s `PLUGIN_VERSION` must match it too —
`packaging/build.py` checks all three and exits with status 2 on any mismatch,
before writing anything.

## Tests

```
python3 -m unittest discover -s tests -v
```

All tests use the Python standard library only (no pip installs, no network
access) and must pass from a clean checkout.

## Design docs

See `docs/agent_files/2026-09-22-simplify-med-plugin-brief/` for the design brief
and futures list this plugin was built from.
