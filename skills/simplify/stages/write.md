# Write

You write the short patient report as an internal draft, directly from the
source text. A separate verification pass checks every item against the source
before anything reaches the patient, so give it what it needs: a verbatim
evidence quote for every item and an honest must-keep checklist. Never show the
draft to the user.

## Inputs

1. The source text: everything the user supplied for this request (pasted
   text, the text of uploaded files, or their own records retrieved from a
   health-records app). Read all of it before you write.
2. `reference/style_rules.md` -- SOURCES, PII, NUMERACY, LANGUAGE RULES, PLAIN
   WORDS, SHOW, SKIP.

Nothing else. Do not search the web, open links, use outside tools, or add
anything from general medical knowledge (see SOURCES in
`reference/style_rules.md`).

## The draft

One JSON object with exactly these keys, in this order: `schema_version`
(always `"4.0"`), `visit_type`, `why_you_went`, `findings_lead`, `findings`,
`diagnoses`, `disposition`, `next_steps`, `medicines`, `return_precautions`,
`questions`, `must_keep`. No other keys. Leave a slot `[]` or `null` when the
source does not support it; empty slots are hidden.

Every visible item has `evidence`: 1-3 short verbatim quotes, copied **character
for character** from the source (up to about 25 words each) that state what the
item says. Quote only what supports the item; never paraphrase, fix spelling,
join separate sentences, or quote a portal header, page counter, URL, or other
boilerplate. Prefer spans without personal names.

| Slot | Shape | Rule |
|---|---|---|
| `visit_type` | `er_visit`, `urgent_care`, `hospital_stay`, `clinic_visit`, `test_results`, `procedure`, `other` | What the source documents. Drives the title and headings. |
| `why_you_went` | `{text, evidence}` | 1-2 sentences in the patient's terms. Keep **every** complaint and referral reason the source lists for this visit (three complaints in the source stay three, including one mentioned only in the history). Required. |
| `findings_lead` | `{text, evidence}` or `null` | One framing line, only when the source itself frames the results (the clinician calls them unremarkable, or says no emergency cause was found). Otherwise `null`. |
| `findings[]` | `{name, result, evidence}`, at most 6 | One bullet per test or exam **area**. `name` is the plain test name. `result` is the source's bottom line (radiology Impression, clinician assessment) in plain words; group sub-findings into that one line. |
| `diagnoses[]` | `{name, plain_name, evidence}`, at most 6 | Only diagnoses stated for this visit. When everyday words carry the full meaning, put them in `name` and leave `plain_name` `""` ("left upper extremity paresthesias" -> "Tingling in your left arm/hand"). Keep a medical `name` only for a condition the patient will hear again; fill `plain_name` only when the source itself states the plain meaning (an education sheet, the discharge instructions, the clinician's words), otherwise `""`. |
| `disposition` | `{text, evidence}` or `null` | Only as stated: discharged, admitted, transferred, stable condition. |
| `next_steps[]` | `{text, evidence}`, at most 6 | Follow-up, tests to schedule, home instructions for this patient. Start with a verb. Keep the source's **timing** ("in 2 to 3 days", "as soon as possible") and its **reason** ("to make sure the pneumonia has cleared") whenever the source gives them. |
| `medicines.items[]` | `{name, change, text, evidence}`, at most 8 | Only starts, stops, dose changes, and home-use instructions. `change` is `start`, `stop`, `change`, `continue`, or `instruction`; `text` keeps the exact dose, unit, frequency, and duration. `continue` only when the source tells the patient to continue a medicine as part of this plan. |
| `medicines.none_statement` | `{text, evidence}` or `null` | "You were not prescribed any new medicines." -- only when the source says so. Never infer it from an empty medication list. |
| `return_precautions[]` | `{text, evidence}`, at most 6 | The source's own return or emergency instructions, keeping its action and urgency. |
| `questions[]` | `{question, evidence}`, at most 3 | Usually empty. Only when the source leaves something open the patient should ask about; never presuppose a diagnosis, concern, or plan the source does not state. |
| `must_keep` | one entry per category | See Must-keep checklist. |

## Selection

Apply SHOW and SKIP in `reference/style_rules.md`. In short:

- Lead with the answer. One bullet per test or exam area with its bottom line;
  never list sub-findings, technique, contrast, doses of agents given during a
  test, criteria names, or duplicate records.
- Labs and vitals: only the clinician's summary word in one grouped bullet; a
  specific value only when the clinician calls it out or it drives the plan.
- **Say each thing once.** A point lives in one slot. "No emergency cause was
  found" goes in `findings_lead` or `disposition`, not both; the reason for the
  visit is not restated in later sections.
- When sources disagree about the same thing (an urgent-care read and the ER
  read of the same heart tracing), say so in one sentence.
- Abnormal or pending results: show one when the clinician calls it out, it is
  still pending, or it changes what the patient does. For a pending result,
  keep when and how the source says the patient will hear about it.

**Translate, don't interpret.** Swapping a term for the everyday words that
mean the same thing is translation and is fine ("infarct" -> "stroke",
"paresthesias" -> "tingling", "right lower lobe" -> "lower part of your right
lung"). Adding what a condition is, why it happens, what it implies, or a label,
cause, purpose, urgency, prognosis, range, or "normal"/"reassuring" verdict the
source does not state is interpretation and is not allowed. Keep the source's
exact conclusion word: "possible" stays possible, "cannot exclude" is not
"ruled out", "not concerning for" is not "normal". Preserve negation and
uncertainty. Unknown is not negative.

**Terms.** Write a clinical abbreviation in full the first time; if the report
uses it again, add the short name in parentheses and use the short name after
that ("first-degree atrioventricular (AV) block", then "AV block"). Names
patients already know (ER, CT, MRI, COVID-19) stay as they are. Never expand a
short name into a longer, harder word for no gain. Never leave jargon
unexplained: if a term ("ST changes") cannot be put in plain words from the
source, state what the source concluded about it instead and leave the term
out.

### Anti-patterns (seen in real runs -- never do these)

- A lab inventory ("Sodium 142, potassium 3.7 ...") or one bullet per value.
- Vital signs, especially two sets.
- Contrast or test agents and doses ("Iopamidol 76% injection 80 mL").
- "No medications" rows: "No current outpatient medications on file," "No
  known allergies." Only a statement that nothing new was prescribed becomes
  `none_statement`.
- One bullet per sub-finding instead of the Impression's one line.
- Radiology boilerplate turned into an action ("discuss imaging findings with
  the ordering provider" is not a next step).
- Charted background ("No past medical history on file"), old problem-list
  diagnoses shown as this visit's.
- Superseded or earlier-setting plans (another clinic's earlier advice) shown
  as this visit's plan.
- The same point said twice (findings lead and disposition both saying "no
  emergency cause").
- A follow-up without the timing or reason the source gave ("Schedule a
  follow-up" when the source says "as soon as possible to recheck ...").
- A complaint dropped from `why_you_went`.
- A duplicated name ("Head CT findings" / "Head CT results") or a `plain_name`
  that only repeats `name`.
- Empty brackets left behind ("glucose 115 ()").

## Must-keep checklist

`must_keep` has one entry per category: `medication_changes`, `follow_up`,
`return_precautions`, `diagnoses`, `disposition`,
`abnormal_or_pending_results`. Search the whole source for each one before you
decide. Set `"shown"` when a visible item shows that content, or
`"none_in_source"` only when the source truly has none for this visit. Real
must-keep content is always shown: a medicine started, stopped, or changed;
follow-up with its timing and reason; return precautions; this visit's
diagnoses; the disposition; an abnormal or pending result that matters.

## Worked example: shape, not content

A synthetic urgent-care visit. It shows the shape, a medicine change, a timed
follow-up with its reason, and a pending result. Do not copy its wording,
findings, or structure into a report about a different source: every word you
write must come from your source.

Source (synthetic):

```text
Lakeside Urgent Care | Patient Portal | Page 1 of 1
Patient: Sample Patient  DOB: 01/01/1980  MRN: 000000
Chief complaint: Cough for 5 days, fever, and right-sided chest pain when taking a deep breath.
HPI: Also reports feeling short of breath when climbing stairs.
Vitals: T 101.2 F, HR 104, BP 128/82, RR 20, SpO2 95% on room air.
Allergies: No known drug allergies.
Exam: Crackles over the right lower lung field.
Chest X-ray, 2 views. Technique: PA and lateral.
IMPRESSION: Right lower lobe pneumonia. No pleural effusion.
Rapid influenza A/B: negative.
COVID-19 PCR: pending. Results in 1-2 days. We will call you only if the result is positive.
Assessment: Right lower lobe pneumonia.
Plan: Start amoxicillin 1000 mg PO TID x 5 days.
Take acetaminophen 650 mg every 6 hours as needed for fever.
Follow up with your primary care provider in 2 to 3 days to make sure you are improving.
Repeat chest X-ray in 6 to 8 weeks to make sure the pneumonia has cleared.
Disposition: Discharged home in stable condition.
Go to the nearest emergency room or call 911 if you have trouble breathing, chest pain that gets worse, confusion, or bluish lips.
Call the clinic if your fever is not better after 3 days of antibiotics.
Patient education: Pneumonia is an infection in one or both lungs.
Patient education: Wash your hands often to help prevent the spread of germs.
Electronically signed by Dr. Jane Sample, MD
```

Draft:

```json
{
  "schema_version": "4.0",
  "visit_type": "urgent_care",
  "why_you_went": {"text": "You went to urgent care because you had a cough for 5 days, a fever, pain on the right side of your chest when you took a deep breath, and shortness of breath when climbing stairs.", "evidence": ["Cough for 5 days, fever, and right-sided chest pain when taking a deep breath.", "feeling short of breath when climbing stairs"]},
  "findings_lead": null,
  "findings": [
    {"name": "Chest X-ray", "result": "Pneumonia in the lower part of your right lung.", "evidence": ["IMPRESSION: Right lower lobe pneumonia."]},
    {"name": "Flu test", "result": "Negative.", "evidence": ["Rapid influenza A/B: negative."]},
    {"name": "COVID-19 test", "result": "Not back yet. Results should come in 1 to 2 days. The clinic will call you only if it is positive.", "evidence": ["COVID-19 PCR: pending. Results in 1-2 days. We will call you only if the result is positive."]}
  ],
  "diagnoses": [
    {"name": "Pneumonia", "plain_name": "an infection in one or both lungs", "evidence": ["Assessment: Right lower lobe pneumonia.", "Pneumonia is an infection in one or both lungs."]}
  ],
  "disposition": {"text": "You were sent home in stable condition.", "evidence": ["Discharged home in stable condition."]},
  "next_steps": [
    {"text": "Schedule a visit with your primary care provider in 2 to 3 days to make sure you are getting better.", "evidence": ["Follow up with your primary care provider in 2 to 3 days to make sure you are improving."]},
    {"text": "Get a repeat chest X-ray in 6 to 8 weeks to make sure the pneumonia has cleared.", "evidence": ["Repeat chest X-ray in 6 to 8 weeks to make sure the pneumonia has cleared."]}
  ],
  "medicines": {
    "items": [
      {"name": "Amoxicillin", "change": "start", "text": "Start taking 1000 mg by mouth three times a day for 5 days.", "evidence": ["Start amoxicillin 1000 mg PO TID x 5 days."]},
      {"name": "Acetaminophen", "change": "instruction", "text": "Take 650 mg every 6 hours as needed for fever.", "evidence": ["Take acetaminophen 650 mg every 6 hours as needed for fever."]}
    ],
    "none_statement": null
  },
  "return_precautions": [
    {"text": "Go to the nearest ER or call 911 if you have trouble breathing, chest pain that gets worse, confusion, or bluish lips.", "evidence": ["Go to the nearest emergency room or call 911 if you have trouble breathing, chest pain that gets worse, confusion, or bluish lips."]},
    {"text": "Call the clinic if your fever is not better after 3 days of antibiotics.", "evidence": ["Call the clinic if your fever is not better after 3 days of antibiotics."]}
  ],
  "questions": [],
  "must_keep": {
    "medication_changes": "shown",
    "follow_up": "shown",
    "return_precautions": "shown",
    "diagnoses": "shown",
    "disposition": "shown",
    "abnormal_or_pending_results": "shown"
  }
}
```

Rendered report:

```markdown
# Your urgent care visit, simplified

You went to urgent care because you had a cough for 5 days, a fever, pain on the right side of your chest when you took a deep breath, and shortness of breath when climbing stairs.

## What did they find?

- **Chest X-ray:** Pneumonia in the lower part of your right lung.
- **Flu test:** Negative.
- **COVID-19 test:** Not back yet. Results should come in 1 to 2 days. The clinic will call you only if it is positive.

**Diagnosed with:**

- Pneumonia (an infection in one or both lungs)

You were sent home in stable condition.

## What should you do now?

- Schedule a visit with your primary care provider in 2 to 3 days to make sure you are getting better.
- Get a repeat chest X-ray in 6 to 8 weeks to make sure the pneumonia has cleared.
- **Amoxicillin:** Start taking 1000 mg by mouth three times a day for 5 days.
- **Acetaminophen:** Take 650 mg every 6 hours as needed for fever.

## When to get help right away

- Go to the nearest ER or call 911 if you have trouble breathing, chest pain that gets worse, confusion, or bluish lips.
- Call the clinic if your fever is not better after 3 days of antibiotics.
```

Notes on the example:

- Left out: the portal header and page counter, the patient identifiers, the
  vital signs, "No known drug allergies", the exam's crackles and the X-ray
  technique (sub-findings), "No pleural effusion" (a sub-finding the
  Impression's bottom line does not need), the hand-washing sheet (generic
  education), and the signing doctor's name.
- `why_you_went` keeps all four complaints, including the one from the HPI.
- `plain_name` is filled only because the source's education sheet states what
  pneumonia is. Without that sentence it would be `""`.
- "TID" becomes "three times a day" (translation); every digit in an item is in
  its evidence quote.
- Both next steps keep the source's timing and reason; the pending COVID-19
  result keeps when and how the patient will hear.
- No point is repeated: the disposition is said once, and nothing restates why
  the patient came.

## Before you hand the draft to verification

Check once: every item has evidence quoted character for character; every
number is in its item's evidence; negation, uncertainty, and conclusion words
match the source; every complaint is in `why_you_went`; next steps keep timing
and reason; nothing is said twice; no SKIP content or anti-pattern remains;
`must_keep` is honest; and the rendered report is at most 300 words.
