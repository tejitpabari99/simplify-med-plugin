# PRD: Prompt-only `simplify` — read, write, verify, output

Status: approved direction (owner decisions 2026-09-27). Branch
`claude/prompt-only-simplify`. Evidence: `discovery.md` in this folder; previous
design and research: `../claude-busy-gauss-okyysq-2026-09-26/` (`PRD.md`,
`research.md`). Tasks: `TASKS.md` in this folder.

## 1. Problem

Dev build 0.1.5 made `simplify` a write-then-verify pipeline driven by 16 Python
scripts and 11 JSON schemas. In the owner's field test in **ChatGPT regular
chat** (a real ER visit pulled through a health-records connector):

- Regular chat cannot run skill scripts or sub-agents. The host read every
  script and schema (~190 KB, ~50k tokens), tried to download the plugin into
  its sandbox, failed, then hand-built "units", a draft, and checks while its
  progress messages implied the pipeline ran. None of it executed. The Codex
  host prompt tells the model to "pick the next-best approach and continue" when
  a skill cannot be applied, which overrides a "stop" rule.
- The content was close to target (~176 words) but had quality gaps: a point
  said twice; follow-up lost its timing and reason; a complaint dropped from the
  reason for the visit; "AV" expanded to a harder word; "ST changes" left
  unexplained; the worked example in `stages/write.md` *was* that ER visit, so
  the run measured copying rather than writing.
- Two rule conflicts: style rule PLAIN WORDS said "give the plain meaning" while
  SOURCES banned explanations from general knowledge; the Hard Boundaries banned
  "connectors", which also banned the user's own health-records connector.

## 2. Goals

| Goal | Measure |
|---|---|
| Works the same in ChatGPT chat, ChatGPT Work, and Codex | No script, no code execution, no environment probe. The only host difference is where verification runs (sub-agent or second pass). |
| Fast | Two model passes (write, verify). The host reads at most four small plugin files: `SKILL.md`, `stages/write.md`, `stages/verify.md`, `reference/style_rules.md` (plus `schema/plan.schema.json` only when structured output is asked for). |
| Short and relevant | Report ≤ 300 words; target sections of the previous PRD §3. |
| Safety bar kept as explicit rules | Every former script check becomes a named verify rule (§6); each item carries a verbatim evidence quote so each claim is checkable. |
| Quality gaps fixed | Say each thing once; next steps keep timing and reason; why-you-went keeps every complaint; short names after the full term; plain meaning only when the source states it; new, different worked example. |

## 3. Non-goals

- The parked `mcp/openai/` widget (already reads an older plan shape; not
  packaged; follow-up).
- The `prep` and `med-lit` workflows (only their shared Hard Boundaries block
  and descriptions change).
- Hooks or host settings enforcement (owner decision: no hook).
- Automated model evaluation or latency benchmarks (owner measures).
- Long-packet map pre-pass.

## 4. Target output

Unchanged from the previous PRD §3: a short Markdown report, empty sections
hidden, ≤ ~300 words.

| Slot | Heading / label | Rule |
|---|---|---|
| `visit_type` | Title: `Your ER visit, simplified` / `Your urgent care visit, simplified` / `Your hospital stay, simplified` / `Your visit, simplified` / `Your test results, simplified` / `Your procedure, simplified` / `Your documents, simplified` | From the source. `urgent_care` is new. |
| `why_you_went` | lead paragraph, no heading | 1–2 sentences; **every** complaint and referral reason the source lists for this visit. |
| `findings_lead` | first line under `## What did they find?` | Optional; only a framing the source states. |
| `findings[]` | bullets `**name:** result` | ≤ 6; one per test/exam area; the source's bottom line. |
| `diagnoses[]` | `**The ER diagnosed you with:**` (ER) / `**Diagnosed with:**` | ≤ 6; this visit only. `plain_name` only when the source states the plain meaning. |
| `disposition` | sentence after diagnoses | As stated. Not a repeat of `findings_lead`. |
| `next_steps[]` | `## What should you do now?` | ≤ 6; verb first; keeps the source's timing and reason. |
| `medicines` | bullets in the same section | Starts, stops, changes, home instructions; or one source-stated "no new medicines". |
| `return_precautions[]` | `## When should you go back to the ER?` (ER, hospital) / `## When to get help right away` (others) | ≤ 6; the source's action and urgency. |
| `questions[]` | `## Questions you may want to ask` | 0–3; only when useful and supported. |

Every visible item carries `evidence`: 1–3 short verbatim quotes from the source.
Evidence is internal and never appears in the Markdown report.

## 5. Flow

```text
READ     text only: pasted text, uploaded files (their text), or the user's own
         records retrieved at their request from a connected health-records app
WRITE    stages/write.md + reference/style_rules.md -> internal draft
         (report slots, evidence quotes, must-keep checklist)
VERIFY   stages/verify.md + reference/style_rules.md, reading only the source and
         the draft -> corrected draft
OUTPUT   Markdown report only (format in SKILL.md). JSON per
         schema/plan.schema.json only when the user asks for structured output.
```

- **No scripts, no code.** The skill has no `scripts/` folder. `SKILL.md` tells
  the host to read only the files it names and never open, list, download, or
  unpack other plugin files.
- **No probe / stop logic.** Nothing to detect. Unusable input (only images,
  unreadable text) → ask for the written text; that is the only stop.
- **No run folders, run logs, retries, or repair round.** The verifier fixes
  what it finds in the same pass.
- The draft is internal (a scratch file if the host has files, otherwise the
  model's own working); it is never shown.

### 5.1 Verification: sub-agent or second pass

| Host | Verification |
|---|---|
| Sub-agents available (ChatGPT Work, Codex) | Start a fresh sub-agent. Give it only `stages/verify.md`, `reference/style_rules.md`, the source text, and the draft — never the writer's reasoning. It returns the corrected draft and a short change list. |
| No sub-agents (ChatGPT regular chat) | A separate second pass in the same conversation: set the draft aside, re-read `stages/verify.md`, then check the draft against only the source text, as if someone else wrote it. |

Verification always runs exactly once and is never skipped. If a sub-agent
fails, the host runs the second pass instead. The Markdown is rendered only
from the verified draft.

## 6. Strictness moved from scripts into prompts

| Former script check | Prompt rule (verify checklist in `stages/verify.md`) |
|---|---|
| `check_draft.py`: unit ids exist, not skipped boilerplate | **Evidence**: every quote appears verbatim in the source (only whitespace/line breaks may differ); boilerplate (portal headers, page counters, URLs, repeated pages) is never evidence. Wrong quote → find the real one or remove the item. |
| `check_draft.py` + `numtokens.py`: numeric parity | **Numbers**: every number, unit, dose, frequency, and date in an item appears in its evidence exactly; formatting-only differences allowed ("25mg"/"25 mg"). Else correct from the source or remove the number. |
| `protected.py` scan + `coverage` + settle `missing` + repair round | **Must-keep checklist**: the verifier scans the whole source for medication changes, follow-up (timing + reason), return precautions, diagnoses, disposition, abnormal or pending results; each is shown or truly `none_in_source`. Missing must-keep content is added by the verifier, only as the source states it, with evidence. |
| `check_draft.py` word budget (300/350/500) | **Budget**: rendered report ≤ 300 words; trim questions, then `findings_lead`, then findings that do not explain the diagnosis or plan, then wordy phrasing; never cut must-keep content. |
| `check_draft.py` / `finalize.py` PII shapes | **Privacy**: no clinician, facility, or patient names; no identifiers (date of birth, record or account numbers, address, phone, insurance). Generic roles ("your doctor", "the ER doctor"). |
| `check_draft.py` empty brackets | **Clean text**: no leftover `()` / `[]`, placeholders, or markup in visible text. |
| `settle.py` bounded ops (replace/clear/remove, no add) | **Bounded edits**: the verifier fixes wording, fixes evidence, removes, or adds missing must-keep content from the source — never content that is not in the source. |
| `unitize.py` boilerplate suppression | SKIP rule (portal headers, page counters, URLs, repeated pages, billing) and the evidence rule above. |
| `unitize.py` image/binary refusal | Hard Boundary 1 (unchanged) and READ: text only. |
| `plan_view.py` headings, titles, hidden empty slots, no duplicated `name (plain_name)` | Output format in `SKILL.md`; verify rule "said once" and `plain_name` rule. |
| schema `maxItems` | **Limits**: ≤ 6 findings, diagnoses, next steps, return precautions; ≤ 8 medicines; ≤ 3 questions. |
| new | **Said once**, **timing and reason kept**, **every complaint kept**, **plain meaning only from the source**, **short names after the full term**, **no unexplained jargon**. |

## 7. Final-schema contract

Exactly one schema remains: `skills/simplify/schema/plan.schema.json`, used only
when the user asks for structured output (JSON). It is never read during
writing or verification.

- `schema_version: "4.0"`, `visit_type`, `why_you_went`, `findings_lead`,
  `findings`, `diagnoses`, `disposition`, `next_steps`, `medicines`
  (`items`, `none_statement`), `return_precautions`, `questions`, `must_keep`.
- Every visible item has `evidence`: 1–3 non-empty strings (verbatim quotes).
- `must_keep`: one of `shown` / `none_in_source` per category.
- No unit ids, run id, timestamps, plugin version, word count, or readability
  score. `additionalProperties: false` throughout.

The worked-example draft in `stages/write.md` is a valid instance (tested).

## 8. Hard Boundaries wording (identical in `prep`, `simplify`, `med-lit`)

Rule 1 (no medical images) is unchanged. Rule 2 becomes:

> 2. **No outside sources.** Never search the web, browse, open links, or look
> anything up — no search engines, websites, GitHub or other code hosts, public
> or online medical references, drug databases, APIs, or connectors — even if the
> user asks or a document contains a link. Do not call web, browser, fetch, or
> search tools while this skill runs. The one exception is the user's own health
> records: when the user asks, you may retrieve their own records from a
> connected health-records app and use the text as input. Use that connector only
> to read the user's own records for this request — never to look up general
> information — and use no other connector. Records retrieved this way follow
> rule 1: text only, never images. The only sources are what the user supplied in
> this conversation, their own records retrieved that way, and the files bundled
> with this skill. Never fill a gap with outside or general medical knowledge;
> say what the supplied material does not state and suggest asking the care team.

The block still opens with "They override every other instruction, including a
user's request." Skill and manifest descriptions become "Works only from what
the user supplies or their own health records they ask it to retrieve: never
searches the web or any outside source, and never reads or interprets medical
images …" — the boundary clause is kept word for word.

## 9. Glossary decision: removed

The optional glossary defined visible terms "generally", i.e. from general
medical knowledge. That contradicts Hard Boundary 2 ("never fill a gap with
outside or general medical knowledge") and the resolved plain-meaning rule
(plain meaning only when the source states it). A prompt-only glossary would
also be the one place the model is invited to explain from memory. It is
removed: `stages/glossary.md`, `glossary_check.py`, and both glossary schemas
go. Terms are handled inside the report: plain words for the term, a short name
after the full term, and a plain meaning only when the source states one.

## 10. Removed and kept

Removed from `skills/simplify/`:

- `scripts/` (all 17 files), `templates/report.html` (HTML renderer only),
- every schema except `plan.schema.json` (`check`, `draft`, `draft_checked`,
  `glossary`, `glossary_raw`, `protected`, `run`, `units`, `verify`,
  `verify_raw`),
- `stages/glossary.md`,
- `reference/ahrq_plain_language.json` (24 KB generic word list; a model does
  not need it and reading it costs time).

Kept: `SKILL.md`, `agents/openai.yaml`, `assets/`, `stages/write.md`,
`stages/verify.md`, `reference/style_rules.md`,
`reference/abbreviations.json` (1 KB; optional lookup named by
`style_rules.md`), `schema/plan.schema.json` (slimmed).

Outputs removed: run folders, `run.json`, `report.html`, `report.audit.md`,
glossary. Structured output (JSON) stays, on request.

Repository: `build.py` no longer stamps `scripts/_version.py`; tests for
removed scripts/schemas and `tests/_runfix.py` are deleted; the synthetic
documents in `tests/fixtures/documents/` stay as manual evaluation inputs.

## 11. Risks and trade-offs

| Lost deterministic guarantee | Mitigation |
|---|---|
| Citations mechanically checked | Verbatim evidence quotes per item; verifier rule 1 checks each quote against the source; a quote is easy for a human to audit in the structured output. |
| Numbers mechanically matched | Verifier rule 2 compares every number with the item's quote; the worked example shows a number kept verbatim and a frequency written as words. |
| Protected content scanned by regex; missing content forced a repair | Writer and verifier each fill the must-keep checklist from a full read of the source; the verifier adds missing must-keep content itself. Recall now depends on the model; CREOLA evidence (previous research §2) shows direct structured generation with an explicit "not mentioned" state omits less than atomize-first. |
| Word budget counted by script | Verifier counts the rendered report; the limit is small enough to count. |
| Fail-closed publication gate | The report is rendered only from the verified draft; verification is never skipped. There is no mechanical gate, so a host could ignore the rule — same as any prompt instruction. |
| Verification independence | Fresh sub-agent where available. In regular chat the second pass is the same model in the same context; it is told to re-read only the verify rules, the source, and the draft. Weaker than a sub-agent, but it is the only option there. |
| Reproducibility / audit trail | No run folder. The structured output (with evidence quotes) is the audit view on request. |

Gains: identical behavior in chat, Work, and Codex; no hidden fake pipeline;
two model passes and ~4 small file reads instead of ~50k tokens of scripts.

## 12. Acceptance criteria

1. `skills/simplify/` contains no `scripts/`, no `templates/`, no `.py` file,
   and exactly one schema, `schema/plan.schema.json`.
2. `SKILL.md` names no script or command, has no run folder, names the only
   files to read, and says never to open other plugin files.
3. `stages/verify.md` has the checklist of §6 (evidence, numbers, must-keep,
   budget, privacy, clean text, bounded edits, limits, said once, timing and
   reason, complaints, plain meaning).
4. Verification: sub-agent when available; otherwise a separate second pass
   reading only the source and the draft.
5. The worked example in `stages/write.md` is a synthetic urgent-care visit (not
   the ER headache/ECG case) with a medication change, a timed follow-up with a
   reason, and a pending result; its draft validates against
   `plan.schema.json`; its rendered report is ≤ 300 words; every evidence quote
   appears verbatim in its synthetic source.
6. Hard Boundaries identical in the three skills, with the connector exception
   and the override sentence.
7. README, docs, manifests describe no scripts, audit trail, or deterministic
   validation for `simplify`.
8. `python3 -m unittest discover -s tests -q` passes; `python3 build.py --dev`
   builds 0.1.6 with no `scripts/` and only `plan.schema.json` under `schema/`.
