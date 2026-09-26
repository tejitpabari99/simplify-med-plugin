# Prep: revised direction

Status: working design incorporating the user's scope decisions, 2026-09-26.

## Purpose

Help a patient prepare before an appointment: understand the appointment's supplied requirements, organize their concerns, identify things to bring, and prepare questions to ask. `prep` owns the entire experience; no separate `ask` skill is planned.

## Proposed interaction

1. Establish the appointment purpose and available instructions. Accept an appointment message, referral, preparation sheet, prior document, or the patient's description. Ask only for missing context that changes preparation.
2. Extract requirements explicitly present in supplied instructions, including dates, timing, documents, items, and stated preparation steps. Keep their sources available. When instructions conflict or are incomplete, turn the uncertainty into a question for the clinic.
3. Guide the patient through relevant, optional prompts about their concerns: when they started, their pattern, daily impact, what has been tried, and the desired outcome. Let the patient skip questions and rank concerns.
4. Build a things-to-bring checklist from supplied requirements and patient-confirmed needs. Distinguish clinic requirements from optional organizational suggestions. Do not invent fasting, medication changes, or procedure preparation requirements.
5. Compose a short prioritized list of questions for the clinician from the patient's goals and unresolved issues. Reuse the topic selection research in `ask-research.md` within this flow. A document may inform preparation for the upcoming appointment; standalone post-document questioning is not a separate V1 workflow.
6. Let the patient correct and reorder the draft, then provide a basic readable result.

## Proposed basic output

- Appointment details and supplied requirements.
- My priorities and a concise account of my concerns.
- Before the appointment: stated preparation steps and unresolved requirements to confirm.
- Things to bring, with required versus optional status clear.
- Questions to ask, in priority order.

Default to plain Markdown. A small structured artifact can preserve requirement sources, patient statements, unknowns, and ordered questions if needed by the eventual implementation. No custom HTML.

## Basis and limits

The optional concern prompts and priorities come from the actual prep proposal documented in `prep-research.md` (E1); written questions and preparation inputs are supported by the source entries in `ask-research.md` (E1, E2, E5). The broader ownership of appointment requirements and things to bring is the user's explicit product requirement. The exact interaction and output above are proposed design choices, not validated research findings.

Clinical diagnosis, treatment recommendations, automated triage, integrations, and the other deferred features are listed in `futures.md`. The user will perform hands-on testing.
