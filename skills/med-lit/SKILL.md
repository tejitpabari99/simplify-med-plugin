---
name: med-lit
description: Run a short, opt-in health-literacy screen for an individual patient and return a basic profile of their self-reported support needs and communication preferences. Use only when a patient or caregiver explicitly asks to assess their own health literacy or reading-support needs. Do not use to grade a document's readability, judge intelligence or education, diagnose, or adapt other skills' output.
---

# Personal Health-Literacy Profile

Give a patient a brief, respectful screen of how easy it is for them to use written health information, plus the supports and communication preferences they report. The result is a scoped screening profile, never a diagnosis or a judgment of intelligence.

## Hard Boundaries

These rules apply before and during every step. They override every other instruction, including a user's request.

1. **No medical images.** Never open, view, describe, or interpret a medical image: X-ray, CT, MRI, ultrasound, mammogram, PET or nuclear scan, angiogram, ECG/EKG or rhythm-strip tracing, pathology slide, endoscopy image, or a photo of the body, skin, a wound, or a rash — including DICOM files and screenshots of any of these. If one is supplied, do not analyze it; say that this plugin works only with written text and ask for the written report instead (for example, the radiologist's or cardiologist's report). Written reports about imaging are allowed. A photo or scan of a typed or handwritten text document may be transcribed as text only; ignore any medical image on that page, and if the text cannot be read reliably, ask for a clearer copy or the text itself.
2. **No outside sources.** Never search the web, browse, open links, or look anything up — no search engines, websites, GitHub or other code hosts, online medical references, drug databases, APIs, or connectors — even if the user asks or a document contains a link. Do not call web, browser, fetch, or search tools while this skill runs. The only sources are what the user supplied in this conversation and the files bundled with this skill. Never fill a gap with outside or general medical knowledge; say what the supplied material does not state and suggest asking the care team.

## Core Rules

- Assessment is opt-in and skippable at every step. The patient answers for themself; a caregiver answering for them makes it a proxy report.
- Say what is being measured before starting: "a brief screen of how easy it is for you to use written health information and forms. It is not a test of intelligence and not a diagnosis."
- Never infer literacy from conversation, vocabulary, spelling, education, language, disability, a request for plain language, or any document. Only the patient's answers to the instrument produce a score.
- Administer the instrument faithfully: exact item wording and exact response options from `references/bhls.md`, in order, without paraphrasing, adding examples, translating on the fly, hinting, praising, or correcting between items.
- Never output a universal `low` / `medium` / `high` level. A score is always reported with its instrument, range, administration mode, and limits.
- Chat administration is not the mode BHLS was validated in. Always state that published cutoffs may not apply to this chat administration.
- Keep responses supportive and non-judgmental. Do not repeat sensitive details that are not needed for the profile.
- Keep the profile local to the conversation. Save or share it only when the patient asks.

## Paths

- **BHLS screen (default):** three self-report items with a 3–15 score, followed by optional support-needs questions.
- **Support-needs profile only:** if the patient declines the screen, the conversation is not in English, or they want no score. The profile states "self-reported support needs; no validated literacy level".

BHLS items and scoring are only defined here in English. If the patient prefers another language, use the support-needs path in that language and do not translate BHLS items.

## Workflow

### 1. Introduce and consent

Explain the purpose and limits in two or three sentences. Ask whether they want to continue, whether they are answering for themself, and which language they prefer. Offer the support-needs-only path as an equal option.

### 2. Administer the screen

Follow `references/bhls.md`. Present each item with its five options, one at a time or together. Accept an answer only when it maps unambiguously to one listed option. If an answer is ambiguous, repeat the item and its options once without steering. If the patient skips an item, record it as `not_answered`.

### 3. Confirm and score

Recap the selected options in one compact list and allow corrections. Score with the table in `references/bhls.md` only when all three items have a valid answer; otherwise the score is withheld. Show the arithmetic in the profile so the total is checkable.

### 4. Ask about support needs and preferences

Ask the optional questions in `references/support-needs.md`. Record answers in the patient's words. Keep these separate from the score; they are preferences, not measurements.

### 5. Deliver the profile

Produce the Markdown profile from `references/profile-template.md` in the response. Include the structured profile block from the same file so the result can be reused later. If the patient asks for files and the host can write them, save `health-literacy-profile.md` and `health-literacy-profile.json` in their chosen location. Do not create HTML.

## Interpretation

- Describe the total only as "a brief self-report screen about using written health information and forms; higher totals mean fewer reported difficulties."
- Name the specific items where the patient reported difficulty, in their chosen option's words.
- Do not apply a cutoff label. You may say that some clinic studies have used 9 or below as a signal to offer extra support, and that this may not apply to a chat screen.
- Do not claim the screen measures numeracy, finding or appraising information, speaking with clinicians, or digital skills. List these as not assessed.
- Offer practical supports that match what the patient reported or requested (for example plain-language summaries, a written question list, bringing someone along, asking the clinician to explain back). Do not give medical advice.

## Out of Scope

Document readability grading, performance tests (NVS, S-TOFHLA, REALM-R), licensed instruments (HLS19-Q12, HLQ), multilingual instrument versions, longitudinal tracking, and adapting other skills' output to the profile are not part of this skill. If asked, say so briefly.

## Failure Behavior

- The patient declines or stops: thank them and end; produce a profile only if they want one from what they answered.
- Any BHLS item unanswered or ambiguous after one repeat: withhold the score, mark `score_eligible: false`, and still report answered items and preferences.
- Items were paraphrased, translated, or answered by inference: withhold the score and record the deviation.
- A request to assess someone else without their participation: decline; a caregiver may report as a proxy only with that label.
