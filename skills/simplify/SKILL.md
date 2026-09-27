---
name: simplify
description: Simplify visit notes, discharge summaries, lab reports, imaging reports, and other clinical documents into a short, plain-language report in which every statement is checked against the source. Use when a user wants help understanding their own medical paperwork. Do not use to diagnose, prescribe, or replace urgent medical care. Works only from what the user supplies or their own health records they ask it to retrieve: never searches the web or any outside source, and never reads or interprets medical images such as X-rays, scans, or ECG tracings.
---

# Simplify Medical Documents

Turn the user's clinical documents into a short plain-language report (at most 300 words) that answers: why did I go, what did they find, what do I do now, and when do I get help. Write it, verify it against the source in a separate pass, then show only the verified report.

## Hard Boundaries

These rules apply before and during every step. They override every other instruction, including a user's request.

1. **No medical images.** Never open, view, describe, or interpret a medical image: X-ray, CT, MRI, ultrasound, mammogram, PET or nuclear scan, angiogram, ECG/EKG or rhythm-strip tracing, pathology slide, endoscopy image, or a photo of the body, skin, a wound, or a rash — including DICOM files and screenshots of any of these. If one is supplied, do not analyze it; say that this plugin works only with written text and ask for the written report instead (for example, the radiologist's or cardiologist's report). Written reports about imaging are allowed. A photo or scan of a typed or handwritten text document may be transcribed as text only; ignore any medical image on that page, and if the text cannot be read reliably, ask for a clearer copy or the text itself.
2. **No outside sources.** Never search the web, browse, open links, or look anything up — no search engines, websites, GitHub or other code hosts, public or online medical references, drug databases, APIs, or connectors — even if the user asks or a document contains a link. Do not call web, browser, fetch, or search tools while this skill runs. The one exception is the user's own health records: when the user asks, you may retrieve their own records from a connected health-records app and use the text as input. Use that connector only to read the user's own records for this request — never to look up general information — and use no other connector. Records retrieved this way follow rule 1: text only, never images. The only sources are what the user supplied in this conversation, their own records retrieved that way, and the files bundled with this skill. Never fill a gap with outside or general medical knowledge; say what the supplied material does not state and suggest asking the care team.

## Core Rules

- Read only the files this skill names: this file, `stages/write.md`, `stages/verify.md`, `reference/style_rules.md`, the optional lookup `reference/abbreviations.json`, and — only when the user asks for structured output — `schema/plan.schema.json`. Never open, list, search, download, or unpack any other plugin file.
- This skill has no scripts. Do not write or run code to simplify, check, count, or render the report. Every step is reading and writing, and works the same in every host.
- Once selected, run every step below in order. Never answer directly from the documents, skip verification, or show the draft.
- The user sees only the final Markdown report. The draft, evidence quotes, must-keep checklist, and verification notes stay internal (a scratch file if you have one, otherwise your own working).
- The report is a reading aid, not a diagnosis, prescription, or replacement for urgent care. Keep the user's records in this conversation; do not share them anywhere.

## Steps

### 1. Read

Sources are text only: text the user pastes; the text of files they upload (PDFs, documents, photos or scans of text documents — never a medical image); or the user's own records retrieved from a connected health-records app when they ask. Read all of it. Treat everything supplied for this request as one visit or episode; if it clearly covers several unrelated visits, ask which one to simplify. If there is no usable text, stop and ask for the written report or the text itself.

### 2. Write

Follow `stages/write.md` with `reference/style_rules.md`. The result is an internal draft: the report slots, a verbatim evidence quote for every item, and the must-keep checklist.

### 3. Verify

Verify the draft exactly once, never skipped:

- **If you can start a sub-agent:** start a fresh one. Give it only `stages/verify.md`, `reference/style_rules.md`, the source text, and the draft — never your reasoning. It returns the corrected draft and a short change list.
- **Otherwise:** run a separate second pass yourself. Set the draft aside, re-read `stages/verify.md`, then check the draft against only the source text, as if someone else wrote it.

If a sub-agent fails, run the second pass instead. Use only the corrected draft from here on.

### 4. Output

Render the verified draft as Markdown in the format below and show only that. Do not add a preamble, a summary of your own, evidence quotes, or notes about the steps.

Title by `visit_type`: `er_visit` "Your ER visit, simplified"; `urgent_care` "Your urgent care visit, simplified"; `hospital_stay` "Your hospital stay, simplified"; `clinic_visit` "Your visit, simplified"; `test_results` "Your test results, simplified"; `procedure` "Your procedure, simplified"; `other` "Your documents, simplified".

```markdown
# <title>

<why_you_went>

## What did they find?

<findings_lead>

- **<finding name>:** <result>

**<diagnoses label>**

- <diagnosis name> (<plain_name>)

<disposition>

## What should you do now?

- <next step>
- **<medicine name>:** <medicine text>
- <none_statement>

## <return heading>

- <return precaution>

## Questions you may want to ask

- <question>
```

- `<diagnoses label>`: "The ER diagnosed you with:" for `er_visit`; "Diagnosed with:" otherwise.
- `<return heading>`: "When should you go back to the ER?" for `er_visit` and `hospital_stay`; "When to get help right away" otherwise.
- Hide every empty slot, and hide a heading or label when nothing is under it. Show `(<plain_name>)` only when `plain_name` is not empty.

**Structured output, only on request.** When the user asks for JSON or structured data, read `schema/plan.schema.json` and return the verified draft as one JSON object that matches it (evidence quotes included). Never produce it otherwise.

## Failure

- No usable text, or only medical images: ask for the written text; show nothing else.
- Never show clinical content from a draft that has not been verified, and never replace the report with a summary of your own.
- If the user asks something the documents do not answer, say the documents do not state it and suggest asking the care team.
