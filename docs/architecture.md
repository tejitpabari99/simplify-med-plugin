# simplify-med — architecture

This document describes the prompt-only `simplify` workflow: its execution
contract, two model passes, the verify rules that replaced the former Python
checks, the final schema, and the package contents. Read
[overview.md](overview.md) first for the patient-facing behavior. The design
rationale and evidence are in
`agent_files/claude-prompt-only-simplify-2026-09-27/` (`discovery.md`,
`PRD.md`); the earlier write-then-verify design is in
`agent_files/claude-busy-gauss-okyysq-2026-09-26/`.

## Why prompt-only

Builds up to 0.1.5 ran `simplify` as a script pipeline. In a field test in
ChatGPT regular chat, which cannot run skill scripts or sub-agents, the host
read every script and schema (about 50k tokens), could not run them, and
hand-built an imitation of the pipeline while its progress messages implied the
scripts had run. The checks those scripts performed now live in
`stages/verify.md` as explicit rules, so the skill behaves the same in ChatGPT
regular chat, ChatGPT Work, and Codex. The only host difference is where
verification runs.

## Principles

- **Explicit invocation.** The `simplify` skill is not implicitly invoked.
  Once selected, it runs the complete workflow rather than answering with an
  ad hoc summary.
- **Instructions only.** No scripts, no code execution, no environment probe,
  no run folders or run logs. The host reads only the files `SKILL.md` names and
  never opens, lists, searches, downloads, or unpacks other plugin files.
- **Write the short report, then verify what is shown.** The work scales with
  the report, not with the chart.
- **Quote, don't cite ids.** Every visible item carries 1-3 short verbatim
  evidence quotes from the source, so each claim is checkable by the verifier
  and, in structured output, by a human.
- **Protected content is never silently dropped.** Writer and verifier each
  fill a must-keep checklist from a full read of the source.
- **Separate verification.** A fresh sub-agent where available, otherwise a
  separate second pass. Exactly once, never skipped.
- **Fail closed.** The report is rendered only from the verified draft. The
  draft is never shown, and unverified content is never shown.

## Repository layout

```text
plugin.json                    portable OpenAI plugin manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build.py                       allowlist-based OpenAI ZIP builder
build-versions.json            repository-only prod/dev version counters
skills/prep/                   pre-visit skill (instruction-only)
skills/med-lit/                health-literacy screen (instruction-only)
skills/simplify/
  SKILL.md                     invocation contract, boundaries, flow, output format
  agents/openai.yaml           UI metadata and explicit-invocation policy
  assets/                      icon-large.png, icon-small.svg
  stages/write.md              writer instructions, must-keep checklist, worked example
  stages/verify.md             verifier checklist and allowed edits
  reference/style_rules.md     SOURCES, PII, NUMERACY, LANGUAGE RULES, PLAIN WORDS, SHOW, SKIP
  reference/abbreviations.json optional abbreviation lookup
  schema/plan.schema.json      final schema, used only for structured output
mcp/openai/                    parked widget; excluded from ZIP; not yet
                               updated to the current plan shape
tests/                         prompt/contract and package tests
docs/                          documentation and design history
```

The distributable ZIP contains only `plugin.json`,
`.codex-plugin/plugin.json`, and `skills/`.

## Flow

```text
READ     text only: pasted text, uploaded files (their text), or the user's own
         records retrieved at their request from a connected health-records app
WRITE    stages/write.md + reference/style_rules.md -> internal draft
         (report slots, evidence quotes, must-keep checklist)
VERIFY   stages/verify.md + reference/style_rules.md, reading only the source and
         the draft -> corrected draft + short change list (internal)
OUTPUT   Markdown report only (format in SKILL.md). JSON per
         schema/plan.schema.json only when the user asks for structured output.
```

Unusable input (only images, or unreadable text) is the only stop: the skill
asks for the written text. There are no retries and no repair round; the
verifier fixes what it finds in the same pass. The draft is internal: a scratch
file if the host has files, otherwise the model's own working.

### Read

Only text. Medical images are never opened or interpreted (Hard Boundary 1).
The user's own health-records connector may be used, on the user's request, to
retrieve their records as text (Hard Boundary 2's single exception). No web,
public sources, or other connectors.

### Write

`stages/write.md` fills fixed slots: `visit_type`, `why_you_went`,
`findings_lead`, `findings[]` (one bottom-line bullet per test or exam area),
`diagnoses[]`, `disposition`, `next_steps[]`, `medicines` (changes or a
source-stated none-statement), `return_precautions[]`, `questions[]`, and
`must_keep` (`shown` or `none_in_source` for medication changes, follow-up,
return precautions, diagnoses, disposition, and abnormal or pending results).
Every visible item has `evidence`: 1-3 short verbatim quotes. The stage carries
the SHOW/SKIP selection rules, the anti-patterns seen in real runs (a point
said twice, follow-up without timing or reason, a dropped complaint), and a
synthetic urgent-care worked example.

### Verify

Where verification runs:

| Host | Verification |
|---|---|
| Sub-agents available (ChatGPT Work, Codex) | A fresh sub-agent gets only `stages/verify.md`, `reference/style_rules.md`, the source text, and the draft — never the writer's reasoning. It returns the corrected draft and a short change list. |
| No sub-agents (ChatGPT regular chat) | A separate second pass in the same conversation: set the draft aside, re-read `stages/verify.md`, then check the draft against only the source text, as if someone else wrote it. |

Verification runs exactly once and is never skipped. If a sub-agent fails, the
host runs the second pass instead.

### Output

The Markdown report is rendered from the verified draft. Titles by
`visit_type`: "Your ER visit, simplified", "Your urgent care visit,
simplified", "Your hospital stay, simplified", "Your visit, simplified", "Your
test results, simplified", "Your procedure, simplified", "Your documents,
simplified". Headings: "What did they find?", "What should you do now?", "When
should you go back to the ER?" (ER visit, hospital stay) or "When to get help
right away" (others), "Questions you may want to ask". Diagnoses use "The ER
diagnosed you with:" (ER visit) or "Diagnosed with:". Order: why you went,
findings lead, findings, diagnoses, disposition, next steps, medicines,
none-statement, return precautions, questions. Empty slots and their headings
are hidden. Evidence quotes never appear in the Markdown.

## Strictness moved from scripts into prompts

Every check the former scripts performed is now a named rule in the verify
checklist in `stages/verify.md`.

| Former script check (removed) | Verify rule |
|---|---|
| unit ids exist and are not skipped boilerplate | **Evidence**: every quote appears verbatim in the source (only whitespace/line breaks may differ); boilerplate (portal headers, page counters, URLs, repeated pages) is never evidence. Wrong quote: find the real one or remove the item. |
| numeric parity | **Numbers**: every number, unit, dose, frequency, and date in an item appears in its evidence exactly; formatting-only differences allowed ("25mg"/"25 mg"). Else correct from the source or remove the number. |
| protected-content scan, coverage, and repair round | **Must-keep checklist**: the verifier scans the whole source for medication changes, follow-up (timing + reason), return precautions, diagnoses, disposition, abnormal or pending results; each is shown or truly `none_in_source`. Missing must-keep content is added by the verifier, only as the source states it, with evidence. |
| word budget | **Budget**: rendered report ≤ 300 words; trim questions, then `findings_lead`, then findings that do not explain the diagnosis or plan, then wordy phrasing; never cut must-keep content. |
| PII shapes | **Privacy**: no clinician, facility, or patient names; no identifiers (date of birth, record or account numbers, address, phone, insurance). Generic roles ("your doctor", "the ER doctor"). |
| empty brackets | **Clean text**: no leftover `()` / `[]`, placeholders, or markup in visible text. |
| bounded settlement operations | **Bounded edits**: the verifier fixes wording, fixes evidence, removes, or adds missing must-keep content from the source — never content that is not in the source. |
| boilerplate suppression | SKIP rule (portal headers, page counters, URLs, repeated pages, billing) and the evidence rule above. |
| image and binary refusal | Hard Boundary 1 and READ: text only. |
| rendered headings, titles, hidden empty slots | Output format in `SKILL.md`; "said once" and `plain_name` rules. |
| schema item limits | **Limits**: ≤ 6 findings, diagnoses, next steps, return precautions; ≤ 8 medicines; ≤ 3 questions. |
| new | **Said once**, **timing and reason kept**, **every complaint kept**, **plain meaning only from the source**, **short names after the full term**, **no unexplained jargon**. |

The verifier also checks fidelity: negation, uncertainty, attribution, and
current versus old history, and it clears any `plain_name` the source does not
state.

## Final schema

`skills/simplify/schema/plan.schema.json` is the only schema. It is read only
when the user asks for structured output, never during writing or
verification. `schema_version` is `"4.0"`; top-level keys are
`schema_version`, `visit_type`, `why_you_went`, `findings_lead`, `findings`,
`diagnoses`, `disposition`, `next_steps`, `medicines`, `return_precautions`,
`questions`, and `must_keep`. Every visible item has `evidence` (1-3 non-empty
verbatim quotes). There are no unit ids, run id, timestamps, plugin version,
word count, or readability score, and `additionalProperties` is `false`
throughout. The worked-example draft in `stages/write.md` is a valid instance.

## Trade-offs

Deterministic guarantees became model-enforced rules. Mitigations: verbatim
evidence quotes make each claim checkable; verification is a separate pass,
independent where a sub-agent exists; the report is rendered only from the
verified draft. There is no run folder or audit file; the structured output
(with evidence quotes) is the audit view on request. See
[openai-plugin.md](openai-plugin.md#current-decision-prompt-only-simplify) for
the full list.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

The suite checks prompt and package contracts: the skill file set, the final
schema and a small validator, the worked example (valid against the schema,
under the word budget, evidence verbatim in its synthetic source), the verify
checklist terms, identical Hard Boundaries across the three skills, identical
default prompts and manifest interfaces, and the ZIP contents. It cannot test
model behavior; the synthetic documents in `tests/fixtures/documents/` are
inputs for manual evaluation. Latency and token use are not benchmarked.

## Known gaps

- The parked `mcp/openai/` widget still reads an older plan shape.
- In regular chat, the second pass is the same model in the same context;
  weaker independence than a sub-agent.
- Very long packets that exceed one model call's context need a map pre-pass
  (not implemented).
