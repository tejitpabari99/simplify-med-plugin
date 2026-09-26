# Skill expansion decisions

Updated 2026-09-26 following user clarification. These decisions supersede conflicting recommendations in the initial research reports.

| Decision | Rationale / ownership |
| --- | --- |
| Existing `simplify-med` skill becomes `simplify`. | The user will perform the rename. No plugin-name change is requested. |
| Add `prep` and `med-lit`. | These are the two new skill directions. |
| Remove the separate `ask` direction. | Question generation is part of `prep`; a separate skill duplicates its purpose. The earlier research remains background evidence. |
| `prep` is before the visit. | It understands appointment requirements, guides the patient through questions, covers things to bring, and develops questions to ask. |
| `med-lit` assesses the patient's individual medical/health literacy. | It should produce a level/profile that could later support other workflows. It is not a document-readability calculator. |
| Keep `med-lit` standalone initially. | Downstream adaptation and pipeline integration are deferred. |
| Basic output; no custom HTML. | Keep the first version simple. |
| Defer the features in `futures.md`. | Individual health-literacy profiling is the explicit exception and remains in scope. |
| User owns hands-on testing. | No additional patient/clinician testing approval gate is required for this design work. |

## Research status

- `prep-research.md`: still relevant; expand its scope to appointment requirements and things to bring, and absorb question-generation findings.
- `ask-research.md`: retained as background research only; no separate `ask` implementation is planned.
- `med-lit-research.md`: superseded as the proposed skill direction; it assessed materials rather than patients.
- `med-lit-patient-research.md`: replacement research requested for individual assessment.

## Model preferences

Primary/default: `gpt-6-astra`, medium. Subagents: `gpt-6-sol`, medium.
