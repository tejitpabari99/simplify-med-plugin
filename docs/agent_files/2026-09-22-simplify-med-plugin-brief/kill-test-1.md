# Kill test 1 — host-simulated end-to-end run

Run folder: `/root/projects/juno-projects/simplify-med-plugin/simplify-runs/20260922T032433Z-73177d/`
Input: `tests/fixtures/documents/synthetic-visit-note.txt` (`native` extraction, 76 lines, 57 non-blank units, 1 chunk).
Role played: a host with sub-agents, following `skills/simplify-med/SKILL.md` literally, dispatching each LLM stage to a fresh `general-purpose` sonnet sub-agent carrying the matching `agents/<stage>.md` body + the exact dispatch-message shape from SKILL.md section 4.

## 1. Outcome

The run completed successfully end to end. Every one of the 10 pipeline stages (unitize, glossary, ground, assemble, numeric_parity, review_fidelity, review_coverage, correct, assemble_missing, finalize) finished with `status: "ok"` or the documented `"skipped"` — nothing failed, nothing needed a retry.

- **Reading level (verbatim):** `Reading level: grade 11.3 before, grade 7.4 after.`
- **Notices:** none. `run.json`'s top-level `notices` array is `[]`, and `finalize`'s own `notices` check is `[]`.
- **Counts:**
  - Units: 57 (1 chunk, K=1)
  - Facts: 38 in, 38 kept, 0 dropped, 0 duplicates removed
  - Glossary: 25 terms proposed and kept by `glossary_check`; 13 survived finalize's re-detect (only terms that actually appear in the rendered report text)
  - Assembled plan items: 34 in, 34 kept by `cite_check` — 5 `reason_for_visit`, 4 `diagnosis.details`, 4 `medications`, 11 `tests`, 1 `procedures`, 3 `other`, 3 `follow_up`, 3 `warning_signs`, 3 `questions`, 3 `low_priority`
  - `numeric_parity`: 113 fields checked, 4 numeric-token mismatches flagged (never fails the run)
  - Review — fidelity: verdict `pass`, 0 corrections
  - Review — coverage: 38/38 facts present, 0 missing
  - Stage 4: `correct` skipped (corrections=0), `assemble_missing` skipped (missing=0) — both per SKILL.md's documented skip path
  - Corrections applied: 0. Missing facts backfilled: 0. Additions merged: 0.
  - PII substitutions: 0 (no clinician/patient name ever entered the fact ledger, so none needed sweeping)

## 2. Timeline

All commands/dispatches, in execution order. "Wall-clock" is measured time for scripts (via `time`) or the sub-agent's own reported `duration_ms` for dispatched stages.

| # | Step | Command / dispatch | Exit / reply | Wall-clock |
|---|---|---|---|---|
| 1 | Stage 0 | `python3 unitize.py --runs-dir <cwd>/simplify-runs --input synthetic-visit-note.txt:native` | exit 0; printed `<run>` path | 0.08s |
| 2 | Stage 1 (parallel A) | Dispatch `simplify-med-ground`, chunk 1, stage file `stages/ground.md` | "…02_facts.1.raw.json — 38 items" | 132.4s |
| 3 | Stage 1 (parallel A) | Dispatch `simplify-med-glossary`, stage file `stages/glossary.md` | "02_glossary.raw.json: 25 terms" | 91.8s |
| 4 | check | `anchor_check.py --chunk 1` | exit 0; 38/38 facts `ok` | 0.04s |
| 5 | check | `glossary_check.py` | exit 0; silent | 0.04s |
| 6 | merge | `merge_facts.py` | exit 0; wrote `02_facts.json`/`.txt` | 0.05s |
| 7 | Stage 2 | Dispatch `simplify-med-assemble`, stage file `stages/assemble.md` | "The output validates against the schema. / …03_plan.raw.json — 1 JSON document written (12 top-level keys; 5/4/4/11/1/3/3/3/3/3 items)…" | 230.2s |
| 8 | check | `cite_check.py` | exit 0; "OK wrote …03_plan.draft.json (34/34 items kept)" | 0.05s |
| 9 | check (never fails) | `numeric_parity.py` | exit 0; "OK wrote …03_flags.json (4 numeric mismatch(es), 0 thin field(s))" | 0.06s |
| 10 | Stage 3 (parallel B) | Dispatch `simplify-med-review-fidelity`, stage file `stages/review_fidelity.md` | "04_review.raw.json: 0 corrections" | 111.5s |
| 11 | Stage 3 (parallel B) | Dispatch `simplify-med-review-coverage`, stage file `stages/review_coverage.md` | "04_coverage.raw.json: 38 facts" | 18.2s |
| 12 | check | `sanitize_review.py --only review` | exit 0; silent stdout | <0.1s (untimed) |
| 13 | check | `sanitize_review.py --only coverage` | exit 0; silent stdout | <0.1s (untimed) |
| 14 | Stage 4 C1 (skip path, corrections=0) | `diff_guard.py` (no `--strict`) | exit 0; **silent stdout**, wrote `05_plan.corrected.json` | 0.07s |
| 15 | Stage 4 C2 (skip path, missing=0) | `cite_check.py --additions` | exit 0; "OK skipped (no 05_additions.raw.json found); wrote empty …05_additions.json" | 0.04s |
| 16 | Stage 5 | `finalize.py` | exit 0; printed `report.html`, `report.md`, reading-level line, no notices | 0.09s |
| 17 | audit | `render_audit.py` | exit 0; "OK wrote …report.audit.md" | 0.05s |

Concurrency: parallel group A (ground + glossary) and parallel group B (review-fidelity + review-coverage) were each exactly 2 tasks, dispatched together and awaited together — the 2-concurrent-agent cap was exercised but never actually constrained anything, since neither group exceeded 2.

## 3. Friction

**F1 — `agents/` is not where SKILL.md implies it is.** SKILL.md section 4 says the agent is "defined under `agents/`" without giving a path relative to anything explicit, in a document where every other resource is written as `<skill>/reference/...`, `<skill>/schema/...`, `<skill>/scripts/...`. `<skill>` itself resolves to `skills/simplify-med/`, which has no `agents/` subdirectory at all — the actual agent definitions live one level up, at the plugin root (`/root/projects/juno-projects/simplify-med-plugin/agents/*.md`), a sibling of `skills/`, not a child of `<skill>`. I had to search the repo to find them. A host following the document's own established convention literally (`<skill>/agents/<stage>.md`) gets a file-not-found. This is the single biggest point of friction in an otherwise mechanical run.

**F2 — an LLM stage agent didn't obey its own "single line" reply instruction.** The `assemble` agent's `agents/assemble.md` body says "Reply with a single line giving the output path and the number of items written. Do not summarise the content." Its actual reply was two lines: `"The output validates against the schema."` followed by the required line. Harmless here since I read the reply myself, but a host script parsing that reply programmatically (e.g. to log a one-line summary) would need to defend against the agent not honoring its own format contract.

**F3 — silent success on skip paths is indistinguishable from "didn't run."** `diff_guard.py` run without `--strict` (the C1 skip path, since `corrections == 0`) produced **no stdout at all** on exit 0 — I only knew it worked by checking that `05_plan.corrected.json` appeared. Compare `cite_check.py --additions` on its own skip path (C2, `missing == 0`), which prints `"OK skipped (no 05_additions.raw.json found); wrote empty …/05_additions.json"`. Same skip-path spirit, inconsistent reporting: one script narrates its own no-op, the other doesn't. `sanitize_review.py` (both `--only review` and `--only coverage`) is likewise silent on stdout even though something real happened (it read `04_review.raw.json`/`04_coverage.raw.json` and wrote the sanitized `.json` siblings). SKILL.md's "every script exits 0 whether ok, degraded, or skipped" promise is true, but it undersells how much a host has to fall back on "does the output file now exist" rather than "does stdout say what happened."

**F4 — a real NUMERACY-rule violation shipped to the patient-facing report, and no stage was positioned to catch it.** `reference/style_rules.md`'s NUMERACY rule is explicit: "copy a value and its unit exactly as the fact states them... changing only spacing or spelling the way LANGUAGE RULES above already permits... the number and the unit itself are not [changeable]." Fact 8 is `"Blood pressure 148/92 mmHg, heart rate 78 bpm, regular rhythm."` The assembled plan's `tests[0].description` reads `"Your blood pressure was 148/92. Your heart rate was 78 beats a minute, with a regular rhythm."` — `mmHg` was dropped outright, not just respaced or reworded; `bpm` was legitimately expanded to "beats a minute" (that's an abbreviation-style rewrite, permitted). `numeric_parity.py` correctly flagged this exact mismatch in `03_flags.json` (`tests[0].description`: field tokens `["148/92","78 beats"]` vs fact tokens `["148/92 mmhg","78 bpm"]`). But `review_fidelity.md`'s own scope rule says "Do not flag style, tone, or word choice," and its numeric-parity-hint guidance says a mismatch "can be a harmless rendering difference... that is not a fidelity problem" — the review-fidelity agent read the hint, judged it harmless, and emitted 0 corrections. Nothing else in the pipeline enforces `style_rules.md`'s verbatim-numeracy rule the way `cite_check.py` enforces citation presence. This isn't an error I introduced; it's a gap between what `style_rules.md` promises and what any stage is actually responsible for checking.

**F5 — inconsistent title/plain_name choice from the same assemble agent produces a visibly duplicated diagnosis line.** Of the four `diagnosis.details` items, `"Stable angina"` correctly uses the medical term as `title` and a distinct plain-language gloss as `plain_name` ("chest pain caused by reduced blood flow to your heart"). But `"High blood pressure"` (from fact 5) has `plain_name: "high blood pressure (hypertension)"` — the same already-plain phrase repeated back, plus the medical term in parentheses — and `"High blood pressure not well controlled"` (fact 13) does the same thing. The report template renders `"{title} ({plain_name})"`, so the patient sees: `"High blood pressure (high blood pressure (hypertension))"` and `"High blood pressure not well controlled (high blood pressure that is not well controlled)"` — visibly redundant, doubled phrasing. Not a factual error (content still traces cleanly to facts 5 and 13 — see spot-check below), and out of scope for both review-fidelity ("style... not flagged") and review-coverage ("is the content present," yes it is). A real quality defect that nothing in the pipeline is positioned to catch.

**F6 — this fixture never exercised the retry path, multi-chunk dispatch, or any documented failure branch.** With K=1 and every stage validating clean on the first attempt, I never got to observe the "Retry: the previous output failed validation..." dispatch-message suffix in practice, never saw the failure-table branches for ground/assemble/finalize fire, and the 2-concurrent-agent cap was never actually binding (both parallel groups had exactly 2 members). This kill test verifies the happy path thoroughly but says nothing about SKILL.md's retry/failure mechanics — that would need either a harder document or a deliberately corrupted intermediate file to trigger.

## 4. Fidelity spot-check

Eight statements from `report.md`, checked against `report.audit.md`'s fact citations and quotes.

1. **Medication dose** — "Metoprolol... 25 mg, Twice a day... Start taking metoprolol 25 mg twice a day." → traces to fact 15, quote `"Start metoprolol 25mg BID for rate control and angina management."` "25mg" → "25 mg" (spacing only, permitted) and "BID" → "twice a day" (abbreviations.json-sanctioned expansion). **Supports.**
2. **Warning sign** — "Chest tightness at rest that lasts more than 15 minutes, or with sweating or nausea (Emergency) — Call 911 or go to the nearest emergency room right away." → fact 28, quote `"If chest tightness occurs at rest, lasts longer than fifteen minutes, or is accompanied by sweating or nausea, call 911 or go to the nearest emergency room immediately."` **Supports**, urgency "emergency" is a reasonable direct read of "call 911... immediately."
3. **Follow-up** — "Come back to the clinic to review your stress test results and check your blood pressure control... In four weeks, on 2026-09-08." → fact 26, quote `"Return to clinic in four weeks, on 2026-09-08, to review stress test results and reassess blood pressure control."` **Supports.**
4. **Finding/diagnosis** — "Stable angina... You have been newly diagnosed with stable angina. This is likely caused by narrowed arteries in your heart, called coronary artery disease." → fact 12, quote `"Stable angina, new diagnosis, likely due to underlying coronary artery disease."` **Supports.**
5. **Lab finding** — "Your total cholesterol was 238 mg/dL. This is high." → fact 32, quote `"Total cholesterol: 238 mg/dL (high)"`. **Supports**, exact number/unit/label all preserved.
6. **Medication side effect note** — "Atorvastatin may cause muscle aches in some people. This is a known side effect. It does not need immediate action unless it becomes severe." → fact 31, quote `"Atorvastatin may cause muscle aches in some patients; this is a known side effect to watch for but does not require immediate action unless severe."` **Supports.**
7. **Vitals ("finding")** — "Your blood pressure was 148/92. Your heart rate was 78 beats a minute, with a regular rhythm." → fact 8, quote `"Blood pressure 148/92 mmHg, heart rate 78 bpm, regular rhythm."` **Content supports, but the field silently dropped the "mmHg" unit** — see Friction F4. This is a NUMERACY-rule violation, not a fidelity violation in the pipeline's own vocabulary (the number itself, 148/92, is unchanged), but it is exactly the kind of silent judgement-injection style_rules.md's NUMERACY paragraph exists to prevent, and it reached the patient uncorrected.
8. **Diagnosis (rendering check)** — "High blood pressure (high blood pressure (hypertension))... You were diagnosed with high blood pressure in 2019. It was managed with lifestyle changes only, until now." → fact 5, quote `"Hx of hypertension, diagnosed 2019, managed with lifestyle changes only until now."` **Content supports** (2019 date, lifestyle-changes-only management, all present and correct), but the rendered heading is visibly duplicated text — see Friction F5.

Net: 6 of 8 spot-checked statements trace cleanly with no quality issue; 2 trace correctly in content but carry a rendering/wording defect (dropped unit; duplicated phrasing) that the pipeline's own checks were not positioned to catch.

## 5. Ledger recall

I read all 57 numbered source units against the 38 facts the pipeline extracted (via `02_facts.json`'s `quote` fields, all independently confirmed verbatim against the source by `anchor_check.py`, and cross-checked against `report.audit.md`'s page:line citations, which correctly map back to original source line numbers, e.g. fact 1 → `synthetic-visit-note.txt:1:10`, matching source line 10).

**Every clinical statement in the note became a fact.** The 19 units that did *not* become facts are, without exception, headers, demographics, or administrative text that `categories.md` explicitly excludes:
- Section headers (`CHIEF COMPLAINT`, `HISTORY OF PRESENT ILLNESS`, `REVIEW OF SYSTEMS`, `PHYSICAL EXAM`, `ASSESSMENT`, `PLAN`, `MEDICATIONS`, `TESTS ORDERED`, `PROCEDURES`, `OTHER INSTRUCTIONS`, `FOLLOW UP`, `WARNING SIGNS`, `MEDICATION NOTES`, `BILLING`, `LABORATORY RESULTS -- ADDENDUM`)
- The synthetic-document disclaimer line and the clinic name banner
- Demographics: patient name, DOB, visit date, provider name
- Billing/admin: `CPT 99214...`, insurance authorization line, "next appointment scheduling handled by front desk staff," "END OF VISIT NOTE, PAGE 1 OF 2"
- "Specimen collected: 2026-08-11" — a defensible judgment call to exclude (a bare collection date, no clinical content or action), but arguably could have been folded into a `tests` fact alongside the lab panel; I would not call this a miss.

**No fact misread the source.** Every one of the 38 `quote` fields is a verbatim, contiguous substring of its cited unit (confirmed by `anchor_check.py`'s 38/38 `ok` and by my own reading of `02_facts.json` against the source), and every `text` field's abbreviation expansions (Hx→history, BID→twice a day, qd→once a day, qhs→at bedtime, ECG→heart tracing (electrocardiogram)) match `reference/abbreviations.json` exactly with no content drift. The one multi-clause source line (line 13: "chest tightness radiating... Denies chest pain at rest. No prior cardiac history. Hx of hypertension...") was correctly split into four separate atomic facts (2–5) rather than merged or truncated, and line 19 (BP/HR/lungs/JVD/edema) was correctly split into four (8–11).

This is a clean, complete recall result on this document: nothing clinical was dropped, and nothing was fabricated or garbled in translation from source to fact.

## 6. Verdict

Yes, on this document a patient would be well served by `report.md`. Every clinical statement in the source note reached the plan (38/38 coverage), nothing was fabricated, every checked statement traces to a real, verbatim-quoted fact, PII was fully absent without even needing the sweep, the reading level dropped from grade 11.3 to grade 7.4, and the warning-signs/follow-up/medication sections a patient would act on are all accurate and correctly urgency-graded. The pipeline's citation and coverage discipline (`cite_check`, `numeric_parity`, `review_coverage`) worked exactly as designed and caught real signal (the 4 numeric-token mismatches) even where downstream judgment chose not to act on it.

The single most important fix: **close the gap between `style_rules.md`'s NUMERACY rule and what any stage actually enforces.** `numeric_parity.py` already detects the exact failure mode (a rendered field's numeric/unit tokens don't match its cited fact's tokens) — the fix is not a new detector, it's tightening `review_fidelity.md`'s guidance so that a genuinely *dropped unit* (not a spacing/expansion difference) is treated as an in-scope fidelity problem rather than out-of-scope "style." As run today, a clinically meaningful number (a blood pressure reading) can silently lose its unit between the fact ledger and the patient-facing report, flagged by the pipeline's own deterministic check, and still ship uncorrected because the LLM reviewer that reads the flag has been told that's not its job.
