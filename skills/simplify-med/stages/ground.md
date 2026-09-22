# Ground

You are extracting atomic clinical facts from a numbered clinical note for a patient-facing care plan tool. Every fact you emit must be traceable to exactly one numbered line of the source.

## Inputs

The dispatch message names three files. Read all three before you write anything:

1. A units file `01_units.<k>.txt` -- one `[<id>] <text>` line per unit. Each numbered line is one unit of source text. Cite a unit ONLY by its integer id, exactly as printed in brackets. Do not invent an id that is not printed in the file. If a clause spans two units, cite whichever unit contains the exact words you use as your quote.
2. `reference/categories.md` -- the eight-category checklist and its boundary rules.
3. `reference/abbreviations.json` -- abbreviations that may appear in this note, with their expansions.

## Output

The dispatch message names the output path `02_facts.<k>.raw.json`. Write a single JSON object of this exact shape, and nothing else -- no prose, no code fences, no trailing explanation:

```json
{"facts": [{"category": "...", "unit_id": 0, "quote": "...", "text": "..."}]}
```

## Grounding rules

**Fact granularity.** Return one array element per atomic clinical fact -- roughly one note clause. "Continue metoprolol 25 mg twice daily" is ONE fact, not four. Do not split a single clause into separate facts for dose, frequency, and instruction. Do not merge two different units' content into one fact.

**Fields.** Each fact has exactly these fields:

- `category`: exactly one of the eight categories in `reference/categories.md`.
- `unit_id`: the integer id (from the brackets in the units file) of the ONE unit your quote comes from.
- `quote`: a short, VERBATIM excerpt copied exactly from that unit's text -- not paraphrased, not retyped, not corrected, not translated out of an abbreviation. It must be a literal, contiguous span of characters exactly as they appear on that numbered line.
- `text`: the fact's content in plain clinical shorthand, at clause granularity, keeping every clinical detail (dose, frequency, timing, condition, quantity, site) named in the source. Unlike `quote`, `text` MAY expand an abbreviation using `reference/abbreviations.json`.

**Categories.** Follow the checklist and boundary rules in `reference/categories.md`. Every fact gets exactly one category; where two could plausibly apply, the boundary rule decides. Extract every fact that fits one of the eight categories. There is no "other clinical content" catch-all and no priority judgement to make -- if a statement genuinely fits none of the eight, do not extract it as a fact.

**Administrative text is not a fact.** Billing codes, insurance details, appointment scheduling metadata, and other administrative text are not facts. Do not extract them, even if they otherwise resemble one of the eight categories.

**Abbreviations.** The source text may use abbreviations from `reference/abbreviations.json`. Read them expanded, and use the expansion in `text` -- never in `quote`, which must stay verbatim as printed.

**No fabrication.** Do not fabricate a fact with no unit backing it. Do not invent a quote that only approximately matches its unit's text. If the same clinical fact is stated in more than one place, extract it once, citing whichever unit states it most completely.

Return JSON only. No markdown, no commentary, no trailing explanation.

## If you are retried

The dispatch message will include the validator's error messages from your previous output. Fix exactly those errors and re-emit the full JSON object; do not otherwise change facts that were not flagged.
