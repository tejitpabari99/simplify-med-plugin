# Research: why `simplify` is slow and verbose

Status: research synthesis, 2026-09-26. Inputs: a code audit of `skills/simplify/`
plus a full read of the team Drive folder (Tech, Patient Research, Product, Data,
Public). No patient identifiers are reproduced here.

Trigger: an ER-visit packet (headache, left-hand tingling, abnormal urgent-care ECG;
CT/CTA head and neck normal; brain MRI normal; labs unremarkable; discharged; PCP
follow-up; return for new or worse symptoms) produced a ~1,200-word report. The
user's target is ~200 words:

> **Your ER visit, simplified** — You went to the ER because … / **What did they
> find?** Brain MRI: Normal. No stroke was seen. · CT/CT angiogram: Normal … ·
> Neurologic exam … · Blood tests: described as unremarkable · Heart tracing: RBBB
> and first-degree AV block, not thought to show a heart attack / **The ER diagnosed
> you with:** acute headache; tingling in left arm/hand / discharged in stable
> condition / **What should you do now?** Schedule primary care … No new medicines.
> / **When should you go back to the ER?** Any new or worsening symptoms.

## 1. Code audit: root causes

### 1.1 The keyword veto (largest single cause of both problems)

`scripts/cite_check.py:134-201` decides, with regexes over the fact's own text,
whether an omission reason is *allowed*; `:340-344` fails the draft otherwise.
Neither `stages/assemble.md` nor `stages/review.md` tells the model these rules.

- Every `reason_for_visit`, `follow_up`, `warning_signs` fact is un-omittable
  (`:139-140`) — so four restatements of the headache history all had to be shown.
- `diagnosis` facts are un-omittable unless they contain "ruled out / unlikely /
  stable…" (`:150-151`) — every CT/MRI sub-finding and "no problem list on file".
- `medications` are un-omittable unless they contain "stable / unchanged / home
  medication" (`:141-149`) — the three "no medications" rows, the ibuprofen advice.
- `technical_detail` requires the literal word "contrast/protocol/sequence…"
  (`:74-77`) — "Iopamidol (Isovue-370) 76 % injection 80 mL" can't be hidden.
- `routine_non_actionable` requires "normal/routine/incidental/completed"
  (`:78-81`) — "sodium 142", every CBC row, both sets of vitals can't be hidden.
- `duplicate_or_already_represented` requires a byte-identical fact (`:175-181`).

A simulation of 23 ER-style facts: 22 of 23 had no omission reason accepted.
Effect: a model that follows "be concise" fails its first assemble attempt, burns
the retry, and ends up showing nearly everything. This check was not in the
approved design (`docs/agent_files/prep-medlit-skills/DESIGN.md:234`, decision D5
says supporting detail must not be forced visible); it arrived in 44846e7.
Tests pass only because test fixtures contain the magic words
(`tests/test_cite_check.py:16-35`).

### 1.2 Work scales with the whole chart, not with the report

- `stages/ground.md:25` extracts *every* statement as an atomic fact with an exact
  quote: ~150–300 facts for an ER packet.
- Assemble must emit a disposition for every fact (`cite_check.py:346-353`).
- Review must list every fact id and emit one review per fact
  (`stages/review.md:36-37`, `settle_review.py:225-240`).
- All of this is serial after grounding. Rough output: grounding 12–18k tokens,
  assemble 6–10k, review 4–6k — to protect ~10 visible sentences.
- Older-pipeline timings: assemble 230 s for 38 facts and 369 s for 77 facts;
  grounding 132–309 s per chunk (`kill-test-1.md:29-47`, `kill-test-2.md:29-49`).
  The current pipeline was never benchmarked (`docs/architecture.md:378-387`).

### 1.3 Other latency drivers

- Near-certain assemble retry caused by 1.1.
- Any `must_include` stops settlement → full reassembly + second full review
  (`settle_review.py:512-524`, `review.md:93-95`).
- Chunks are 150 *lines*, not tokens (`unitize.py:33`), so a 700–900-line ER
  export is 5–6 grounding calls, parallel only if the host has sub-agents.
- Whole-clause quote matching (`anchor_check.py:293-296`) and fail-on-any-bad-quote
  (`merge_facts.py:138`) force full chunk re-runs.
- The host is told to read `01_units.json` (~120–140 KB for an ER packet) just to
  learn the chunk count (`SKILL.md:82`); `unitize.py` already prints it. Assemble
  also reads ~45 KB of references, half of it the AHRQ word list.
- Clean path: K+2 model calls, K+6 scripts. Worst case: 2K+8 model calls.

### 1.4 Other verbosity drivers

- Review can only *add*: `omitted_facts` is protected (`settle_review.py:26-28`) and
  removing an item leaves its facts uncovered (`:434-437`).
- Merging is forbidden: "never replace specific details with a vague collective
  phrase" (`assemble.md:71`) — "Blood tests: unremarkable" is illegal.
- No length budget anywhere; the 60–120-word summary hint is never checked.
- The schema cannot express the target: tests are to-do/done tasks with no result
  or bottom-line field (`care_plan_agent.schema.json:121-134`); there is no
  disposition, no discharge-diagnosis list separate from findings, no "no new
  medicines" statement; every `done` item lands in "Already done"
  (`plan_view.py:340-368`).
- Render bugs: stray `_Medication_`/`_Test_` line per row (`render_md.py:37`);
  `title (plain_name)` whenever the strings differ at all → "Head CT findings (Head
  CT results)" (`render_md.py:61`, `plan_view.py:257,276,290`); follow-up rows
  hard-coded "Appointment" plus a double dash with empty timing
  (`plan_view.py:301-306` + `render_md.py:35`); title hard-coded "Your visit,
  explained" (`plan_view.py:444`).
- "glucose 115 ()" is probably an "(H)" flag stripped by the no-labels/expand-
  abbreviations rules on a row that was forced visible (inference, unconfirmed).

### 1.5 History

- 2026-09-22 port: 7 stages, roughly one fact → one item. Verbose by design; ~15
  minute runs.
- 4e53e8e: relevance triage with a free-form `low_priority` list; the model could
  hide freely. Most concise-capable version, but K+4..K+6 calls.
- 44846e7 "Faster, Fail-Closed": K+2 calls, fail-closed everywhere, plus (beyond the
  design) the keyword veto, whole-clause quotes, fail-on-any-bad-quote. The speed
  gain was never measured. A summarize-then-verify path was ruled out
  (`DESIGN.md:57-59`) — without evidence either way.

## 2. Drive: Tech folder (pipeline lineage and evidence)

The current pipeline is almost exactly the "GPT Researched pipeline" bundle (docs
00–07, 2026-09-12): ground = candidate fact ledger (01), every-fact disposition =
lint `FACT_DROPPED_WITHOUT_DECISION` (02), per-fact review = bidirectional coverage
(03/04), settle = release controller (05). Those same docs flag the ledger as
unproven — doc 07 open question #5: "The benefit of context selection and
ledger-guided generation is unresolved for this workload." Docs 01 and 03 say the
obligations "do not require every fact to appear"; protected categories were meant
to be the focus.

The earlier "GPT Plugin" docs (2026-09-07) proposed writer → fidelity reviewer →
clarity reviewer with "no … full evidence ledger": "A ledger becomes risky if later
stages treat it as the only evidence: omissions in the ledger then become
invisible." "For a short or simple record, the writer and reviewers work directly
from the original source."

Published evidence the team collected:

| Source | Finding relevant to us |
|---|---|
| Asgari et al. (CREOLA), Exp 5 | Extract-atomic-facts-then-write *increased* major hallucinations 4 → 25 and major omissions 24 → 47 vs. direct generation. A single structured prompt with an explicit "unknown/not mentioned" state cut major hallucinations 75% and major omissions 58%; one variant reached 0 major omissions. Hallucination types: fabrication 43%, negation 30%; major ones cluster in the Plan (21%). 83% of omissions were minor. |
| Kruse et al. | Extract-events-first "did not yield improvements over direct generation." |
| Croxford (PDSQI-9 judge) | Single judge: ICC 0.818, 12–22 s, $0.03–0.05. Multi-agent panel: ICC 0.768, 69 s, $0.16. |
| Li et al. (self-check loop) | 83 s vs ~25 s single pass (3.3×); most gain in iteration 1. |
| Fact-Controlled Diagnosis | Per-fact detectors correlate only 0.36–0.43 with truth, undercount errors, "computationally expensive." |
| AgenticSum | One whole-summary entailment check listing "problematic spans," fix only flagged spans, stop rule. |

Team guidance on speed: doc 04 "maximum of one factual repair pass," judge in
"shadow mode"; doc 05 "The MVP's key guardrail is not an extra LLM call; it is the
deterministic refusal to release unresolved protected facts"; Simplify V2: don't
have the LLM return spans/quotes ("Too long / Higher token cost / Fragile") — cite
unit ids and let scripts check.

Team guidance on length: AHRQ "Limit information to one to three need-to-know or
need-to-do points"; GPT Plugin "Main point: two or three sentences. Next steps: a
short checklist … Medication changes: include only when applicable … Questions:
zero to three … The goal is not to display every extracted field … Empty sections
are hidden"; Good summary criteria (Must) "Remove or hide … history that was not
discussed; details about how a test was done; repeated medication lists …;
administrative details." Radiology Impression = the radiologist's conclusion → the
right source for one-line bottom lines.

Likely origin of the "show everything" instinct — doc 02: "Put remaining supported
details in their evidence-conditional section rather than delete them."

## 3. Drive: Patient Research and Product

- The three questions patients ask: what happened / what it means / what do I need
  to do. A caregiver: "What is important is the summary of the outcome … what has
  happened. What do I need to do." The PRD-like "Juno updated idea": reason for
  visit, key findings, assessment, diagnosis explanation, meds (only new or
  changed), next steps.
- Less is better: "The total number of items to be recalled per visit … were
  significant predictors of poorer recall"; clinicians on AI summaries: "Over
  inclusive … Has to be succinct"; "top three"; survey (~165): 22 "too much
  information", 29 don't want long recordings to find one detail. Progressive
  disclosure for the few who want depth.
- Normal results in words: "Blood tests say this is fine. They might look
  borderline. What does that mean — That is annoying." Words are read more
  accurately than numbers.
- Reading level target ~6th grade (Video Script).
- Speed: no stated SLA. Decks promise "Real-time Summarization"; integrations
  report suggests parallel calls and one "QA evaluator" rather than a full second
  pass. "For me to write 3 lines, faster than to review 4 lines for errors."
- Trust rules that bound what we cut: "Juno translates; it does not interpret";
  no new facts; citations back to source; show uncertainty. Deck line "NO ADDED OR
  REMOVED INFORMATION" is read by the engineering docs as "preserve clinical
  meaning, instructions and risks" — dropping noise is allowed; dropping
  decisions, diagnoses, instructions or return precautions is not. Neuro-oncologist
  warning: "If high level summary — they come back and say we didn't discuss."
- Prefer "what was agreed / what the discharge says" over advice-voice.

## 4. Drive: Data and Public

- No ER cases in Drive. Real test data is one pediatric set (ophthalmology notes,
  labs, sleep study, neck ultrasound, allergy consult), 60–1,500 words per document,
  heavy with portal headers, repeated pages and fax/legal boilerplate. In the sleep
  study all conclusions live in ~220 words of Impression + Comments.
- Closest gold output: the clinician "V2" rewrite (~450 words; What we found →
  about the condition → daily-life impact → one important concern → 5 numbered next
  steps). FK grade 14.2 → 10.9 → 8.2 across versions.
- CSO critique of current outputs ("Comparison summaries of Test results"):
  "compress, group, and prioritize" — one lead takeaway, ~5 grouped buckets, only ~4
  key numbers, "main findings" separate from "other reassuring findings", hide the
  rest; old problem-list diagnoses leaking into "what it means"; don't turn "interpret
  in clinical context" boilerplate into actions; don't resurface superseded
  conditional plans; keep the conclusion's exact word ("significant" ≠ "major");
  drop alarming labels ("OVERALL STATUS: CONCERN"); define terms inline; show the
  "why" for actions; add a title. She also wants a *short* explanation per key
  result — short body, not bare terseness.
- Current-model outputs run 650–750 words from sources whose key content is ~220.
- Proposed eval: PDSQI-9 LLM judge; MIMIC-IV-Note / BHC / "Discharge Me!" as ER and
  discharge test sources.
- Public pitch: "Turn discharge summaries, and care instructions into personalized
  guidance with clear next steps." No speed or length promise.

## 5. Safety constraints any redesign must keep

1. Translate, don't interpret: no diagnosis, cause, urgency, prognosis, purpose, or
   "normal"/"reassuring" label the source does not state.
2. Exact medication names, doses, units, dates, frequencies — deterministic parity.
3. Negation and certainty preserved (30% of hallucinations are negation errors).
4. Unknown ≠ negative. "No new medicines" must itself come from the source.
5. Protected content is never silently dropped: medication starts/stops/changes,
   follow-up, return precautions, discharge diagnoses, disposition, abnormal or
   pending results.
6. Independent review against the *original source*, not a ledger. One bounded
   repair. Never fall back to an unchecked draft.
7. No identifiers in output; don't resurface old history or superseded plans.
8. Validate any pipeline change on the same inputs before/after.

## 6. Housekeeping found during research (outside the repo)

- A Drive doc ("Datasets, Benchmarks and Assessment by LLM") holds a PhysioNet
  username and password in plain text — rotate it and remove it from the doc.
- The Patient 1 folder holds un-redacted records of a minor next to the
  de-identified copies.
