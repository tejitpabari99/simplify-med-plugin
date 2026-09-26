# simplify-med

An OpenAI plugin with three patient-facing skills:

- **`prep`** — before a visit: capture the appointment's stated requirements, the patient's prioritized concerns, a things-to-bring checklist, and questions to ask.
- **`simplify`** — after a visit: turn supplied clinical documents into a short, plain-language report in which every statement cites the source and is independently verified.
- **`med-lit`** — for each person: an opt-in, brief health-literacy screen (BHLS) plus self-reported support needs, returned as a basic profile.

`prep` and `med-lit` are instruction-only skills (no scripts) with basic Markdown output.

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
  stages/                      language-stage instructions
  scripts/                     deterministic checks and renderers
  schema/                      structured-data contracts
  reference/                   medical plain-language rules and dictionaries
  templates/                   report template
```

`mcp/openai/` remains in the repository for possible future work. It is parked: not connected to the plugin, not declared by either manifest, not included in the ZIP, and not yet updated to the current plan shape.

## What `simplify` Does

1. Numbers every source line as a unit, drops portal boilerplate (URL-only lines, page counters, exact repeats), and flags candidate lines for six protected categories: medication changes, follow-up, return precautions, diagnoses, disposition, and abnormal or pending results.
2. Writes the short report in one model call, directly from the numbered source. Every visible item cites the source units that support it.
3. Checks the draft with a script: schema, valid citations, word budget, numbers that do not appear in the cited units, and protected candidates that no item cites.
4. Verifies every visible item in a second, independent model call against the original source, returning only bounded edits (replace, clear, remove), numeric-flag resolutions, and a decision for each uncited protected candidate.
5. Applies those edits exactly with a script. If the verifier marks protected content as missing, the writer gets one repair round, which is checked and verified again.
6. Finalizes only after every step passes, then renders `report.md`.

The report targets 150-300 words and answers four questions: what happened, what did they find, what do I do now, and when do I come back. It shows one bottom-line bullet per test area, the diagnoses and disposition stated for this visit, next steps, medicine changes (or a source-stated "no new medicines"), and return precautions. Lab inventories, vital signs, test technique, empty medication lists, charted background, and radiology boilerplate stay out.

The model has two core responsibilities: writing the draft and independently verifying it. Python owns the deterministic work: unitizing, protected-candidate scanning, schema and citation checks, numeric parity, exact settlement, audit logging, rendering, and fail-closed finalization. See `docs/openai-plugin.md` for the governing authoring rules and the per-script rationale.

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

It excludes `build-versions.json`, `mcp/`, `docs/`, `tests/`, repository metadata, caches, and the builder itself.

## Use in OpenAI

Install or import the generated ZIP as an OpenAI plugin. The plugin exposes the `prep`, `simplify`, and `med-lit` skills and requires no MCP server, connector, endpoint, API key, or separate deployment.

### `prep`

Ask for help getting ready for an appointment (implicit invocation is allowed). Optionally share the appointment message, referral, or preparation sheet. The skill asks a few optional questions, then returns an editable Markdown visit brief: appointment details, ordered priorities in the patient's words, clinic-stated preparation steps and items to confirm, a required-versus-optional things-to-bring checklist, and 3–5 prioritized questions. It never invents preparation requirements, diagnoses, or triage advice, and it keeps clinic instructions, patient statements, and generated suggestions visibly separate.

### `med-lit`

Explicitly invoke `med-lit` (implicit invocation is disabled because the screen is opt-in). It administers the three-item Brief Health Literacy Screen verbatim, scores it 3–15 only when all items are answered, asks optional support-needs and preference questions, and returns a Markdown profile plus a structured JSON block. It never infers literacy from conversation, never emits a universal low/medium/high level, and states that published cutoffs may not apply to chat administration. Wiring the profile into other skills is deferred.

### `simplify`


Explicitly invoke the `simplify` skill for a visit note, discharge summary, lab report, imaging report, or similar clinical document. Implicit invocation is disabled so this relatively expensive medical workflow does not activate accidentally. Input text should be extracted to UTF-8 `.txt`; page boundaries may be represented with form-feed characters (`\f`).

Explicit invocation requires the complete workflow. The skill must not return a direct, ad hoc simplification or expose clinical content before fail-closed finalization succeeds. The only default clinical output is the validated `report.md`; the host must not rewrite it into a second summary.

Each run writes `simplify-runs/<run-id>/` in the working directory. A clean run has two model calls and about a dozen artifacts: `run.json`, the numbered source and protected candidates, the draft and its check, the verification record, the settled plan, `05_plan.final.json`, and `report.md`. Glossary JSON, `report.html`, and `report.audit.md` are post-finalization outputs created only when requested.

Runs started under an earlier schema version cannot be resumed; start a fresh run.

## Safety Boundary

- The plugin explains supplied records and helps patients prepare; it does not diagnose, prescribe, or triage.
- `prep` uses only patient statements and supplied appointment materials; `med-lit` scores only the patient's answers to the screen.
- Every medical statement must be supported by the source documents.
- Missing information stays missing rather than being guessed.
- Numeric details are checked against the cited source units.
- Protected content (medication changes, follow-up, return precautions, diagnoses, disposition, abnormal or pending results) is shown or explicitly dismissed by the verifier.
- Missing, failed, degraded, stale, or invalid core stages prevent publication.
- The result is a reading aid, not a replacement for clinical or emergency care.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

When the OpenAI plugin and skill validators are available in your development
environment, run them against `.`, `skills/prep`, `skills/simplify`, and `skills/med-lit` before distribution.
Run `build.py` only when you intend to consume the next production or development version.

## Documentation

- `docs/openai-plugin.md` — defining rules for manifests, skill creation, resources, scripts, and future skills.
- `docs/architecture.md` — the medical transformation pipeline and deterministic safeguards.
- `docs/overview.md` — user-facing behavior, inputs, outputs, and limitations.
- `docs/openai.md` — the current skills-only OpenAI package and archive boundary.
