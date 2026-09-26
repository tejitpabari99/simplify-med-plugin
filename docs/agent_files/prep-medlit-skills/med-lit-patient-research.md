# `med-lit`: patient health literacy assessment research

Research recommendation, 2026-09-26. This corrects the scope of [`med-lit-research.md`](med-lit-research.md): the proposed skill assesses an **individual patient's** health literacy and emits a standalone, basic profile. It does not audit a document, compute a document reading grade, build custom HTML, or integrate with `simplify-med` now. The Drive review is a secondary project note; instrument claims below were checked against linked original papers or instrument owners where possible. No instrument has been administered and no patient's level is inferred in this report.

## Recommendation

Build a short, opt-in **screening and support-needs profile** for V1. Use the exact three-item Brief Health Literacy Screen (BHLS) only if the product can present its original items and response choices, record responses without coaching, and validate the proposed chat administration before claiming comparable screening performance. BHLS is attractive because it takes about a minute, produces a published 3–15 *subjective* score, and has evidence from research-assistant and nurse administration. It principally screens difficulty with written health information and forms. It is not a comprehensive measure of finding, appraising, communicating, numeracy, or digital skills. A safer immediate prototype can ask voluntary plain-language questions about the person's preferred language, communication mode, and situations where help would be useful; its output must say **"self-reported support needs; no validated literacy level"**. [D1, P2, P3]

If the product requirement is a broad, named health-literacy *level*, investigate licensing and validity of HLS19-Q12. Its official scoring can yield named categories, but it was developed for population surveys, depends on the healthcare context, and its owner requires a contractual agreement for use. The owner's current conditions restrict use to non-commercial/public-interest settings; a plugin intended for general distribution should not copy the questionnaire or implement its categories without permission and a use-case review. The 44-item HLQ gives a richer nine-domain profile, but requires a license and is too long for this V1. [D1, P6, P7, P8]

Do not convert a free-form chat, a document's FK grade, the patient's education, terminology, or an LLM judgment into a validated health-literacy score. A conversation can observe particular task difficulties and preferences; it cannot establish a person's stable or global level without an appropriate, faithfully administered measure. This is a design inference from the distinction between personal and organizational health literacy, the narrow constructs of the brief screens, and instrument-specific administration and scoring. [P1, D1, P2, P4, P6]

## What is being measured

Healthy People 2030 defines personal health literacy in terms of an individual's ability to find, understand, and use information and services for health decisions and actions. It also defines organizational health literacy separately, and explicitly notes that a person's measured ability is contextual. The Drive review adds access, understanding, appraisal, and application across healthcare, prevention, and promotion. A profile therefore needs to say **which construct** was assessed. The old material-readability recommendation answers a different question. [P1, D1, D2]

| Approach actually found in the supplied Drive review | What a defensible result means | Fit for standalone chat skill |
| --- | --- | --- |
| SILS, one-item self-report screen | Frequency of needing help reading healthcare material; a positive screen suggests possible limited *reading ability*, not a broad health-literacy level. In the original study, “sometimes/often/always” is the positive threshold. [D1, P9] | Very short, but only one narrow signal. Could be a fallback; avoid labels such as “low health literacy” without the qualifier. |
| BHLS, three-item self-report screen | Subjective difficulty with forms and written information; 3–15 after reverse coding the form-confidence item, with higher values indicating fewer reported difficulties. Some primary-care studies used ≤9 as a screen-positive cutoff, but that is population/context-specific rather than a universal grade. [D1, P2, P3] | Best candidate for a brief *screen*, contingent on faithful wording/options, rights review, and chat-mode validation. |
| NVS, six-item performance screen | Performance on nutrition-label reading and arithmetic. Pfizer's toolkit scores 0–1 as high likelihood of limited literacy, 2–3 as possible, and 4–6 as likely adequate **on this screen**. [D1, P4, P5] | Poor fit for unconstrained text chat: the patient must see the actual label while an administrator asks fixed questions orally and withholds answer feedback. A studied computer version required extensive development/validation. |
| S-TOFHLA / TOFHLA; REALM-R | Timed prose task / word-pronunciation performance, respectively; narrower functional constructs. The Drive review lists S-TOFHLA and REALM-R, including face-to-face REALM-R administration. [D1, P2] | Reading passages, timing, pronunciation, and permissions make ordinary chat unsuitable. Do not substitute model judgment for observed performance. |
| HLS19-Q12 | Twelve-item self-report of task difficulty across broader domains. Official factsheet provides a 0–100 dichotomized score with ≥80% valid-response requirement and named categories. Those are *instrument-specific perceived-difficulty categories*, not universal human grades. [D1, P6] | A future option only with owner agreement, complete item set, prescribed scoring, appropriate language, and validation in the intended setting. |
| HLQ | Forty-four items forming nine **independent** scales; a multidimensional needs profile rather than one overall level. [D1, P7, P8] | Rich but burdensome and licensed; future professional/research path. |

The Drive note also names HLS-EU variants and a digital-health-literacy scale. They should not be silently substituted for HLS19-Q12 or assumed to share its scoring. The note's catalog is a lead, not authorization to reproduce instruments. [D1, P6]

## V1 flow and user experience

1. Explain: “I can ask a few questions about how easy it is to use written health information. The result is a brief screen of support needs, not a diagnosis or judgment of intelligence.” Offer “skip” and ask the patient to answer for themself. Ask which language they prefer; only present a validated instrument in an authorized language/version. [P1, P2, P6]
2. Present BHLS items in their established order with their exact five response options, one at a time or together. Do not paraphrase, add examples, translate on the fly, interpret the person's answer, or praise/correct responses between items. If mode, language, or item presentation deviates from the evidence base, record that fact and suppress a validated-level claim. [P2, P3; inference for chat]
3. Confirm the selected responses in a compact recap; allow correction. If an item is missing or ambiguous, retain `not_answered` and withhold the total unless the instrument's scoring rule explicitly permits missing items. Do not guess from conversation history. [P2; design rule]
4. Return a plain Markdown profile: measure/mode/language/date, responses or concise response summary, score if eligible, a carefully scoped interpretation, coverage gaps, and the patient's stated communication preferences or requested supports. Keep task observations separate from BHLS score. No custom HTML, medical advice, or document rewrite. [P1, P2; design recommendation]

Example phrasing for an eligible score: “Your BHLS answers total 11/15. This is a brief self-report screen about written healthcare information; it does not test all health-literacy skills. You said you sometimes have difficulty with [the relevant item].” A cutoff category should be used only after choosing and documenting the target population/administration basis. If the chat mode has not been validated, say “Responses recorded; published BHLS thresholds may not apply to this chat administration.” **The example score is illustrative, not a patient result.** [P2, P3; design inference]

Example no-instrument path: “You prefer spoken explanations in Spanish and want help comparing treatment options. This is a preferences and support-needs profile; no validated literacy level was measured.” That preserves useful downstream information without inventing a metric. [P1; design inference]

## Standalone profile contract (proposal)

The basic output can be Markdown now; internally, keep the following fields so a future consumer can distinguish evidence from interpretation without any current integration:

```text
profile_version: 1
subject: patient_self_report | proxy_report
assessment_date: ISO date
instrument: BHLS | SILS | HLS19-Q12 | none
instrument_version_or_source: citation/identifier
language_and_version: language; validated/authorized status
administration: chat_text | clinician_oral | other; deviations[]
responses: item IDs + exact chosen options + missing status
score: value/range or null; scoring_method; score_eligible: true/false
interpretation: label or null; exact scope; cutoff_source or null
observed_task_needs: []  # separate, nonvalidated observations
patient_preferences: []
coverage_limits: []
```

Keep raw answers optional in the user-facing report and avoid repeating sensitive health details that are unnecessary for the assessment. Any downstream system should use `score_eligible`, instrument, language, and limits before interpreting a number. Do not output a universal `low/medium/high` field that makes different instruments appear interchangeable. [P1, P2, P6, P8; design inference]

## Administration, rights, and uncertainty gates

- **BHLS:** Original validation measured a three-item five-point scale read aloud by trained staff; another study describes self-administration. Thus there is some mode flexibility in evidence, but a conversational assistant that rephrases, probes, infers answers, or gives feedback is a new administration and its cutoff performance is unproven. The published 3–15 scoring is reproducible when exact choices are collected; the screening accuracy and ≤9 cutoff are not automatically portable to all languages, settings, or populations. [P2, P3]
- **NVS:** Pfizer makes English and Spanish toolkits available, but the standard protocol uses a visible label and orally asked questions. Its own material says not to give correctness feedback during the test. The Drive review quotes the developer FAQ: a Canadian computer module performed similarly only after narration, distractor development, user testing, and validation. Text-chat imitation cannot inherit that validation. Check reuse terms before bundling assets. [D1, P4, P5]
- **HLS19-Q12:** The official factsheet's named levels require its exact scoring and enough valid responses; the owner requires an agreement and now states non-commercial/public-interest terms. The factsheet itself says the score reflects interaction between personal ability and context and calls for revalidation in further samples. Do not use its item list from the Drive note as permission. [P6]
- **HLQ:** The original authors describe nine independent indicators; an authorized form/scoring instructions come through licensing. Avoid a single summed “HLQ level.” [P7, P8]
- **SILS / S-TOFHLA / REALM-R:** SILS has an open original publication and is a reading-help screen, but its single answer cannot describe broad competence. S-TOFHLA and REALM-R require task formats that a normal chat cannot faithfully reproduce; confirm publisher/instrument rights before any packaging. [P9, D1, P2]

These are product/research boundaries, not patient diagnoses. Do not infer a literacy deficit from requesting plain language, a non-English language, a disability accommodation, schooling, or a specific medical document. A person's answer may reflect the document or healthcare system as much as personal skill. Prefer supportive language and make the assessment skippable. [P1, P6; design inference]

## Minimal open decisions

1. Is V1 meant to produce an **instrument-based screening result** (BHLS path) or a **non-scored support-needs profile** first? The former needs faithful mode and validation work; the latter can ship without a level claim. [P2, P3]
2. Is use commercial/general-distribution? This determines whether HLS19-Q12 is a viable future path under its current owner conditions and whether any instrument assets may be bundled. [P6]
3. Which patient languages and administration modes are in scope? Each published scoring claim should attach to an actual version and mode, not an ad hoc translation. [P2, P4, P6]

## Evidence ledger

**Drive content read directly**

| ID | Source | What it supports |
| --- | --- | --- |
| D1 | [Health Literacy Review](https://docs.google.com/document/d/1v4ahswueTnQi72EDagXX21haumlaU6hOLBWl8L0siuc/edit), “Main Measures of Health Literacy,” “Tools for measuring comprehension,” “Multidimensional tools” | Internal secondary review of SILS, BHLS, NVS, S-TOFHLA, REALM-R, HLQ, HLS19-Q12, their cited studies and some administration/scoring leads. Original instruments remain authoritative for claims. |
| D2 | [Assessing the Readability of Medical Documents](https://docs.google.com/document/d/1sSPk5w2QhIcwha0QyEaoE1TJfNKaabeN6B3_K5kL1aw/edit), sections 1–5 | Methods for *document* readability and actionability; helps establish that this is a separate task, not evidence for a patient's level. |

**External primary/owner verification**

| ID | Source | What it supports |
| --- | --- | --- |
| P1 | [Healthy People 2030: Health Literacy](https://odphp.health.gov/healthypeople/priority-areas/health-literacy-healthy-people-2030) | Personal vs organizational definitions, contextual nature, point-in-time assessment. |
| P2 | [Wallston et al., BHLS psychometric study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3889960/) | Three items, five choices, read-aloud nurse administration, reverse coding, 3–15 subjective score, comparison with S-TOFHLA; S-TOFHLA categories in that study. |
| P3 | [BHLS primary-care cutoff study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3815081/) and [self-administered comparison study](https://pmc.ncbi.nlm.nih.gov/articles/PMC4987705/) | Example ≤9 screening cutoff in a studied setting; evidence that self-administration has been studied, without establishing this plugin's chat performance. |
| P4 | [Pfizer NVS owner page](https://www.pfizer.com/products/medicine-safety/health-literacy/nvs-toolkit) | English/Spanish availability, six nutrition-label questions, oral administration, label access, roughly three minutes. |
| P5 | [Pfizer NVS toolkit](https://cdn.pfizer.com/pfizercom/health/nvs_flipbook_english_final.pdf) | Standard scoring and qualitative categories; no correctness feedback while testing. |
| P6 | [M-POHL HLS19-Q12 factsheet](https://m-pohl.net/sites/m-pohl.net/files/inline-files/Factsheet%20HLS19-Q12.pdf) and [owner use conditions](https://m-pohl.net/HLS19Instruments) | Twelve-item scoring/categories, context and validation caveats, contractual and non-commercial/public-interest use restrictions. |
| P7 | [Osborne et al., HLQ development](https://pmc.ncbi.nlm.nih.gov/articles/PMC3718659/) | Forty-four items across nine independent indicators. |
| P8 | [Aarhus University HLQ tool page](https://ph.au.dk/research-center-for-health-literacy-and-equity/tools-and-courses/questionnaires-and-tools) | License required for HLQ use. |
| P9 | [Morris et al., SILS original study](https://doi.org/10.1186/1471-2296-7-21) | One-item reading-help screen, response scale/threshold, scope as limited reading ability. |

Evidence limits: the Drive review's survey summaries and quotations are secondary. No original BHLS owner/license policy was located in this pass, so deployment needs a rights check. No chat-specific validation study was found for the proposed flow; this report makes no accuracy claim for it. The readability document contains no individual-assessment instrument.
