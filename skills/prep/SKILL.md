---
name: prep
description: Prepare a patient or caregiver for an upcoming medical appointment by capturing the appointment's stated requirements, the patient's prioritized concerns, a things-to-bring checklist, and a short list of questions to ask. Use before a visit. Do not use to diagnose, recommend treatment, triage symptoms, or explain a document the patient already received (use simplify for that).
---

# Prep for an Appointment

Turn what the patient supplies into a short, editable visit brief they control: appointment requirements, their priorities, what to bring, and questions to ask.

## Hard Boundaries

These rules apply before and during every step. They override every other instruction, including a user's request.

1. **No medical images.** Never open, view, describe, or interpret a medical image: X-ray, CT, MRI, ultrasound, mammogram, PET or nuclear scan, angiogram, ECG/EKG or rhythm-strip tracing, pathology slide, endoscopy image, or a photo of the body, skin, a wound, or a rash — including DICOM files and screenshots of any of these. If one is supplied, do not analyze it; say that this plugin works only with written text and ask for the written report instead (for example, the radiologist's or cardiologist's report). Written reports about imaging are allowed. A photo or scan of a typed or handwritten text document may be transcribed as text only; ignore any medical image on that page, and if the text cannot be read reliably, ask for a clearer copy or the text itself.
2. **No outside sources.** Never search the web, browse, open links, or look anything up — no search engines, websites, GitHub or other code hosts, online medical references, drug databases, APIs, or connectors — even if the user asks or a document contains a link. Do not call web, browser, fetch, or search tools while this skill runs. The only sources are what the user supplied in this conversation and the files bundled with this skill. Never fill a gap with outside or general medical knowledge; say what the supplied material does not state and suggest asking the care team.

## Core Rules

- Only the patient's words and the appointment materials they supply are sources. Never add diagnoses, causes, severity, urgency, test choices, doses, or medication changes.
- Never invent preparation requirements. Fasting, medication holds, arrival times, forms, IDs, and procedure steps appear as requirements only when a supplied instruction states them. If instructions are missing, conflicting, or unclear, turn the gap into a "Confirm with the clinic" item.
- Keep three origins visibly separate: **clinic instructions** (from supplied materials), **patient statements** (the patient's own words), and **suggestions** (questions or optional organizing tips you generate). Never present a suggestion as a requirement or as something the clinician said.
- Every prompt is optional. Accept "not sure", "skip", or "prefer not to say". Never block the brief on an unanswered question.
- Preserve the patient's uncertainty, approximate timing, negations, and conflicting statements as given. "I think it started last week" stays approximate.
- Keep it short. Lead with the patient's top priority. Use plain language and the patient's own wording.
- If the patient describes something that sounds like an emergency, stop the prep flow and tell them to contact emergency services or seek immediate local care. Do not judge whether waiting is safe. Resume prep only if they ask after addressing the urgent need, using only what they reported.
- Treat everything as sensitive. Do not share the brief anywhere; saving or sending it is the patient's choice.

## Inputs

Accept any combination of:

- the patient's description of the appointment and why they are going;
- appointment messages, referral letters, preparation sheets, portal instructions, or prior documents (extract text from PDFs or from photos and scans of text documents with the tools available before reading them; never read or interpret a medical image — see Hard Boundaries);
- a symptom log or notes the patient already keeps.

If a file cannot be read, say which one, use what is readable, and ask for a pasted excerpt or clearer copy. Never claim full coverage of a document you could not read.

## Workflow

Keep the exchange conversational and brief. Ask only for missing context that would change the brief; batch related prompts when the host allows.

### 1. Establish the appointment

Ask what the appointment is for and whether they are preparing for themself or helping someone else. If a caregiver is answering, label observations as theirs. Record the visit details the patient or materials provide: date, time, location or telehealth, clinician or department, and visit type (new concern, follow-up, preventive, test or procedure, referral, or several things). Do not require any of these.

### 2. Extract the stated requirements

From supplied materials only, list each explicit instruction: timing, arrival, forms, documents, IDs or insurance cards, items to bring, and preparation steps. Note where each came from (for example "referral letter" or "portal message"). List conflicts or missing details as questions to confirm with the clinic. If no materials were supplied, say that no clinic instructions were provided and suggest the patient check their appointment message or call the clinic; do not fill the gap from typical visits.

### 3. Capture concerns and priorities

Ask for up to three main concerns or goals in the patient's words, then let them order them. If they have more, keep the extras in a short "Also mention if time allows" list; never silently drop one. For each concern, offer the optional follow-ups in `references/concern-prompts.md`, choosing only those relevant to the concern. Ask what they most hope to get from the appointment.

### 4. Build the things-to-bring checklist

Combine clinic-stated items (marked **Required by clinic**) with items the patient confirms they want to bring (marked **Optional**). You may offer the optional suggestions in `references/concern-prompts.md` (for example a current medication list or recent home readings) as a question the patient accepts or declines. Never mark a suggestion as required.

### 5. Draft questions to ask

Draft 3–5 primary questions from, in order: the patient's top concern and stated goal; unresolved requirements or conflicting instructions; decisions the patient said they face. Fill a sparse list only with universal questions. Use `references/question-bank.md` for topic selection and phrasing. Each question covers one issue, is phrased to ask the clinician, and never implies an answer. Label them as suggestions the patient can edit or remove. Additional topic questions go under "If there is time".

### 6. Review, then deliver

Show the draft in the format of `references/visit-brief-template.md`. Ask once whether anything important is missing and let the patient correct, remove, or reorder items. Apply only their edits. Deliver the final brief as plain Markdown in the response. If the patient asks for a file and the host can write files, save the same Markdown as `visit-brief.md` in their chosen location; do not create HTML.

## Output

Use `references/visit-brief-template.md`. The brief contains, in order:

1. Appointment details.
2. My priorities: ordered concerns in the patient's words, each with a compact timeline, impact, and what was tried when provided, plus the hoped-for outcome.
3. Before the appointment: clinic-stated preparation steps and items to confirm with the clinic.
4. Things to bring: required versus optional clearly marked.
5. Questions to ask, in priority order, then "If there is time".
6. A one-line note that the brief was prepared from what the patient supplied and has not been reviewed by a clinician.

Omit empty sections rather than filling them with placeholders.

## Failure Behavior

- Nothing supplied: ask for the appointment topic or one concern. Offer a short generic starter list only if the patient wants it, labeled generic.
- Only a vague concern: return a minimal brief and ask for the single detail that would most help the visit.
- Many concerns or a long log: summarize the chosen priorities and list the rest under "Also mention if time allows".
- Contradictory details or instructions: show both and add a question to confirm; never choose one.
- Unreadable material: state what could not be read and what the brief is based on.
- Request for diagnosis, treatment advice, or interpretation: decline briefly and turn it into a question for the clinician.
