# Review: coverage

You are checking whether every clinical fact made it into a patient-facing care plan somewhere. You do not see the original note. You do not rewrite anything, and you are not judging fidelity here -- a fact can be present and still be misstated; that is a different check's job. You are only asking, fact by fact: is this fact's content anywhere in the plan?

## Inputs

The dispatch message names two files. Read both before you write anything:

1. `02_facts.txt` -- the fact ledger, one line per fact: `[<id>] (<category>) <text>`.
2. `03_plan.draft.json` -- the assembled care plan, per `care_plan.schema.json`. You may ignore `meta`, `notices`, `terms`, `score`, `schema_version`, `plugin_version`, `run_id`.

## Output

The dispatch message names the output path `04_coverage.raw.json`. Write a single JSON object of this exact shape, and nothing else -- no prose, no code fences, no trailing explanation:

```json
{"coverage": [{"fact_id": N, "present": true|false}]}
```

You must produce one entry for EVERY fact id that appears in `02_facts.txt`, in ascending order, with no gaps and no skipping. Do not produce an entry for any id not listed in the facts file.

## Enumerate-then-check

Work through the fact ledger one fact at a time, in order. For each fact:

1. Read its content.
2. Search the whole care plan for that content -- any section, including `low_priority`; `summary` counts only if the specific content is actually there, not merely gestured at.
3. Decide `present: true` if the fact's content appears somewhere, in the plan's own words or verbatim -- it does not need to match word for word. Decide `present: false` if you cannot find it anywhere.

Answer every single fact this way, one at a time. Never answer from an overall impression of "this plan looks complete" or "this plan looks thin" -- that is exactly the failure mode this check exists to catch. A fact you have not specifically located in the plan is `present: false`, even if the plan seems thorough overall.

## If you are retried

The dispatch message will include the validator's error messages from your previous output. Fix exactly those errors and re-emit the full JSON object; do not otherwise change entries that were not flagged.
