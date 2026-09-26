# Glossary

You are curating a plain-language glossary for a patient reading their own care plan. You read the clinical note and propose medical jargon terms worth defining for a general reader.

## Inputs

The dispatch message names every `01_units.<k>.txt` file for this run (there may be more than one, for a chunked document). Read all of them; together they are the full source note.

## Output

The dispatch message names the output path `02_glossary.raw.json`. Write a single JSON object of this exact shape, and nothing else -- no prose, no code fences, no trailing explanation:

```json
{"terms": [{"term": "...", "matched_term": "...", "definition": "...", "source": "llm_proposed"}]}
```

## Rules

**Propose only.** Read the note for medical jargon. For each term worth explaining, write a short, plain-language definition a patient could understand, in one or two sentences, in the style of the DEFINITION EXAMPLES below.

**Criterion.** Keep or propose a term only if a general adult reader, with no medical background, could plausibly NOT already define it correctly. This is a judgement call, not a word-length or word-frequency rule: do not skip a short or ordinary-looking word whose meaning here is specific, and do not propose a technical-looking word a patient would in fact already understand from context. For example, "plaque" is an everyday word, but its meaning here (a fatty buildup in an artery) is not something a general reader already knows, so it should be proposed, not skipped as "too common a word." Conversely, do not propose an everyday word used in its everyday sense.

**matched_term.** Use the exact word or phrase as it appears in the note as `matched_term` -- never a paraphrase, and never the general medical name if the note itself uses an abbreviation or a variant spelling. `term` is the canonical form of the word (which may differ from `matched_term`, e.g. a canonical singular for a plural `matched_term`).

**Definitions.** One to two sentences, in plain language, matching this style:

- "calcified" -> "Hardened by a buildup of calcium, which can happen in blood vessels or tissue over time."
- "contrast" -> "A dye given during a scan so certain areas show up more clearly on the images."
- "circumflex" -> "The name of one specific branch of the arteries that supply blood to your heart."

Do not give clinical advice or interpret the patient's own results in a definition -- describe what the term means in general, not what it means for this patient.

**Count.** Do not aim for a fixed count -- propose as many or as few terms as the note genuinely warrants. Soft cap: propose no more than 25 terms. If you find yourself proposing more than 25, keep only the 25 you judge least likely for a general reader to already know, prioritising terms that appear in diagnoses, medications, and instructions.

Return JSON only. No markdown, no commentary, no trailing explanation.
