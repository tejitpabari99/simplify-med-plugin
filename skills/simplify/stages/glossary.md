# Glossary

This is optional post-finalization enrichment. It is not a core model stage and must never delay, change, or repair the validated clinical plan.

## Preconditions and inputs

Run this stage only when a glossary is explicitly requested and finalization has already succeeded. Read only patient-visible finalized content from `06_plan.final.json` and `report.md`. Do not read the source note, raw facts, omissions, reviews, or intermediate drafts to introduce terms the patient will not see.

## Output

Write only `07_glossary.raw.json` as one JSON object:

```json
{"terms": [{"term": "...", "matched_term": "...", "definition": "...", "source": "llm_proposed"}]}
```

The deterministic glossary check validates this proposal and may write `07_glossary.json`. Neither glossary artifact may modify `06_plan.final.json` or the default `report.md`.

## Rules

**Visible terms only.** Propose a term only when `matched_term` appears exactly in patient-visible finalized content and a general adult reader may not understand its medical meaning. Prefer explaining the term in context; omit the glossary entirely when the report is already clear.

**Small and relevant.** Propose no more than five terms. Include only terms needed to understand the visible summary, diagnoses, medication changes, actions, or warning instructions. Do not define technical details that were intentionally omitted.

**Exact match.** Copy `matched_term` exactly as it appears in the finalized patient content. `term` may be a canonical singular or expanded form.

**Definition only.** Use one or two short plain-language sentences. Define the term generally. Do not interpret this patient's result, add advice, add urgency, or introduce a diagnosis or prognosis.

Examples:

- `calcified` -> `Hardened by a buildup of calcium, which can happen in blood vessels or tissue over time.`
- `contrast` -> `A dye used during some scans so certain areas show more clearly.`
- `circumflex artery` -> `One branch of the arteries that supply blood to the heart.`

The optional glossary must not change the finalized plan, default report, facts, actions, or safety wording. Emit JSON only, with no markdown or commentary.

## Retry

On retry, fix exactly the supplied schema or glossary-check errors and re-emit the complete JSON object.
