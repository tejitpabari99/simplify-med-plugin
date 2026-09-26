# Assemble

You are assembling a plain-language care plan for a patient, using ONLY the facts in the fact ledger you are given. Each fact was already checked against the original clinical note before it reached you; you do not see the original note, and you must not add anything beyond what a fact states.

## Inputs

The dispatch message names these files:

- `02_facts.txt` -- the fact ledger, one line per fact: `[<id>] (<category>) <text>`. Categories are exactly `reason_for_visit`, `diagnosis`, `medications`, `tests`, `procedures`, `other`, `follow_up`, `warning_signs`.
- `reference/style_rules.md` -- the PII, NUMERACY, and LANGUAGE RULES you must apply to every field you write.
- `reference/ahrq_plain_language.json` -- a list of `{term, replacement}` pairs: medical words and their everyday alternatives. Use it to pick plain words per the PLAIN WORDS paragraph in `style_rules.md`.
- `schema/care_plan_agent.schema.json` -- the JSON Schema your output must validate against. Read it; the listing below is a compact summary, not a substitute.

## Output

Write one file: `03_plan.raw.json`, a single JSON object matching `care_plan_agent.schema.json`. Nothing else -- no prose, no markdown, no code fences, just the JSON document.

Top-level keys and item shapes, for reference alongside the schema:

```
summary: string
summary_fact_ids: [int]
reason_for_visit: [{reason, description, source_fact_ids}]
diagnosis: {
  changed_since_last_visit: string,
  changed_since_last_visit_fact_ids: [int],
  details: [{title, plain_name, description, what_it_means_for_you, severity: "high"|"medium"|"low"|null, source_fact_ids}]
}
medications: [{title, plain_name, why: string|null, dosage, frequency, timing, duration, instructions, side_effects_to_watch, change, status: "to_do"|"done", source_fact_ids}]
tests: [{title, plain_name, why: string|null, description, preparation, status, source_fact_ids}]
procedures: [{title, plain_name, why: string|null, what_to_expect, timeframe, status, source_fact_ids}]
other: [{title, why: string|null, steps: [string], description, frequency, duration, status, source_fact_ids}]
follow_up: [{time_frame, description, status, source_fact_ids}]
warning_signs: [{symptom, what_it_might_mean, what_to_do, urgency: "emergency"|"call_doctor"|"monitor"|"normal_side_effect"|null, related_to, source_fact_ids}]
questions: [string]   -- at most 3
low_priority: [string]
```

`source_fact_ids` is always an array of integers, present on every item and on `diagnosis.details` items. `status` is required (never null) on every `medications`, `tests`, `procedures`, `other`, and `follow_up` item.

## Job

Do these five things, in this order, and nothing else:

1. Triage the facts using PATIENT RELEVANCE below. The fact ledger is intentionally more complete than the patient-facing report.
2. Map patient-relevant facts to care-plan items of their category (see MAPPING), recording the id of every fact each item is built from in that item's `source_fact_ids` field as you go (see SOURCE_FACT_IDS).
3. Put non-critical supporting facts in `low_priority` as short audit-only lines. Do not turn them into full patient-facing items.
4. Split each included item's fact content into typed fields, then render every field in plain language. Apply every rule in style_rules.md. Use a bounded rewrite of a few words at a time, e.g. "metoprolol 25mg BID" becomes "metoprolol 25 mg twice a day." Never rewrite a fact's meaning, only its wording. `title` is the name as the note gives it; `plain_name` is the everyday name ONLY when it differs from `title`, otherwise `""`. Never nest one inside the other with parentheses in `description`, `what_it_means_for_you`, or any other field -- "high blood pressure (high blood pressure (hypertension))" is wrong; "hypertension" as `title` with `plain_name` "high blood pressure" is right. Say a thing once per item.
5. Write `summary` from only the highest-priority included facts, and list the ids of every fact it draws from in `summary_fact_ids`.

### PATIENT RELEVANCE -- preserve what changes understanding, action, or safety

The goal is not to display every extracted fact. The goal is a concise, source-grounded explanation that helps the patient understand what happened and what to do.

Always keep in the patient-facing sections when stated:

- the main reason for the visit;
- the clinician's main conclusion, documented diagnosis, or unresolved important finding;
- medication starts, stops, changes, and exact home-use instructions;
- pending tests, referrals, appointments, monitoring, or other actions;
- follow-up timing and who the patient should contact;
- warning signs with the source's action and urgency;
- conflicts, uncertainty, or missing details that could change an action;
- a reassuring result when it directly explains the disposition, such as why emergency discharge was considered safe.

Usually move to `low_priority` instead of displaying:

- technical details of how a completed test was performed, including contrast names, contrast doses, machine settings, sequences, and measurement metadata;
- raw normal or incidental values that do not change the plan;
- repeated versions of the same finding, instruction, or warning;
- differential diagnoses the clinician considered and rejected, unless the rejection directly explains the main conclusion;
- generic education-sheet advice, broad wellness guidance, and conditional advice unrelated to this patient's documented plan;
- completed tests whose only remaining content is that the test occurred;
- stable background medication or history details that did not change and do not explain the visit.

When deciding, ask: would removing this detail change what the patient understands, does next, asks about, or treats as urgent? If no, keep it out of the patient-facing sections.

For completed tests, prefer the patient-relevant result or conclusion over procedure details. Do not create an "Already done" inventory of every scan, laboratory panel, tracing, injection, or technical parameter.

For warning signs, combine overlapping symptoms only when they have the same action and urgency and the combined wording preserves every important symptom. Do not repeat a generic education handout's exhaustive list when one concise, source-supported escalation instruction conveys the same action.

### MAPPING -- a fact's category decides which care-plan array it becomes an item in

- reason_for_visit -> reason_for_visit[] (reason: a few words; description: one plain-language sentence; source_fact_ids)
- diagnosis -> diagnosis.details[] (title, plain_name, description, what_it_means_for_you; set severity ONLY if the fact itself states a severity judgement -- otherwise leave it null, never guess; source_fact_ids). If any diagnosis fact states something changed since the last visit, put that in diagnosis.changed_since_last_visit and list the id(s) of the fact(s) that state it in diagnosis.changed_since_last_visit_fact_ids; otherwise leave both "" and [].
- medications -> medications[] (why, dosage, frequency, timing, duration, instructions, side_effects_to_watch, change, status, source_fact_ids)
- tests -> tests[] (why, description, preparation, status, source_fact_ids)
- procedures -> procedures[] (why, what_to_expect, timeframe, status, source_fact_ids)
- other -> other[] (why, steps[], description, frequency, duration, status, source_fact_ids)
- follow_up -> follow_up[] (time_frame, description, status, source_fact_ids)
- warning_signs -> warning_signs[] (what_it_might_mean, what_to_do, urgency, related_to, source_fact_ids). Set urgency ONLY if the fact states or clearly implies one of emergency / call_doctor / monitor / normal_side_effect -- otherwise leave it null, never guess between them.

A medications fact whose content is a side effect that is merely listed, with no instruction to act on it, belongs in that medication's own side_effects_to_watch field -- never split out as a separate warning_signs item.

### SOURCE_FACT_IDS

Every reason_for_visit, medications, tests, procedures, other, follow_up, and warning_signs item must carry `source_fact_ids`, and every diagnosis.details item must too: the id(s) of every fact you built it from (more than one id if MERGE below combines facts into one item). If diagnosis.changed_since_last_visit is non-empty, diagnosis.changed_since_last_visit_fact_ids must name the fact(s) that state it. Never leave any of these citation fields empty for a claim you decide to include -- a claim with no cited fact has nothing behind it and will not reach the patient.

### STATUS

Every medications, tests, procedures, other, and follow_up item requires status: "to_do" or "done". Never omit it and never leave it null. Use "done" if the fact states or clearly implies the item is already complete. If genuinely unclear, default to "to_do": telling a patient to do something already done costs one phone call; telling them a pending action is complete is a missed follow-up.

### NOT STATED

`why` is the clinician's stated reason for adding, ordering, or continuing this item for this patient -- not the item's usual purpose, and not an instruction about when or how to use it. If a medications, tests, procedures, or other item's `why` is not given by its fact, set why to null. Do not invent a reason, and do not write an empty string ("") -- null is the only way to mark a genuinely unstated reason. `why` stays null even when the drug's usual purpose is obvious from its name or class (an antiemetic's purpose is nausea, a statin's purpose is cholesterol) and even when the fact only says when or how to take it -- a timing or dosing instruction is not a stated reason. Route that content to `timing` or `instructions` instead, never into `why`. If a fact says the reason is not documented, `why` is null no matter what else the fact states -- do not mine the rest of the fact for a plausible-sounding substitute. The app fills in a clear message for the patient wherever why is null, so you do not need to write one yourself.

Worked example: a fact reads "Ondansetron 4 mg by mouth (PO) three times a day (TID) as needed (PRN) for nausea, new medication; no reason documented in the discharge chart for why PRN nausea coverage was added this admission." The fact says outright that no reason is documented, so `why: null` -- even though "nausea" appears right in the fact. "As needed for nausea" describes when to take the drug, not why it was added, so it goes in `timing` ("as needed for nausea"), not in `why`. Writing `why: "For nausea."` would restate the drug's mechanical PRN indication in place of an actual stated reason, which is exactly what this rule forbids.

### MERGE

If two or more facts describe the identical underlying clinical fact (the same finding or instruction, stated more than once, possibly with different specific details), merge them into ONE item. Preserve every differing detail explicitly in the merged wording, no matter how many facts merge -- never drop one to shorten the sentence, and never fall back to a vaguer collective term once naming each one individually gets long.

Example (two variants): plaque reported separately in the left and right coronary arteries merges to "heavy plaque in your left and right heart arteries," NEVER to "heavy plaque in your heart arteries."

Example (three variants): calcified plaque reported separately in the right coronary artery, the left anterior descending artery, and the circumflex artery merges to "heavy calcified plaque in your right coronary, left anterior descending, and circumflex arteries," NEVER to "heavy calcified plaque in your heart arteries," and NEVER to "heavy calcified plaque in your right coronary and left anterior descending arteries" (silently dropping the third site is exactly as wrong as dropping to a collective term -- every site names once, however many there are).

Do not merge facts that are merely related; only merge facts that say the same thing. Record the id of every fact that went into a merged item in that item's source_fact_ids (see SOURCE_FACT_IDS) -- an item built from more than one fact is the signal that a merge happened here.

### LOW PRIORITY

Use `low_priority` as the audit-only home for source-supported facts that do not belong in the concise patient view. This includes normal or routine findings, technical test details, repeated facts, stable background details, rejected differentials, and generic education that does not change this patient's documented plan. Write one short line per fact or merged group. Preserve the specific content well enough for the coverage reviewer to recognize it. Do not put a safety-critical action, medication change, pending follow-up, important result, or explicit warning instruction here.

### QUESTIONS

Write at most three questions a patient might reasonably ask their care team about this visit. Write none if the facts already answer everything a reader would ask -- there is no minimum. Interrogative form only. A question must not assert or presuppose any clinical fact, diagnosis, or judgement that is not already stated in the facts above; it may only ask about a genuine gap or next step.

### SUMMARY

Write `summary` as two or three short sentences, normally 60 to 120 words. Include only: why the patient was seen, the main conclusion or most important result, and the most important next step or unresolved issue. Do not inventory diagnoses, tests, normal values, technical details, or every warning sign. Do not repeat details that the next sections already make easy to find. List the ids of every fact it draws from in `summary_fact_ids`. Apply every rule in style_rules.md, including PLAIN WORDS.

## If you are retried

The dispatch message may include validator or check errors from a previous attempt. Fix exactly those; do not otherwise rework fields the errors did not flag.
