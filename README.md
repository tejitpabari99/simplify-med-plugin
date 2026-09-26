# simplify-med

An OpenAI plugin that turns supplied clinical documents into a plain-language, source-anchored care plan with deterministic validation and an audit trail.

## Plugin Structure

The repository root is the plugin folder OpenAI uses:

```text
plugin.json                    portable Agent Plugins manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build-versions.json            repository-only prod/dev version counters
skills/simplify/
  SKILL.md                     workflow and safety boundaries
  agents/openai.yaml           OpenAI skill metadata
  assets/                      skill icons
  stages/                      language-stage instructions
  scripts/                     deterministic checks and renderers
  schema/                      structured-data contracts
  reference/                   medical plain-language rules and dictionaries
  templates/                   report template
```

`mcp/openai/` remains in the repository for possible future work. It is not connected to the plugin, declared by either manifest, or included in the ZIP.

## What It Does

1. Splits extracted document text into numbered source units.
2. Extracts atomic facts anchored to exact source lines.
3. Builds a structured plain-language care plan from checked facts only.
4. Reviews fidelity, coverage, and numeric preservation.
5. Applies bounded corrections and fills verified omissions.
6. Produces Markdown, with HTML and a source audit available on request.

The language work lives in `skills/simplify/stages/`. Python is reserved for deterministic work such as source anchoring, schema validation, citations, numeric checks, bounded diffs, audit logging, and rendering. See `docs/openai-plugin.md` for the governing authoring rules and the per-script rationale.

## Build the Plugin ZIP

Production build:

```bash
python3 build.py
```

Development build:

```bash
python3 build.py --dev
```

`build-versions.json` stores independent production and development versions.
Every successful build increments the selected version's patch number before
creating the archive. Failed builds do not consume a version.

Production builds:

- package `simplify-med`;
- update `plugin.json`, `.codex-plugin/plugin.json`, and the pipeline version in the source tree;
- write `dist/simplify-med-<version>-openai.zip`.

Development builds:

- package `simplify-med-dev`;
- stamp the dev name and version into both packaged manifests and the packaged pipeline version;
- leave the production manifests in the source tree unchanged;
- write `dist/simplify-med-dev-<version>-openai.zip`.

The version ledger is repository-only and is never included in either archive.

Use a different output directory with:

```bash
python3 build.py --out /path/to/output
python3 build.py --dev --out /path/to/output
```

The builder uses an allowlist. The ZIP contains only:

- `plugin.json`
- `.codex-plugin/plugin.json`
- `skills/`

It excludes `build-versions.json`, `mcp/`, `docs/`, `tests/`, `agent_files/`, repository metadata, caches, and the builder itself.

## Use in OpenAI

Install or import the generated ZIP as an OpenAI plugin. The plugin exposes the `simplify` skill and requires no MCP server, connector, endpoint, API key, or separate deployment.

Ask it to simplify a visit note, discharge summary, lab report, imaging report, or similar clinical document. Input text should be extracted to UTF-8 `.txt`; page boundaries may be represented with form-feed characters (`\f`).

Each run writes `simplify-runs/<run-id>/` in the working directory. The folder contains the stage artifacts, `run.json`, the final JSON plan, and `report.md`. `report.html` and `report.audit.md` are created only when requested.

## Safety Boundary

- The plugin explains supplied records; it does not diagnose or prescribe.
- Every medical statement must be supported by the source documents.
- Missing information stays missing rather than being guessed.
- Numeric details are checked independently.
- The result is a reading aid, not a replacement for clinical or emergency care.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

When the OpenAI plugin and skill validators are available in your development
environment, run them against `.` and `skills/simplify` before distribution.
Run `build.py` only when you intend to consume the next production or development version.

## Documentation

- `docs/openai-plugin.md` — defining rules for manifests, skill creation, resources, scripts, and future skills.
- `docs/architecture.md` — the medical transformation pipeline and deterministic safeguards.
- `docs/overview.md` — user-facing behavior, inputs, outputs, and limitations.
- `docs/openai.md` — the current skills-only OpenAI package and archive boundary.
