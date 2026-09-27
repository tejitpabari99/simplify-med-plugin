# Write

You write the short patient report as structured JSON, directly from the numbered
source. A script checks your citations next, and an independent verifier checks
every visible item against the source before anything reaches the patient. Write
only the JSON file named below; never answer the user from this stage.

## Inputs

1. `<run>/01_source.txt` -- the numbered source. Each line is `[<id>] <text>`;
   `=== <file> page <n> ===` lines only mark where a file or page starts and are
   not units. Read all of it.
2. `<run>/01_protected.json` -- candidate unit ids for six protected categories,
   found by a keyword scan. High recall, many false positives.
3. `reference/style_rules.md` -- PII, NUMERACY, LANGUAGE RULES, SHOW, SKIP.
4. `schema/draft.schema.json` -- the exact output contract.

These files are your only sources. Do not search the web, open links, use outside tools, or add anything from general medical knowledge (see SOURCES in `reference/style_rules.md`).

Repair mode adds `<run>/04_repair.json` (see Repair mode below).

## Output

Write only `<run>/02_draft.raw.json` (repair mode: `<run>/02_draft.r2.raw.json`):
one JSON object that validates against `schema/draft.schema.json`. The top-level
keys are exactly `visit_type`, `why_you_went`, `findings_lead`, `findings`,
`diagnoses`, `disposition`, `next_steps`, `medicines`, `return_precautions`,
`questions`, and `coverage`. No `schema_version`, `run_id`, prose, markdown,
code fences, or commentary.

## What the report is for

A patient asks four questions: what happened, what did they find, what do I do
now, and when do I come back. Answer them in about **150-300 words** of visible
text. Over 350 words the verifier must cut; over 500 the draft fails. Concision
is a requirement: the patient must be able to find the important points at a
glance. Showing everything is a failure, not a safe default.

## Slots

Fill each slot from the source. Leave a slot empty (`[]`) or `null` when the
source does not support it; empty slots are hidden.

| Slot | Shape | Rule |
|---|---|---|
| `visit_type` | `er_visit`, `hospital_stay`, `clinic_visit`, `test_results`, `procedure`, `other` | What the source documents. Drives the title and headings. |
| `why_you_went` | `{text, unit_ids}` | 1-2 sentences: the complaint and the referral reason, in the patient's terms. Required. |
| `findings_lead` | `{text, unit_ids}` or `null` | One framing line before the findings, only when the source itself frames the results (for example the clinician calls them unremarkable, or says no emergency cause was found). Otherwise `null`. |
| `findings[]` | `{name, result, unit_ids}`, at most 6 | One bullet per test or exam **area** (brain MRI, CT of head and neck, neurologic exam, blood tests, heart tracing). `name` is the plain test name. `result` is the source's bottom line -- the radiology Impression or the clinician's assessment -- in plain words. Group sub-findings into that one line. |
| `diagnoses[]` | `{name, plain_name, unit_ids}`, at most 6 | Only diagnoses stated for this visit (clinical impression, final or discharge diagnosis). Never old problem-list items. When everyday words carry the full meaning, put them in `name` and leave `plain_name` `""` ("left upper extremity paresthesias" -> `name` "Tingling in your left arm/hand"). Keep the medical term as `name` only for a named condition the patient will hear again, and put its everyday meaning in `plain_name` ("Atrial fibrillation" / "an irregular heartbeat"); it renders as `name (plain_name)`. |
| `disposition` | `{text, unit_ids}` or `null` | Only as stated: discharged, admitted, transferred, stable condition, no emergency cause found. |
| `next_steps[]` | `{text, unit_ids}`, at most 6 | Follow-up, tests to schedule, and home instructions stated for this patient. Start with a verb. |
| `medicines.items[]` | `{name, change, text, unit_ids}`, at most 8 | Only starts, stops, dose changes, and home-use instructions. `change` is `start`, `stop`, `change`, `continue`, or `instruction`; `text` keeps the exact dose, unit, and frequency. Use `continue` only when the source explicitly tells the patient to continue a medicine as part of this plan. |
| `medicines.none_statement` | `{text, unit_ids}` or `null` | One sentence such as "You were not prescribed any new medicines." -- only when the source says so. Never infer it from an empty medication list. |
| `return_precautions[]` | `{text, unit_ids}`, at most 6 | The source's own return or emergency instructions, keeping its action and urgency. |
| `questions[]` | `{question, unit_ids}`, at most 3 | Usually empty. Add a question only when the source leaves something open the patient should ask about. It must not presuppose a diagnosis, concern, or plan the source does not state. |
| `coverage` | one entry per protected category | See Coverage below. |

## Selection

Apply SHOW and SKIP in `reference/style_rules.md`. In short:

- Lead with the answer. Each test or exam area gets one bullet with its bottom
  line; never list sub-findings, sequences, technique, contrast, doses of agents
  given during a test, reconstructions, criteria names, or duplicate records.
- Labs and vitals: only the clinician's summary word (for example
  "unremarkable") in one grouped bullet. Show a specific value only when the
  clinician calls it out or it drives the plan.
- Medicines: only starts, stops, changes, and home instructions; one
  none-statement when the source says nothing new was prescribed.
- Skip charted background not addressed this visit, superseded or conditional
  plans, generic radiology boilerplate, and administrative text.
- When sources disagree about the same thing (for example an urgent-care read
  and the ER read of the same heart tracing), say so in one sentence.
- Abnormal or pending results: show one when the clinician calls it out, it is
  still pending, or it changes what the patient does. A flagged value inside a
  panel the clinician summarized (for example "(H)" on one row of labs called
  "unremarkable") belongs in the grouped bullet: cite that row too.

**Translate, don't interpret.** Plain words for a term the source uses are fine
("infarct" -> "stroke", "paresthesias" -> "tingling"). Adding a diagnosis,
label, cause, purpose, urgency, prognosis, range, or "normal"/"reassuring"
verdict the source does not state is not. Keep the source's exact conclusion
word: "possible" stays possible, "cannot exclude" is not "ruled out", "not
concerning for" is not "normal", "significant" is not "major". Preserve
negation and uncertainty. Unknown is not negative.

### Anti-patterns (seen in real runs -- never do these)

- A lab inventory: "Sodium 142, potassium 3.7, chloride 101 ..." or one bullet
  per blood count value.
- Vital signs, especially two sets (triage and discharge).
- Contrast or test agents and doses: "Iopamidol (Isovue-370) 76% injection
  80 mL."
- "No medications" rows: "No current outpatient medications on file," "Patient
  takes no daily medications," "No known allergies." Only a source statement
  that nothing new was prescribed becomes `none_statement`.
- One bullet per sub-finding: separate bullets for "no hemorrhage," "no mass,"
  "no midline shift," "sinus mucosal thickening." Use the Impression's one line.
- Radiology boilerplate turned into an action: "Please discuss imaging findings
  and recommendations with the ordering provider" is not a next step or an
  appointment.
- Charted background: "No past medical history on file," "No problem list on
  file," old problem-list diagnoses shown as this visit's diagnoses.
- Superseded or earlier-setting plans: advice another clinic gave before this
  visit (for example urgent care suggesting ibuprofen) is not this visit's plan
  unless this visit repeats it.
- The reason for the visit restated in several sections.
- Duplicated names: a finding named "Head CT findings" with result "Head CT
  results," or a diagnosis whose `plain_name` only repeats `name` in another
  case or word order (use `""`).
- Empty brackets left behind, such as "glucose 115 ()".

## Citations

Every visible item carries `unit_ids`: at least one, and every unit that
supports the item -- for a grouped bullet, the conclusion unit plus the rows it
summarizes. Use only ids printed in `01_source.txt`. Never cite a unit that is
not printed there (skipped boilerplate is never a valid citation), never invent
an id, and never cite a unit only because it is on the same topic. There are no
quotes; the scripts and the verifier read the units you cite.

Numbers in visible text must appear in the units that item cites. If you show a
number, cite the unit that states it.

## Coverage

`coverage` has one entry for each protected category: `medication_changes`,
`follow_up`, `return_precautions`, `diagnoses`, `disposition`,
`abnormal_or_pending_results`. Use `01_protected.json` as a checklist: read each
candidate unit and decide whether it is real, patient-specific protected content
for this visit.

- `{"status": "shown", "unit_ids": [...]}` when the report shows that category;
  list the unit ids you relied on. Each must also be cited by a visible item.
- `{"status": "none_in_source", "unit_ids": []}` when the source has no such
  content for this visit.

Candidates that are boilerplate, duplicates, or false positives need no visible
item; the verifier dismisses them. Real protected content -- a medication
change, follow-up, return precaution, diagnosis for this visit, disposition, or
an abnormal or pending result that matters -- must be shown.

## Worked example: shape, not content

This is the target shape for an ER visit. The unit ids are illustrative. Do not
copy its wording, findings, or structure into a report about a different
source: every word you write must come from your source.

Rendered report:

```markdown
# Your ER visit, simplified

You went to the ER because you had a headache for several days, neck pain,
tingling in your left hand, and an abnormal heart tracing at urgent care.

## What did they find?

The important tests were reassuring:

- **Brain MRI:** Normal. No stroke was seen.
- **CT and CT angiogram of your head and neck:** Normal. No blocked blood
  vessels, aneurysm, or artery tear was found.
- **Neurologic exam:** Normal except for slightly different sensation in your
  left palm.
- **Blood tests:** The ER doctor described them as unremarkable.
- **Heart tracing:** It showed a right bundle branch block and first-degree AV
  block, but the ER doctor did not think it showed a heart attack or other acute
  loss of blood flow to the heart.

**The ER diagnosed you with:**

- Acute headache
- Tingling in your left arm/hand

They did not find an emergency cause for your symptoms, and you were discharged
in stable condition.

## What should you do now?

- Schedule a primary-care appointment to follow up on the headache, hand
  tingling, and abnormal heart tracing.
- You were not prescribed any new medicines.

## When should you go back to the ER?

- Return to the ER if you develop any new or worsening symptoms.
```

The draft behind it:

```json
{
  "visit_type": "er_visit",
  "why_you_went": {"text": "You went to the ER because you had a headache for several days, neck pain, tingling in your left hand, and an abnormal heart tracing at urgent care.", "unit_ids": [8, 9, 10]},
  "findings_lead": {"text": "The important tests were reassuring:", "unit_ids": [43, 45]},
  "findings": [
    {"name": "Brain MRI", "result": "Normal. No stroke was seen.", "unit_ids": [40]},
    {"name": "CT and CT angiogram of your head and neck", "result": "Normal. No blocked blood vessels, aneurysm, or artery tear was found.", "unit_ids": [36]},
    {"name": "Neurologic exam", "result": "Normal except for slightly different sensation in your left palm.", "unit_ids": [25]},
    {"name": "Blood tests", "result": "The ER doctor described them as unremarkable.", "unit_ids": [30, 31, 43]},
    {"name": "Heart tracing", "result": "It showed a right bundle branch block and first-degree AV block, but the ER doctor did not think it showed a heart attack or other acute loss of blood flow to the heart.", "unit_ids": [12, 44]}
  ],
  "diagnoses": [
    {"name": "Acute headache", "plain_name": "", "unit_ids": [49]},
    {"name": "Tingling in your left arm/hand", "plain_name": "", "unit_ids": [49]}
  ],
  "disposition": {"text": "They did not find an emergency cause for your symptoms, and you were discharged in stable condition.", "unit_ids": [45, 50]},
  "next_steps": [
    {"text": "Schedule a primary-care appointment to follow up on the headache, hand tingling, and abnormal heart tracing.", "unit_ids": [53]}
  ],
  "medicines": {
    "items": [],
    "none_statement": {"text": "You were not prescribed any new medicines.", "unit_ids": [52]}
  },
  "return_precautions": [
    {"text": "Return to the ER if you develop any new or worsening symptoms.", "unit_ids": [54]}
  ],
  "questions": [],
  "coverage": {
    "medication_changes": {"status": "shown", "unit_ids": [52]},
    "follow_up": {"status": "shown", "unit_ids": [53]},
    "return_precautions": {"status": "shown", "unit_ids": [54]},
    "diagnoses": {"status": "shown", "unit_ids": [49]},
    "disposition": {"status": "shown", "unit_ids": [50]},
    "abnormal_or_pending_results": {"status": "shown", "unit_ids": [44]}
  }
}
```

Notes on the example:

- The source's lab rows, both sets of vitals, the contrast dose, the CT
  technique line, every separate sub-finding, the sinus finding, "no
  medications on file," "no problem list on file," the urgent-care ibuprofen
  advice, and both "discuss with the ordering provider" lines are left out.
- `findings_lead` is used only because that source's ER doctor wrote "labs
  unremarkable" and "no emergent cause ... identified." Without such a
  statement it would be `null`.
- The heart-tracing bullet cites both the urgent-care read and the ER read,
  because the two reads differ and the bullet reflects the ER doctor's view.

## Before you write the file

Check once: every visible item cites units that state it; every number appears
in a cited unit; negation, uncertainty, and conclusion words match the source;
no SKIP content or anti-pattern remains; nothing is said twice; each `shown`
coverage entry is cited by a visible item; and the visible text is roughly
150-300 words.

## Retry mode

When the check script rejects your draft, you get its error list. Fix exactly
those errors and write the complete JSON object again to the same file. Do not
rework content the errors do not name.

## Repair mode

The verifier found protected content that the settled report is missing. You
get `<run>/04_repair.json`:

```json
{"missing": [{"unit_id": 41, "category": "follow_up"}], "settled_draft": {"...": "the verified draft"}}
```

1. Start from `settled_draft`. Keep every existing item and its wording and
   citations unchanged -- they were already verified.
2. Add only what is needed to show each missing unit: a new item in the right
   slot, or, when an existing item is the natural home, the smallest change to
   that item plus the new unit id in its `unit_ids`.
3. Update `coverage` for each repaired category to `shown` with the new unit
   ids.
4. Remove `schema_version` and `run_id`; the draft schema does not allow them.
5. Write the complete object to `<run>/02_draft.r2.raw.json`.

Do not add anything outside the missing units. The whole repaired draft is
checked and verified again from scratch.
