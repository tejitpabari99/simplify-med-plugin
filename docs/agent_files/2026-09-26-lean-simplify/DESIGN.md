# Design (draft for brainstorm): lean `simplify` — write, then verify what is shown

Status: proposal, not yet approved. Evidence in `research.md` (same folder).

## Principle

**Ground the claims, not the chart.** Grounding effort should scale with what the
patient sees (~10–25 claims), not with everything in the packet (~150–300 facts).
Keep the guarantees that matter — every visible sentence traceable to source,
numbers exact, negation intact, protected content never silently dropped, an
independent check before release — and drop the machinery that only exists to
account for facts nobody will read.

## Target output (fixed slots, empty slots hidden)

```text
# Your ER visit, simplified            <- visit type from the source (ER, hospital stay,
                                          clinic visit, test results)
<1–2 sentences: why you went>

## What did they find?
<optional one-line lead, only if the source frames it, e.g. "reassuring">
- **Brain MRI:** Normal. No stroke was seen.          <- test/area + bottom line in words,
- **CT angiogram of head and neck:** Normal. …           taken from the Impression/assessment
- **Heart tracing:** … the ER doctor did not think …     max ~6 bullets; numbers only when
                                                          the number itself matters
**Diagnosed with:** acute headache; tingling in your left arm/hand
<disposition sentence: discharged / admitted / stable — only as stated>

## What should you do now?
- Schedule a primary-care appointment …               <- follow-up, med starts/stops/changes
- You were not prescribed any new medicines.          <- only if the source supports it

## When should you go back to the ER?
- Any new or worsening symptoms.                      <- return precautions, verbatim action

## Questions to ask (0–3, optional)
```

Budget: target 150–300 words; deterministic warning above ~350, hard fail above a
configurable cap (e.g. 500). Everything else stays in the source and the audit view.

## Proposed pipeline (clean path: 2 model calls)

```text
UNITIZE (script)            number lines, strip portal/fax boilerplate, larger
                            token-based chunks; print unit count, don't make the
                            host read 01_units.json
  -> WRITE (1 model call)   reads the numbered source directly; fills the fixed
                            slots; every bullet cites unit ids (no quotes); fills a
                            protected-content checklist: for each protected
                            category either the item that covers it or
                            "none in source"
  -> CHECK (script)         schema; unit ids exist; every number/unit/dose in a
                            bullet appears in its cited units; word budget;
                            abbreviation/label lint; protected-candidate scan of
                            the SOURCE (return/ER precautions, follow up, med
                            verbs, discharge diagnosis, pending/abnormal) ->
                            short list of units the verifier must look at
  -> VERIFY (1 model call)  independent; reads source + draft + candidate list;
                            checks each visible claim against its cited units
                            (fidelity, negation, uncertainty, no added labels) and
                            checks candidate units for protected omissions; emits
                            bounded ops (replace/clear/remove) + `missing` ids
  -> SETTLE (script)        apply ops; if `missing` is non-empty -> one REPAIR
                            call adding only those items, then re-verify only the
                            changed bullets; a second miss fails the run
  -> RENDER (script)        report.md; audit view on request
```

Long packets (above a token threshold, not a line count): an optional parallel
**map** pre-pass per chunk that pulls only impressions/assessments/plan/
instructions/med changes with unit ids — not every statement — feeding WRITE.

### What gets removed

| Current | Proposed | Why |
|---|---|---|
| ground[1..K]: every statement, exact quotes | gone (optional targeted map for long packets) | Asgari Exp 5: atomize-first raised major hallucinations 4→25 and omissions 24→47; biggest token cost |
| Every-fact disposition in assemble | protected-category checklist only | Scales with chart, not report; not in team docs 01/03 |
| cite_check keyword veto | removed | Makes concision impossible; not in approved design |
| Review of every fact | verify visible claims + protected candidates | Single-judge beats panels; per-fact detectors 0.36–0.43 |
| Reassembly + full second review | one repair + re-verify changed bullets only | Doc 04: one factual repair pass |
| Quotes emitted by the model | unit ids; scripts do the matching | Simplify V2: quotes are "too long / fragile" |

### What stays

- Numbered source units and unit-id citations on every visible bullet.
- Deterministic numeric/dose/unit parity, now against cited units.
- An independent verifier against the original source; one bounded repair; fail
  closed — never ship an unverified draft.
- Protected content cannot vanish silently: the writer must cover it or declare
  "none in source", the script surfaces candidate units, the verifier checks them.
- PII rules, translate-don't-interpret, no added labels/ranges/urgency.

### Expected effect (estimate, to validate)

| | Current (ER packet, K≈5) | Proposed |
|---|---|---|
| Model calls, clean path | 7, with ~5 in parallel only on sub-agent hosts | 2 |
| Model output tokens | ~25–35k | ~2–4k |
| Script calls | ~11 | ~3 |
| Report length | ~1,200 words | ~150–300 words |

## Verbosity rules for WRITE (prompt, not regex)

- One bullet per test/area with the source's own bottom line (Impression /
  assessment wording, plain-worded). Group sub-findings; never list them.
- Labs/vitals: only if the clinician comments on them or a value drives the plan;
  otherwise at most one grouped line using the clinician's word ("unremarkable").
- Medications: only starts, stops, changes, and home instructions; "no new
  medicines" only when the source supports it. Never list empty med lists.
- Skip: test technique, contrast, reconstructions, criteria names, duplicate
  records, radiology boilerplate ("discuss with ordering provider"), charted
  background not addressed this visit, superseded or conditional plans.
- Keep exact conclusion words ("no significant" stays "no significant").
- Show conflicts in one sentence (e.g., urgent-care ECG read vs. ER read).

## Render fixes (independent of the pipeline change)

- Title from visit type; drop stray `_Medication_`/`_Test_` lines; show
  `plain_name` only when it adds meaning; no empty-timing double dash; no
  "Already done" inventory.

## Open questions for the brainstorm

1. Citation grain: unit ids per bullet (proposed) or exact quotes per bullet?
2. Verifier: keep one independent model check (proposed), or deterministic-only for
   maximum speed?
3. Length: hard cap or warning only? Should there be a collapsed "More details"
   section, or nothing beyond the short report?
4. Long packets: is the optional map pre-pass needed now, or later?
5. Evaluation: before/after on the ER case plus the Patient 1 set and the
   "Comparison summaries" cases, with a PDSQI-9 judge in shadow mode?
