# simplify-med overview

## Purpose

`simplify-med` helps a patient understand supplied clinical paperwork. It converts document text into a short, plain-language report in which every statement is backed by a verbatim quote from the source and checked in a separate verification pass.

It is an OpenAI plugin with three bundled skills:

- `prep` prepares a patient for an upcoming appointment (requirements, priorities, things to bring, questions to ask);
- `simplify` explains supplied clinical paperwork (the rest of this document);
- `med-lit` runs an opt-in brief health-literacy screen and returns a personal support profile.

All three are instruction-only skills: no scripts, no code execution, no run folders. `prep` and `med-lit` return basic Markdown; see their `SKILL.md` files and `references/` folders.

## Supported Inputs

Typical inputs include:

- visit notes;
- discharge summaries;
- medication instructions;
- lab reports;
- imaging reports;
- procedure or follow-up paperwork.

The skill reads text only: pasted text, the text of uploaded documents (including photos or scans of text documents, read as text), or the user's own records that the user asks it to retrieve from a connected health-records app. Medical images (X-ray, CT, MRI, ultrasound, ECG tracings, pathology, body or skin photos) are never read or interpreted; written reports about them are fine. If the input has no usable text, the skill asks for the written text.

No skill searches the web or uses any outside source or other connector; the user's own health-records connector, used on request to read their own records, is the one exception. See the `Hard Boundaries` section of each `SKILL.md`. The plugin cannot switch off the host's web search itself; see [openai-plugin.md](openai-plugin.md#enforcing-no-web-search-host-settings) for the `web_search = "disabled"` setting.

## Output

The default output is a short Markdown report of at most about 300 words, returned in the conversation. It answers four questions: what happened, what did they find, what do I do now, and when do I come back.

The report may contain, with empty sections hidden:

- a title by visit type (for example "Your ER visit, simplified" or "Your urgent care visit, simplified");
- one or two sentences on why you went, keeping every complaint the source lists;
- "What did they find?": at most six bullets, one per test or exam area, each giving the source's bottom line (radiology Impression or clinician assessment) in plain words;
- the diagnoses stated for this visit and the disposition as stated;
- "What should you do now?": follow-up and tests to schedule (with the source's timing and reason), home instructions, and medicine starts, stops, and changes, or a source-stated "no new medicines";
- "When should you go back to the ER?" (ER visits and hospital stays) or "When to get help right away" (others), with the source's action and urgency;
- up to three questions to ask, only when useful.

Lab inventories, vital signs, test technique and contrast, empty medication lists, charted background, superseded plans, and radiology boilerplate stay out. There is no "more details" or "already done" section.

Each thing is said once. Medical terms get plain words; a plain meaning is added only when the source states it, never from general medical knowledge.

On request, the skill returns the same verified content as structured JSON matching `schema/plan.schema.json`, including the verbatim evidence quotes behind each item. There is no glossary, HTML report, audit file, or run folder.

The skill must be explicitly invoked. Once selected, it runs the complete workflow and returns only the verified report. It does not summarize the source directly, skip verification, or show the internal draft.

## How It Works

The workflow is prompt-only and has two model passes:

1. **Read.** The host reads only the files `SKILL.md` names and the source text. It never opens, lists, downloads, or unpacks other plugin files.
2. **Write.** Following `stages/write.md` and `reference/style_rules.md`, the model fills the fixed report slots. Every visible item carries 1-3 short verbatim quotes from the source (internal, never shown). A must-keep checklist records whether each protected category (medication changes, follow-up, return precautions, diagnoses, disposition, abnormal or pending results) is shown or not in the source.
3. **Verify.** Following `stages/verify.md`, a checker reads only the source and the draft: a fresh sub-agent where the host has one (ChatGPT Work, Codex), otherwise a separate second pass in the same conversation (ChatGPT regular chat). It checks every quote is verbatim, every number matches its quote, nothing is interpreted or added from outside, must-keep content is complete, timing and reasons are kept, each thing is said once, privacy, clean text, item limits, and the 300-word budget. It fixes or removes items and adds only missing must-keep content that the source states. Verification runs exactly once and is never skipped; if a sub-agent fails, the second pass runs instead.
4. **Output.** The Markdown report is rendered only from the verified draft.

These checks were Python scripts in builds up to 0.1.5. Those scripts could not run in ChatGPT regular chat, so the checks are now explicit rules the model follows. The trade-offs are in [openai-plugin.md](openai-plugin.md#current-decision-prompt-only-simplify). Latency and token use are not benchmarked by the test suite; measure them on representative documents.

## Limitations

The plugin does not:

- diagnose a condition;
- recommend a new treatment;
- infer why a medicine was prescribed when the document does not say;
- replace a clinician, pharmacist, emergency service, or poison-control service;
- guarantee that source documents are complete or correct.

The report reflects only the supplied documents and preserves documented uncertainty. Unverified content is never shown. The checks are model-enforced rules rather than mechanical guarantees, so the report is a reading aid, not a replacement for the source documents or the care team.

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
Both packaged OpenAI manifests receive the same selected name and version. The generated package contains only the plugin
manifests and `skills/`. It contains no version ledger, MCP server, connection
declaration, repository tests, or internal documentation.
