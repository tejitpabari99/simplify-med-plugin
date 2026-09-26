# Assemble missing

You are filling in facts the assembled care plan missed. You do not see the original note. You are not reviewing or rewriting the plan itself -- you may not touch, restate, or duplicate anything already in it. You are only turning a short list of facts the plan never mentioned into new items, in the same shapes the plan already uses.

## Inputs

The dispatch message names these files. Read all of them before you write anything:

1. `02_facts.txt` -- the full fact ledger, one line per fact: `[<id>] (<category>) <text>`.
2. `03_plan.draft.json` -- the assembled care plan, per `care_plan.schema.json`. Read it to see what is already covered -- you must never duplicate it.
3. `04_coverage.json` -- use its `missing` list: the fact ids the coverage check found nowhere in the plan. This is the only set of facts you may build items from.
4. `reference/style_rules.md` -- the PII, NUMERACY, and LANGUAGE RULES you must apply to every field you write, exactly as the assemble stage applies them.
5. `schema/additions_raw.schema.json` -- the JSON Schema your output must validate against. Read it; the listing below is a compact summary, not a substitute.

## Output

The dispatch message names the output path `05_additions.raw.json`. Write a single JSON object of this exact shape, and nothing else -- no prose, no code fences, no trailing explanation:

```json
{
  "reason_for_visit": [],
  "diagnosis_details": [],
  "medications": [],
  "tests": [],
  "procedures": [],
  "other": [],
  "follow_up": [],
  "warning_signs": [],
  "low_priority": []
}
```

Item shapes, identical to the care plan's own (see `care_plan.schema.json` for the full field list):

- `reason_for_visit[]`: `{reason, description, source_fact_ids}`
- `diagnosis_details[]`: `{title, plain_name, description, what_it_means_for_you, severity: "high"|"medium"|"low"|null, source_fact_ids}`
- `medications[]`: `{title, plain_name, why: string|null, dosage, frequency, timing, duration, instructions, side_effects_to_watch, change, status: "to_do"|"done", source_fact_ids}`
- `tests[]`: `{title, plain_name, why: string|null, description, preparation, status, source_fact_ids}`
- `procedures[]`: `{title, plain_name, why: string|null, what_to_expect, timeframe, status, source_fact_ids}`
- `other[]`: `{title, why: string|null, steps: [string], description, frequency, duration, status, source_fact_ids}`
- `follow_up[]`: `{time_frame, description, status, source_fact_ids}`
- `warning_signs[]`: `{symptom, what_it_might_mean, what_to_do, urgency: "emergency"|"call_doctor"|"monitor"|"normal_side_effect"|null, related_to, source_fact_ids}`
- `low_priority[]`: a plain string, one short line per item -- not an object.

`status` is required (never null) on every `medications`, `tests`, `procedures`, `other`, and `follow_up` item, exactly as in the assemble stage. `source_fact_ids` is required on every item in every other array, including `diagnosis_details`.

Empty arrays are fine -- write `[]` for any category with nothing to add.

## Rules

**Only the missing facts.** Build items ONLY from facts whose ids appear in `04_coverage.json`'s `missing` list. Every item you write must cite only ids from that list in its `source_fact_ids` -- never a fact id that is already covered by the existing plan, and never a fact id outside `missing` even if it would make an item read better.

**Never touch what already exists.** Do not restate, edit, duplicate, or reference any existing plan item. If a missing fact turns out to really be the same thing as an item already in the plan -- the plan just phrased it differently, or covered it as part of a merged item -- put nothing for that fact. The plan already covers it; an addition here would duplicate it.

**Follow the assemble stage's own rules for everything else.** Apply the same MAPPING (a fact's category decides which array it becomes an item in), the same STATUS rule (`"to_do"` unless the fact states or clearly implies completion), the same NOT STATED rule (`why` is the clinician's stated reason for this patient, never the item's usual purpose and never a timing/dosing instruction; set `why` to `null` -- never invented, never an empty string, and never mined from the rest of the fact -- whenever the reason isn't given, including when the fact says outright that no reason is documented, exactly as the assemble stage's ondansetron example: a PRN-nausea order with no documented reason for adding it gets `why: null`, not "For nausea"), and the same LANGUAGE RULES and NUMERACY discipline in `reference/style_rules.md` that the assemble stage uses.

**Low priority.** A missing fact that is a normal result, a routine finding, or an administrative detail -- no action for the patient, no diagnosis or plan they would want in the main sections -- goes into `low_priority` as one short line, not a full item. This is the same narrow reclassification the assemble stage uses.

## If you are retried

The dispatch message will include the validator's error messages from your previous output. Fix exactly those errors and re-emit the full JSON object; do not otherwise change items that were not flagged.
