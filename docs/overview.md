# simplify-med overview

## Purpose

`simplify-med` helps a patient understand supplied clinical paperwork. It converts extracted document text into a structured, plain-language care plan while preserving traceability to the source.

It is an OpenAI plugin with one bundled skill: `simplify`.

## Supported Inputs

Typical inputs include:

- visit notes;
- discharge summaries;
- medication instructions;
- lab reports;
- imaging reports;
- procedure or follow-up paperwork.

The pipeline accepts one UTF-8 `.txt` file per source document. Text from PDFs, DOCX files, images, or scans must be extracted before the pipeline begins. Known page boundaries can be marked with `\f`.

## Output

The default output is a concise `report.md`, backed by a more complete structured final JSON plan. The patient-facing report keeps facts that affect understanding, action, questions, or safety. Technical, repetitive, generic, and non-actionable supporting detail stays in the audit layer.

The report may contain:

- a short summary;
- reasons for the visit;
- diagnoses stated in the documents;
- medications and documented instructions;
- tests and procedures;
- follow-up timing;
- warning signs explicitly present in the source;
- up to three questions to ask the care team.

On request, the skill can also produce:

- `report.html` for printing or sharing;
- `report.audit.md` showing the source support for report statements.

## How It Works

The pipeline separates language reasoning from deterministic checks:

1. `unitize.py` preserves files, pages, lines, and chunks.
2. `ground.md` extracts source-anchored facts.
3. `anchor_check.py` verifies every quote against the numbered source.
4. `assemble.md` maps checked facts into the care-plan schema.
5. Citation and numeric checks reject or flag unsupported output.
6. Fidelity and critical-coverage reviews identify unsupported claims and important omissions without forcing every extracted detail into the report.
7. Diff and citation guards constrain the repair stages.
8. `finalize.py` merges validated results, records notices, and renders Markdown.

The full rationale for the bundled scripts is in [openai-plugin.md](openai-plugin.md#current-python-decision).

## Limitations

The plugin does not:

- diagnose a condition;
- recommend a new treatment;
- infer why a medicine was prescribed when the document does not say;
- replace a clinician, pharmacist, emergency service, or poison-control service;
- guarantee that source documents are complete or correct.

The report reflects only the supplied documents and explicitly records uncertainty or degraded checks.

## Installable Package

Build a production OpenAI plugin ZIP with:

```bash
python3 build.py
```

Build the independently versioned development plugin with:

```bash
python3 build.py --dev
```

Each successful command increments that channel's patch version. Production
packages use `simplify-med`; development packages use `simplify-med-dev`.
Both packaged OpenAI manifests and the packaged runtime version receive the
same selected name and version. The generated package contains only the plugin
manifests and `skills/`. It contains no version ledger, MCP server, connection
declaration, repository tests, or internal documentation.
