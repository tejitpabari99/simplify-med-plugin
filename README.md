# simplify-med

## What it is

simplify-med is a Claude Code plugin that turns a clinical document into a plain-language, fact-checked care plan. A deterministic pipeline of scripts and LLM stages grounds every statement to a line of the original document, assembles a structured care plan, reviews and corrects it for fidelity and coverage, and renders it to Markdown and a single self-contained HTML page. Every interim file the pipeline writes is schema-validated and logged, so a full run leaves an auditable trail from source text to final output.

## Layout

```
plugin.meta.json               source of truth for name/version/description
.claude-plugin/plugin.json     Claude Code manifest (version must match plugin.meta.json)
skills/simplify-med/
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
packaging/                     build.py, claude-code.ignore, claude-ai.ignore
tests/                         unittest modules and fixtures
docs/agent_files/...           design brief and futures list (excluded from packages)
```

Some of the directories above (`stages/`, `reference/`, `templates/`, `agents/`, and the
non-`validate.py`/`runlog.py` scripts) are populated by later sub-projects; this
sub-project lays down the metadata, schemas, validator, run logger, packaging, and
tests that everything else builds on.

## Install for local dev

```
claude --plugin-dir /path/to/simplify-med-plugin
```

Then invoke the `simplify-med` skill from within Claude Code.

## Input contract

- One `.txt` file per source document.
- Insert a form-feed character (`\f`) between pages when page boundaries are known.
- Each input file has a declared extraction method: `native` (text layer extracted
  directly from a digital document), `ocr` (extracted via optical character
  recognition from a scan or image), or `pasted` (typed or pasted in by a person,
  no reliable page/line structure guaranteed).

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
python3 packaging/build.py --platform claude-code --out dist
python3 packaging/build.py --platform claude-ai --out dist
```

`--platform claude-code` packages the whole plugin (wrapped in a top-level
`simplify-med/` folder) for use as a Claude Code plugin. `--platform claude-ai`
packages just `skills/simplify-med/` (also wrapped in `simplify-med/`) for use as
a standalone Claude.ai skill. Both write a zip to `dist/` (gitignored).

## Versioning

`plugin.meta.json` is the source of truth for the plugin's version.
`.claude-plugin/plugin.json` must carry the same `version`, and
`skills/simplify-med/scripts/_version.py`'s `PLUGIN_VERSION` must match it too —
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
