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

- a validated glossary generated from visible finalized content;
- `report.html` for printing or sharing;
- `report.audit.md` showing the source support for report statements.

These are optional post-finalization outputs. They never change the final plan, and their failure does not authorize the host to replace `report.md` with an improvised summary.

Every verified fact is accounted for. Critical patient-specific facts appear in cited content; supporting facts receive one audited omission reason such as duplicate, generic education, technical detail, routine non-actionable information, or not patient-specific. Generic education does not become patient-specific merely because it was attached to discharge paperwork.

The skill must be explicitly invoked. Once selected, it runs the complete workflow and returns only the validated `report.md` by default. It does not directly summarize the source or present clinical content from an intermediate artifact.

## How It Works

The pipeline separates three model responsibilities from deterministic checks:

1. `unitize.py` preserves files, pages, lines, and chunks.
2. The grounding model extracts complete-clause, source-anchored facts from each chunk; `anchor_check.py` and `merge_facts.py` require every expected chunk to pass.
3. The assembly model creates a concise draft and assigns every non-visible fact an audited omission disposition.
4. `cite_check.py` validates citations and fact dispositions, while `numeric_parity.py` creates stable numeric flags.
5. One independent review model checks every visible fact and omission, fidelity, negation, uncertainty, medication status, urgency, and every numeric flag.
6. `settle_review.py` validates the review and applies accepted operations exactly, then reruns citation, disposition, and numeric checks.
7. If a critical omission requires new prose, the workflow permits one bounded reassembly followed by a fresh independent review. New prose never bypasses review.
8. `finalize.py` is assertion-only: it publishes `06_plan.final.json` and `report.md` only when every required current-run stage and artifact passes.

For `K` source chunks, the clean path uses `K + 2` model calls: `K` grounding calls, one assembly call, and one combined review call. A clean one-chunk run targets approximately 13 core artifacts. This is the implemented call and artifact contract; latency and token improvements still require representative benchmarking.

The full rationale for the bundled scripts is in [openai-plugin.md](openai-plugin.md#current-python-decision).

## Limitations

The plugin does not:

- diagnose a condition;
- recommend a new treatment;
- infer why a medicine was prescribed when the document does not say;
- replace a clinician, pharmacist, emergency service, or poison-control service;
- guarantee that source documents are complete or correct.

The report reflects only the supplied documents and preserves documented uncertainty. A missing, failed, degraded, stale, or invalid core stage prevents publication rather than producing a lower-confidence clinical report.

Completed schema-v1 final reports can still be rendered to Markdown, HTML, or audit views. Partial schema-v1 runs are rejected; they must be restarted as fresh schema-v2 runs.

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
