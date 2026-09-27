# simplify-med

An OpenAI plugin with three patient-facing skills:

- **`prep`** — before a visit: capture the appointment's stated requirements, the patient's prioritized concerns, a things-to-bring checklist, and questions to ask.
- **`simplify`** — after a visit: turn supplied clinical documents into a short, plain-language report in which every statement is backed by a short quote from the source and checked in a separate verification pass.
- **`med-lit`** — for each person: an opt-in, brief health-literacy screen (BHLS) plus self-reported support needs, returned as a basic profile.

All three skills are instruction-only: no scripts, no code execution, and no run folders. They behave the same in ChatGPT chat, ChatGPT Work, and Codex.

## Plugin Structure

The repository root is the plugin folder OpenAI uses:

```text
plugin.json                    portable Agent Plugins manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build-versions.json            repository-only prod/dev version counters
skills/prep/
  SKILL.md                     pre-visit workflow and safety boundaries
  agents/openai.yaml           OpenAI skill metadata
  assets/                      skill icons
  references/                  concern prompts, question bank, brief template
skills/med-lit/
  SKILL.md                     screening workflow and safety boundaries
  agents/openai.yaml           OpenAI skill metadata
  assets/                      skill icons
  references/                  BHLS items and scoring, support needs, profile template
skills/simplify/
  SKILL.md                     workflow and safety boundaries
  agents/openai.yaml           OpenAI skill metadata
  assets/                      skill icons
  stages/                      write.md and verify.md instructions
  reference/                   style rules and an optional abbreviation list
  schema/                      plan.schema.json, used only for structured output
```

`mcp/openai/` remains in the repository for possible future work. It is parked: not connected to the plugin, not declared by either manifest, not included in the ZIP, and not yet updated to the current plan shape.

## What `simplify` Does

`simplify` is prompt-only. The host reads only the files `SKILL.md` names (`SKILL.md`, `stages/write.md`, `stages/verify.md`, `reference/style_rules.md`, optionally `reference/abbreviations.json`, and `schema/plan.schema.json` only when structured output is requested) and never opens other plugin files. There are no scripts, run folders, run logs, repair rounds, audit trail, HTML report, or glossary.

```text
READ     text only: pasted text, uploaded files (their text), or the user's own
         records retrieved at their request from a connected health-records app
WRITE    stages/write.md -> internal draft: fixed report slots, 1-3 verbatim
         evidence quotes per item, and a must-keep checklist
VERIFY   stages/verify.md, reading only the source and the draft -> corrected draft
OUTPUT   the short Markdown report; JSON per schema/plan.schema.json only on request
```

1. **Read.** Only text. If the input is only images or unreadable text, the skill asks for the written text; that is its only stop.
2. **Write.** One model pass fills the report slots. Every visible item carries 1-3 short verbatim quotes from the source as internal evidence (never shown), and a must-keep checklist records whether each protected category is shown or not in the source: medication changes, follow-up, return precautions, diagnoses, disposition, and abnormal or pending results.
3. **Verify.** Exactly once, never skipped. Where the host has sub-agents (ChatGPT Work, Codex), a fresh sub-agent gets only `stages/verify.md`, the style rules, the source, and the draft. In ChatGPT regular chat, a separate second pass sets the draft aside and re-checks it against only the source. The verifier checks every quote and number against the source, the must-keep checklist, the 300-word budget, privacy, and wording; it fixes or removes items and may add only missing must-keep content the source states. It never adds content that is not in the source.
4. **Output.** Only the verified short Markdown report. The draft and the verifier's change list stay internal.

The report targets at most about 300 words and answers four questions: what happened, what did they find, what do I do now, and when do I come back. It shows a title by visit type, why you went (every complaint listed), one bottom-line bullet per test area, the diagnoses and disposition stated for this visit, next steps with their timing and reason, medicine changes (or a source-stated "no new medicines"), return precautions, and up to three questions. Empty sections are hidden. Lab inventories, vital signs, test technique, empty medication lists, charted background, and radiology boilerplate stay out.

Earlier builds (up to 0.1.5) used Python scripts for these checks. They could not run in ChatGPT regular chat, so the checks now live in the verify instructions as explicit rules. See `docs/architecture.md` for the rule list and `docs/openai-plugin.md` for the trade-offs.

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
- update `plugin.json` and `.codex-plugin/plugin.json` in the source tree;
- write `dist/simplify-med-<version>-openai.zip`.

Development builds:

- package `simplify-med-dev`;
- stamp the dev name and version into both packaged manifests;
- leave the production manifests in the source tree unchanged;
- write `dist/simplify-med-dev-<version>-openai.zip`.

The version ledger is repository-only and is never included in either archive. The builder no longer stamps a pipeline version into the skill; the two manifests are the only versioned files.

Use a different output directory with:

```bash
python3 build.py --out /path/to/output
python3 build.py --dev --out /path/to/output
```

The builder uses an allowlist. The ZIP contains only:

- `plugin.json`
- `.codex-plugin/plugin.json`
- `skills/`

It excludes `build-versions.json`, `mcp/`, `docs/`, `tests/`, repository metadata, caches, and the builder itself.

## Use in OpenAI

Install or import the generated ZIP as an OpenAI plugin. The plugin exposes the `prep`, `simplify`, and `med-lit` skills and requires no MCP server, connector, endpoint, API key, or separate deployment.

### `prep`

Ask for help getting ready for an appointment (implicit invocation is allowed). Optionally share the appointment message, referral, or preparation sheet. The skill asks a few optional questions, then returns an editable Markdown visit brief: appointment details, ordered priorities in the patient's words, clinic-stated preparation steps and items to confirm, a required-versus-optional things-to-bring checklist, and 3–5 prioritized questions. It never invents preparation requirements, diagnoses, or triage advice, and it keeps clinic instructions, patient statements, and generated suggestions visibly separate.

### `med-lit`

Explicitly invoke `med-lit` (implicit invocation is disabled because the screen is opt-in). It administers the three-item Brief Health Literacy Screen verbatim, scores it 3–15 only when all items are answered, asks optional support-needs and preference questions, and returns a Markdown profile plus a structured JSON block. It never infers literacy from conversation, never emits a universal low/medium/high level, and states that published cutoffs may not apply to chat administration. Wiring the profile into other skills is deferred.

### `simplify`

Explicitly invoke the `simplify` skill for a visit note, discharge summary, lab report, imaging report, or similar clinical document. Implicit invocation is disabled so this medical workflow does not activate accidentally. Paste the text, upload text documents, or ask the skill to retrieve your own records from a connected health-records app.

Explicit invocation requires the complete workflow: the skill must not answer with a direct summary, skip verification, or show the draft. The default output is the verified Markdown report only. Ask for structured output to get the same report as JSON matching `schema/plan.schema.json`, including each item's evidence quotes.

## Safety Boundary

- The plugin explains supplied records and helps patients prepare; it does not diagnose, prescribe, or triage.
- **No medical images (all skills).** The plugin never opens or interprets X-ray, CT, MRI, ultrasound, ECG-tracing, pathology, or body/skin images. Written reports and photos or scans of text documents (transcribed as text) are fine.
- **No outside sources (all skills).** The plugin never searches the web, opens links, or uses GitHub, websites, online references, drug databases, APIs, or connectors, even if the user asks. The one exception: when the user asks, it may retrieve the user's own records from a connected health-records app and use their text as input — never to look up general information, and no other connector. Otherwise it uses only what the patient supplied and the files bundled with each skill. Each `SKILL.md` carries the same `Hard Boundaries` block, checked by `tests/test_boundaries.py`.
- The plugin cannot switch off the host's web search itself. For the strongest guarantee in Codex, set `web_search = "disabled"` in `~/.codex/config.toml` (admins: `allowed_web_search_modes = ["disabled"]`); see `docs/openai-plugin.md`.
- `prep` uses only patient statements and supplied appointment materials; `med-lit` scores only the patient's answers to the screen.
- Every visible statement carries a verbatim evidence quote from the source, and the verifier checks it.
- Missing information stays missing rather than being guessed or filled from general medical knowledge.
- Every number, unit, dose, and date is checked against the item's evidence quote.
- Protected content (medication changes, follow-up, return precautions, diagnoses, disposition, abnormal or pending results) is shown or confirmed absent from the source.
- Unverified content is never shown. These are model-enforced rules, not mechanical checks.
- The result is a reading aid, not a replacement for clinical or emergency care.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

When the OpenAI plugin and skill validators are available in your development
environment, run them against `.`, `skills/prep`, `skills/simplify`, and `skills/med-lit` before distribution.
Run `build.py` only when you intend to consume the next production or development version.

## Documentation

- `docs/openai-plugin.md` — defining rules for manifests, skill creation, resources, scripts, and future skills, and the prompt-only decision for `simplify`.
- `docs/architecture.md` — the prompt-only `simplify` flow and the verification rules.
- `docs/overview.md` — user-facing behavior, inputs, outputs, and limitations.
- `docs/openai.md` — the current skills-only OpenAI package and archive boundary.
