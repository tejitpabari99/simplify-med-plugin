# PRD: Lean `simplify` — write the short report, then verify what is shown

Status: approved direction (2026-09-26). Branch `claude/busy-gauss-okyysq`.
Evidence: `research.md` in this folder. Tasks: `TASKS.md` in this folder.

## 1. Problem

Running `simplify` on one ER visit (headache, left-hand tingling, abnormal
urgent-care ECG; CT/CTA and brain MRI normal; discharged with PCP follow-up)
produced a ~1,200-word report and took far too long. Everything shown was
grounded, but most of it was noise: every CT/MRI sub-finding, 30+ lab values,
two sets of vitals, contrast dye dose, three "no medications" rows, radiology
boilerplate turned into an appointment, and duplicate headings.

Root causes (details in `research.md` §1):

1. **Keyword veto** — `cite_check.py` only lets a fact be omitted when the fact's
   own text contains magic words, so concise drafts fail and nearly everything is
   forced visible. Main cause of verbosity *and* of retries.
2. **Work scales with the chart** — every statement becomes a quoted fact
   (~150–300 for an ER packet); assemble must disposition each one and review
   must re-judge each one, serially. Main cause of latency.
3. **Schema can't express the target** — no per-test bottom line, no
   disposition, no "no new medicines", every completed item lands in "Already
   done", no length budget.
4. **Review can only add, merging is forbidden, render bugs.**

## 2. Goals

| Goal | Measure (user will measure before/after) |
|---|---|
| Much faster | Clean path = **2 model calls** (write + verify), ~2–4k model output tokens, ≤ 4 script runs. Worst case = 8 model calls (one retry per stage per round, one repair round). |
| Short and relevant | Report targets **150–300 words**; warning above 350; hard fail above 500. No "more details" section. |
| Same safety bar where it matters | Every visible bullet cites source units; numbers/doses/units match cited units; negation and uncertainty preserved; protected content (below) is shown or explicitly declared absent; an independent verifier runs before release; fail closed. |

Non-goals: the parked `mcp/openai/` widget (not packaged; follow-up); the `prep`
and `med-lit` skills; a long-packet map pre-pass (deferred until a packet
exceeds a single call's context); automated latency benchmarking (the user
measures).

## 3. Target output

The user's reference output for the ER case is the acceptance target:

```markdown
# Your ER visit, simplified

You went to the ER because you had a headache for several days, neck pain,
tingling in your left hand, and an abnormal heart tracing at urgent care.

## What did they find?

The important tests were reassuring:

- **Brain MRI:** Normal. No stroke was seen.
- **CT and CT angiogram of your head and neck:** Normal. No blocked blood
  vessels, aneurysm, or artery tear was found.
- **Neurologic exam:** Normal except for slightly different sensation in your
  left palm.
- **Blood tests:** The ER doctor described them as unremarkable.
- **Heart tracing:** It showed a right bundle branch block and first-degree AV
  block, but the ER doctor did not think it showed a heart attack or other acute
  loss of blood flow to the heart.

**The ER diagnosed you with:**

- Acute headache
- Tingling in your left arm/hand

They did not find an emergency cause for your symptoms, and you were discharged
in stable condition.

## What should you do now?

- Schedule a primary-care appointment to follow up on the headache, hand
  tingling, and abnormal heart tracing.
- You were not prescribed any new medicines.

## When should you go back to the ER?

- Return to the ER if you develop any new or worsening symptoms.
```

Section rules:

| Slot | Heading / label | Rule |
|---|---|---|
| `visit_type` | Title: `Your ER visit, simplified` / `Your hospital stay, simplified` / `Your visit, simplified` / `Your test results, simplified` / `Your procedure, simplified` / `Your documents, simplified` | From the source; drives headings. |
| `why_you_went` | (lead paragraph, no heading) | 1–2 sentences. Complaint + referral reason. |
| `findings_lead` | first line under "What did they find?" | Optional. Only a framing the source supports (e.g., clinician calls results reassuring/unremarkable). |
| `findings[]` | `## What did they find?` bullets `**name:** result` | ≤ 6. One bullet per test or exam **area**, grouping sub-findings. `result` = the source's bottom line (radiology Impression, clinician assessment) in plain words. Numbers only when the number itself matters to the patient. |
| `diagnoses[]` | `**The ER diagnosed you with:**` (ER) / `**Diagnosed with:**` (other) | ≤ 6. Only diagnoses stated for this visit. Never old problem-list items. |
| `disposition` | sentence after diagnoses | Only as stated (discharged, admitted, stable condition, no emergency cause found). |
| `next_steps[]` | `## What should you do now?` | ≤ 6. Follow-up, tests to schedule, home instructions stated for this patient. Start with a verb. |
| `medicines` | bullets appended to "What should you do now?" | Starts, stops, dose changes, and home instructions only. If the source says no new medicines / none prescribed, one `none_statement`. Never list empty or unchanged medication lists. |
| `return_precautions[]` | `## When should you go back to the ER?` (ER/hospital) / `## When to get help right away` (other) | ≤ 6. The source's own action and urgency. |
| `questions[]` | `## Questions you may want to ask` | 0–3, only when useful and supported. |

Empty slots are hidden. There is no "more details", "already done", audit, or
inventory section in the patient report.

## 4. Pipeline

```text
UNITIZE      scripts/unitize.py            (script)
  -> WRITE   stages/write.md               (model call 1)
  -> CHECK   scripts/check_draft.py        (script)
  -> VERIFY  stages/verify.md              (model call 2, independent)
  -> SETTLE  scripts/settle.py             (script)
       exit 3 = repair requested -> one repair round (WRITE -> CHECK -> VERIFY -> SETTLE, --round 2)
  -> FINALIZE scripts/finalize.py          (script)  -> 05_plan.final.json + report.md
```

Retries: WRITE may be retried once when CHECK fails; VERIFY may be retried once
when SETTLE rejects the verification contract. One repair round at most. Any
second failure stops the run without clinical output. The host never falls back
to its own summary.

### 4.1 UNITIZE (`scripts/unitize.py`, modified)

- Same inputs/CLI as today (`--runs-dir`/`--run-dir`, `--input path[:ocr|:pasted]`).
- Numbers every non-blank line as a unit (unchanged `01_units.json` unit shape).
- **Boilerplate suppression**: a unit is marked `"skip": "<reason>"` (and left out
  of `01_source.txt`) when it is (a) a line that is only a URL, (b) a page
  counter like `Page 3 of 9`, or (c) an exact repeat (after whitespace
  normalization, ≥ 8 characters) of an earlier unit — repeated portal headers,
  footers, and duplicated pages. Only the first occurrence is kept. A repeated
  line that matches any protected-content pattern (§4.3) is never skipped, so
  two studies with the same impression both stay citable. Skipped units
  stay in `01_units.json` for audit and are never valid citations.
- Writes `01_source.txt`: every non-skipped unit as `[<id>] <text>`, with a
  `=== <file> page <n> ===` header line (not a unit) whenever file/page changes.
- Writes `01_protected.json` (see 4.3) using `scripts/protected.py`.
- Drops chunking (`chunks`, `01_units.<k>.txt`, `--chunk-size`).
- Prints `unitize: ok | files=N units=N skipped=N protected=N` then the run dir.
  The host never reads `01_units.json`.

### 4.2 WRITE (`stages/write.md`, model call 1)

Inputs: `01_source.txt`, `01_protected.json`, `reference/style_rules.md`,
`schema/draft.schema.json`. Output: `02_draft.raw.json` (round 2:
`02_draft.r2.raw.json`, plus `04_repair.json` as an extra input).

The writer reads the numbered source directly and fills the slots. Every visible
item carries `unit_ids` (≥ 1) — the units that support it. No quotes. It also
fills `coverage` for six protected categories: `status: "shown"` with the
`unit_ids` it relied on, or `status: "none_in_source"` with `unit_ids: []`.

Selection rules (prompt, not regex):

- Lead with the answer to "what happened / what did they find / what do I do /
  when do I come back".
- One bullet per test/exam area using the source's bottom line; group
  sub-findings; never list sub-findings, sequences, technique, contrast, doses
  of agents given during a test, reconstructions, criteria names, or duplicate
  records.
- Labs and vitals: only the clinician's summary word (e.g., "unremarkable") in
  one grouped bullet, or a specific value only when the clinician calls it out
  or it drives the plan.
- Medicines: only starts/stops/changes/home instructions; one none-statement if
  the source says nothing new was prescribed; never list empty med lists.
- Skip charted background not addressed this visit, superseded or conditional
  plans, generic radiology boilerplate ("correlate clinically", "discuss with
  the ordering provider"), and admin text.
- When sources disagree (e.g., urgent-care ECG read vs. ER read), say so in one
  sentence.
- Translate, don't interpret: plain words for terms the source uses (infarct →
  stroke) are fine; adding a label, cause, urgency, prognosis, range, or "normal"
  the source does not state is not.

### 4.3 Protected content (`scripts/protected.py`, new library)

Six categories: `medication_changes`, `follow_up`, `return_precautions`,
`diagnoses`, `disposition`, `abnormal_or_pending_results`.

`protected.scan(units) -> dict[category, list[unit_id]]` runs case-insensitive
regexes over non-skipped units to find **candidate** units (high recall, cheap;
false positives are fine because the verifier dismisses them). Starting
patterns:

| Category | Signals |
|---|---|
| return_precautions | `return to (the )?(er|ed|emergency)`, `come back`, `seek (immediate|emergency|medical)`, `call 911`, `go to the (nearest )?emergency`, `return (precautions|if)`, `if .* (worsen|worsening)` |
| follow_up | `follow[- ]?up`, `schedule`, `appointment`, `referr`, `see your (primary|pcp|doctor|provider)`, `within \d+ (day|week|month)` |
| medication_changes | `prescri`, `\b(start|started|stop|stopped|discontinue|increase|decrease|resume|hold)\b`, `new medication`, `\d+(\.\d+)? ?(mg|mcg|g|ml|units?)\b` with `(daily|bid|tid|qid|prn|by mouth|po|every|twice|times)` |
| diagnoses | `diagnos`, `impression`, `assessment`, `clinical impression`, `final dx`, `\bdx\b` |
| disposition | `discharg`, `admit`, `disposition`, `transfer`, `(stable|good|fair) condition` |
| abnormal_or_pending_results | `pending`, `awaiting`, `abnormal`, `elevated`, `critical`, `positive`, `\((h|l|hh|ll|a)\)`, `flagged` |

`01_protected.json`:

```json
{"schema_version": "3.0", "run_id": "...",
 "categories": {"follow_up": [41, 88], "return_precautions": [90], "...": []}}
```

### 4.4 CHECK (`scripts/check_draft.py`, new; replaces cite_check + numeric_parity)

`python3 scripts/check_draft.py --run-dir <run> [--round 2]`

Validates `02_draft.raw.json` against `schema/draft.schema.json`; every
`unit_ids` entry exists and is not skipped; `coverage` "shown" categories cite at
least one unit that some visible item also cites; every visible string is free
of leftover empty brackets `()`/`[]` and of unexpanded clinician names matching
the existing PII shapes. On pass writes `02_draft.json` (= raw + `schema_version`,
`run_id`; schema `draft_checked`) and `02_check.json`; on fail prints errors for the one WRITE retry and
records `write` as failed after the retry budget.

`02_check.json` (schema `check.schema.json`):

- `word_count` of the rendered visible text (`plan_view.visible_text`),
  `budget: {"target": 300, "warn": 350, "max": 500}`, `over_budget: bool`
  (word_count > warn). word_count > max is a CHECK failure.
- `numeric_flags[]`: for each visible field, number tokens (reuse the existing
  tokenizer from `numeric_parity.py`, moved to `scripts/numbers.py`) that do not
  appear in that item's cited units → `{flag_id, path, token, unit_ids}`.
- `uncited_protected[]`: protected candidate unit ids (from `01_protected.json`)
  that no visible item cites, with their categories.

### 4.4a Visible paths and edit rules (`scripts/plan_paths.py`, shared)

`plan_paths.visible_items(plan)` is the single definition of what the patient
sees, in report order: `why_you_went`, `findings_lead`, `findings[i]`,
`diagnoses[i]`, `disposition`, `next_steps[i]`, `medicines.items[i]`,
`medicines.none_statement`, `return_precautions[i]`, `questions[i]`.
`plan_paths.visible_strings(plan)` yields `(field_path, text, unit_ids)`; CHECK,
SETTLE, the renderers' word count, and the verifier's `claims` all use these
item paths.

Verifier operation paths:

- `replace`: a visible string field, e.g. `findings[2].result`,
  `why_you_went.text`, `diagnoses[0].plain_name`. `unit_ids` replaces the
  containing item's `unit_ids`.
- `clear`: `findings_lead`, `disposition`, `medicines.none_statement` (→ `null`)
  or `diagnoses[i].plain_name` (→ `""`).
- `remove`: an array item path (`findings[3]`, `medicines.items[0]`, ...).
  Removals are applied from the highest index down so paths stay valid.

### 4.5 VERIFY (`stages/verify.md`, model call 2)

Independent: run in a fresh sub-agent when the host supports it; otherwise
re-read only the named inputs. Inputs: `01_source.txt`, `02_draft.json`,
`02_check.json`, `reference/style_rules.md`, `schema/verify_raw.schema.json`.
Output: `03_verify.raw.json` (round 2: `03_verify.r2.raw.json`).

The verifier does four things, each bounded by the short draft:

1. **Claims** — one entry per visible item path (e.g., `findings[2]`,
   `why_you_went`, `medicines.none_statement`): `supported` or
   `needs_correction` or `unsupported`. It checks the item against its cited
   units *and* the surrounding source: fidelity, negation, uncertainty, exact
   numbers/units/doses, no added label/cause/urgency, correct attribution
   (urgent care vs ER), not an old history item presented as current.
2. **Operations** — bounded edits for every non-`supported` claim and for
   trimming: `replace` (path to a string field, value, unit_ids), `clear`
   (optional field), `remove` (array item) with `reason` ∈ `unsupported`,
   `noise`, `duplicate`. When `over_budget` is true it must remove or shorten
   the least important non-protected items until the draft fits.
3. **Numeric flags** — each resolved once: `equivalent` / `corrected` /
   `removed`, with `correction_path` for the latter two.
4. **Protected candidates** — each `uncited_protected` unit gets exactly one
   result: `covered` (already represented by a visible item), `not_needed` with
   reason ∈ `boilerplate`, `duplicate`, `superseded`, `not_patient_specific`,
   `false_positive`, or `missing` (patient-specific protected content that must
   be shown).

No verdict, no rewritten plan, no new items (missing content goes only through
`missing`).

### 4.6 SETTLE (`scripts/settle.py`, new; replaces settle_review)

`python3 scripts/settle.py --run-dir <run> [--round 2]`

- Validates `03_verify.raw.json` against schema: every visible path has exactly
  one claim; every numeric flag and every uncited protected unit resolved once;
  operations target existing visible paths; `corrected`/`removed` resolutions
  name an operation path; non-`supported` claims have an operation.
- Applies operations exactly (reuse `settle_review.apply_operations` path logic).
  Replacement values' `unit_ids` replace the item's citations.
- Re-asserts after edits: schema valid; coverage "shown" categories still backed
  by a visible item (a removal that orphans protected coverage is rejected);
  no unresolved numeric token remains (tokens must appear in cited units or be
  resolved `equivalent`); word_count ≤ max.
- If any protected unit is `missing`: in round 1, write `04_repair.json`
  (`{missing: [{unit_id, category}], settled_draft: <settled plan>}`), record
  `settle` status `repair_requested`, print `settle: repair requested`, exit 3.
  In round 2, fail.
- Otherwise writes `03_verify.json` (record of claims, resolutions, applied ops)
  and `04_plan.settled.json`; exit 0.
- Contract errors: exit 1 with errors for the one VERIFY retry.

### 4.7 FINALIZE (`scripts/finalize.py`, rewritten)

Assertion-only: current run id everywhere; stages `unitize`, `write`, `check`,
`verify`, `settle` ok for the final round; schema-valid artifacts; PII sweep
(existing bounded shapes); writes `05_plan.final.json` (schema `plan.schema.json`
= settled draft + `schema_version`, `plugin_version`, `run_id`, `created_at`,
`word_count`, readability `score`) and `report.md` via `render_md.render`.

### 4.8 Renderers

`plan_view.build_view(plan)` produces the sections in §3 order;
`render_md`, `render_html` (+ `templates/report.html`), `render_audit` (each
visible item followed by its cited unit texts with file/page/line), and
`glossary_check`/`stages/glossary.md` (optional, on request, visible text only)
all consume it. Fixes: title from `visit_type`; no stray type-label lines; no
`title (plain_name)` duplication — diagnoses show `plain_name` only when it adds
meaning (not a case/word-order variant of `name`); no empty-dash rows; no
"Already done".

## 5. Artifact contract (clean run)

```text
run.json
00_input/<files>
01_units.json          all units incl. skipped (audit)
01_source.txt          numbered source the models read
01_protected.json      protected candidate units
02_draft.raw.json      WRITE output
02_draft.json          checked draft
02_check.json          budget, numeric flags, uncited protected units
03_verify.raw.json     VERIFY output
03_verify.json         settled verification record
04_plan.settled.json
05_plan.final.json
report.md
```

Repair round adds `04_repair.json`, `02_draft.r2.raw.json`, `02_draft.r2.json`,
`02_check.r2.json`, `03_verify.r2.raw.json`, `03_verify.r2.json`, and settles to
`04_plan.settled.json`. Failed attempts keep an `.attempt1` suffix.

Schemas (`schema/`): keep `units`, `run`, `glossary`, `glossary_raw` (updated);
add `protected`, `draft` (WRITE contract), `draft_checked` (`02_draft.json`
and `04_plan.settled.json`), `check`, `verify_raw`, `verify`, `plan`; delete
`facts_raw`, `facts`, `care_plan_agent`, `care_plan`, `flags`, `review_raw`,
`review`. `SCHEMA_VERSION` becomes `"3.0"`.

Run-log core stages: `unitize`, `write`, `check`, `verify`, `settle`,
`finalize`; statuses `ok`/`failed`, plus `repair_requested` for `settle`.
Optional stages unchanged.

Scripts: add `protected.py`, `numbers.py`, `check_draft.py`, `settle.py`;
delete `anchor_check.py`, `merge_facts.py`, `cite_check.py`,
`numeric_parity.py`, `settle_review.py`. Stages: add `write.md`, `verify.md`;
delete `ground.md`, `assemble.md`, `review.md`. Reference: rewrite
`style_rules.md` (keep PII, NUMERACY, LANGUAGE; replace CRITICAL VS SUPPORTING
with SHOW/SKIP rules from §4.2); delete `categories.md`; keep
`abbreviations.json` and `ahrq_plain_language.json` as optional lookups (not
required reading).

## 6. Safety requirements (must hold after the change)

1. Every visible item cites ≥ 1 existing, non-skipped source unit.
2. Every number token in visible text appears in the item's cited units or is
   resolved `equivalent` by the verifier.
3. Protected candidates are each shown, or dismissed by the verifier with a
   reason; `missing` triggers exactly one repair; a second miss fails.
4. An independent verification of every visible item precedes release.
5. No clinical content is shown after any terminal failure; no host-authored
   fallback summary.
6. PII: clinician/facility names generic; patient identifiers never shown.
7. Translate, don't interpret; unknown ≠ negative; exact conclusion wording.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Omitting something important without a fact ledger | Protected-candidate scan is source-side and high-recall; verifier must resolve each; CREOLA evidence shows direct generation omits less than atomize-first. |
| Writer mis-cites units | CHECK validates ids; verifier checks each claim against source; numeric parity per cited units. |
| Grouped bullets hide an abnormal result | `abnormal_or_pending_results` is a protected category. |
| Very long packets exceed one call | Out of scope now; unitize reports unit count; add a map pre-pass later if needed. |
| Parked OpenAI widget reads the old plan shape | Not packaged; tracked as follow-up. |
