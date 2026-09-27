# simplify-med overview

## Purpose

`simplify-med` helps a patient understand supplied clinical paperwork. It converts extracted document text into a short, plain-language report in which every statement cites the source and is independently verified.

It is an OpenAI plugin with three bundled skills:

- `prep` prepares a patient for an upcoming appointment (requirements, priorities, things to bring, questions to ask);
- `simplify` explains supplied clinical paperwork (the rest of this document);
- `med-lit` runs an opt-in brief health-literacy screen and returns a personal support profile.

`prep` and `med-lit` are instruction-only skills with basic Markdown output; see their `SKILL.md` files and `references/` folders.

## Supported Inputs

Typical inputs include:

- visit notes;
- discharge summaries;
- medication instructions;
- lab reports;
- imaging reports;
- procedure or follow-up paperwork.

The pipeline accepts one UTF-8 `.txt` file per source document. Text from PDFs, DOCX files, or photos and scans of text documents must be extracted before the pipeline begins. Medical images (X-ray, CT, MRI, ultrasound, ECG tracings, body or skin photos) are never read or interpreted, and `unitize.py` refuses image, DICOM, PDF, and other binary files. No skill searches the web or uses any outside source; see the `Hard Boundaries` section of each `SKILL.md`. Known page boundaries can be marked with `\f`.

## Output

The default output is a short `report.md` (target 150-300 words; a warning above 350 and a hard failure above 500). It answers four questions: what happened, what did they find, what do I do now, and when do I come back.

The report may contain, with empty sections hidden:

- a title by visit type (for example "Your ER visit, simplified");
- one or two sentences on why you went;
- "What did they find?": at most six bullets, one per test or exam area, each giving the source's bottom line (radiology Impression or clinician assessment) in plain words;
- the diagnoses stated for this visit and the disposition as stated;
- "What should you do now?": follow-up, tests to schedule, home instructions, and medicine starts, stops, and changes, or a source-stated "no new medicines";
- when to go back to the ER or get help right away, in the source's own words;
- up to three questions to ask, only when useful.

Lab inventories, vital signs, test technique and contrast, empty medication lists, charted background, superseded plans, and radiology boilerplate stay out. There is no "more details" or "already done" section.

On request, the skill can also produce:

- a validated glossary generated from visible finalized content;
- `report.html` for printing or sharing;
- `report.audit.md` showing each visible item with the source lines it cites.

These are optional post-finalization outputs. They never change the final plan, and their failure does not authorize the host to replace `report.md` with an improvised summary.

The skill must be explicitly invoked. Once selected, it runs the complete workflow and returns only the validated `report.md` by default. It does not directly summarize the source or present clinical content from an intermediate artifact.

## How It Works

The pipeline has two model calls and four script runs on the clean path:

1. `unitize.py` numbers every source line, skips URL-only lines, page counters, and exact repeats, writes the numbered `01_source.txt`, and scans for protected candidates (`01_protected.json`).
2. The writer model reads the numbered source and fills the report slots. Every visible item cites the units that support it, and a `coverage` entry records whether each protected category is shown or absent from the source.
3. `check_draft.py` validates the schema and citations, counts words against the budget, flags numbers that do not appear in an item's cited units, and lists protected candidates no item cites.
4. An independent verifier model checks every visible item against the original source (fidelity, negation, uncertainty, exact numbers, attribution, current versus old history) and returns bounded edits, numeric-flag resolutions, and a decision for each uncited protected candidate.
5. `settle.py` validates the verification and applies the edits exactly. If the verifier marks protected content as missing, the writer gets one repair round, which is checked and verified again; a second miss fails the run.
6. `finalize.py` is assertion-only: it publishes `05_plan.final.json` and `report.md` only when every required current-run step passes.

The writer may be retried once per round when the check fails, and the verifier once when settlement rejects its output. Latency and token use are not benchmarked by the test suite; measure them on representative documents.

The full rationale for the bundled scripts is in [openai-plugin.md](openai-plugin.md#current-python-decision).

## Limitations

The plugin does not:

- diagnose a condition;
- recommend a new treatment;
- infer why a medicine was prescribed when the document does not say;
- replace a clinician, pharmacist, emergency service, or poison-control service;
- guarantee that source documents are complete or correct.

The report reflects only the supplied documents and preserves documented uncertainty. A missing, failed, degraded, stale, or invalid core stage prevents publication rather than producing a lower-confidence clinical report.

Runs started under an earlier schema version cannot be resumed; start a fresh run.

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
