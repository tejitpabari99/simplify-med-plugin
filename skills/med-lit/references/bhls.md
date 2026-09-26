# Brief Health Literacy Screen (BHLS)

Three self-report items about difficulty with written health information and forms. Present the wording and options exactly as written below, in this order.

Sources: item wording and options as recorded in the project's Health Literacy Review (Sand-Jecklin & Coyle, 2014, *Clinical Nursing Research* 23(6):581–600; Wallston et al., 2014, *J Gen Intern Med* 29(1):119–126). Validation used face-to-face (read aloud by staff) and paper administration; this chat administration is not validated. Confirm instrument rights before any commercial distribution.

## Items

**Item 1 — `bhls_confidence_forms`**
How confident are you filling out medical forms by yourself?

- Extremely
- Quite a bit
- Somewhat
- A little bit
- Not at all

**Item 2 — `bhls_help_reading`**
How often do you have someone help you read hospital materials?

- All of the time
- Most of the time
- Some of the time
- A little of the time
- None of the time

**Item 3 — `bhls_problems_learning`**
How often do you have problems learning about your medical condition because of difficulty understanding written information?

- All of the time
- Most of the time
- Some of the time
- A little of the time
- None of the time

## Scoring

Each item scores 1–5 so that a higher value always means fewer reported difficulties. The confidence item is scored in the opposite direction from the two frequency items.

| Item 1 option | Points | Items 2 and 3 option | Points |
| --- | --- | --- | --- |
| Extremely | 5 | None of the time | 5 |
| Quite a bit | 4 | A little of the time | 4 |
| Somewhat | 3 | Some of the time | 3 |
| A little bit | 2 | Most of the time | 2 |
| Not at all | 1 | All of the time | 1 |

- Total = Item 1 + Item 2 + Item 3. Range 3–15.
- Score only when all three items have exactly one valid option. Otherwise `score` is `null` and `score_eligible` is `false`.
- An item "reports difficulty" when it scores 3 or less.

## Administration rules

- Ask the patient to answer about themself.
- Do not paraphrase items, add examples, explain what an option "means", or suggest an answer.
- Do not comment on answers between items.
- If the patient answers in their own words, accept it only if it clearly equals one option; otherwise repeat the item and options once.
- Record any deviation (paraphrase, translation, proxy answer, inferred answer) in `administration.deviations`. A paraphrased, translated, or inferred item makes the score ineligible.

## Interpretation limits

- The score is a subjective screen of difficulty with written materials and forms. It does not measure numeracy, finding or appraising information, oral communication, or digital skills.
- Published cutoffs (for example 9 or below in some primary-care studies) are population- and mode-specific. Do not apply them as a label to this chat administration.
- Answers can reflect the materials and healthcare system as much as personal skill.

## Single Item Literacy Screener (reference only)

If a patient wants only one question, the SILS (Morris et al., 2006, *BMC Family Practice* 7:21) may be used instead. Wording: "How often do you have someone help you read instructions, pamphlets, or other written material from your doctor or pharmacy?" Options: Never, Rarely, Sometimes, Often, Always. Report the chosen option only; SILS screens need for reading help, not broad health literacy. Record `instrument: SILS` and `score: null`.
