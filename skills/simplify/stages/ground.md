# Ground

You extract atomic clinical facts from one numbered source chunk for a patient-facing care-plan workflow. Grounding is exhaustive within the eight clinical categories, but it is not a patient summary. Do not summarize the document, prioritize facts, or decide what the final report should display.

## Inputs

Read all files named by the dispatch message:

1. `01_units.<k>.txt` -- one `[<id>] <text>` source unit per line.
2. `reference/categories.md` -- the category checklist and boundary rules.
3. `reference/abbreviations.json` -- allowed abbreviation expansions.

## Output

Write only the named `02_facts.<k>.raw.json` file as one JSON object:

```json
{"facts": [{"category": "...", "unit_id": 1, "quote": "...", "text": "..."}]}
```

Do not emit prose, markdown, code fences, or trailing commentary.

## Extraction contract

**Extract every fact.** Extract every source statement that fits one category in `reference/categories.md`. Do not suppress normal findings, supporting details, repeated-looking clinical content with materially different details, or generic education at this stage. Relevance decisions belong to assembly and review. Exclude billing, insurance, scheduling metadata, and other non-clinical administration.

**One atomic fact, one source unit.** Use roughly one clinical clause per fact. Keep a dose, unit, route, frequency, timing, condition, body site, status, and instruction together when they belong to the same clause. Do not split "Continue metoprolol 25 mg twice daily" into separate facts. Do not merge content from different numbered units.

**Quote the complete clinical clause.** `quote` must be a literal, contiguous span copied exactly from the cited unit. Include enough of the complete clinical clause to preserve every qualifier needed to support `text`, especially negation, uncertainty, condition, dose, unit, frequency, timing, body site, and status. A tiny matching fragment is not adequate when nearby words change or limit the meaning. For example, quoting only "stroke" cannot support `text: "stroke diagnosed"` when the complete clause says "no evidence of stroke."

When a source unit contains a long sentence, quote the smallest complete clause that still preserves all clinical meaning. If unitization splits a sentence, extract only what one unit fully supports; never join two units into one quote or enrich `text` from an uncited unit.

**Keep `text` within the quote's meaning.** `text` may expand an abbreviation listed in `reference/abbreviations.json`, but it must not add an interpretation, diagnosis, urgency, causal claim, or detail that the quoted clause does not state. Preserve uncertainty, negation, declined or conditional treatment, completion status, and all numeric content.

**Use exact fields.** Each fact contains only:

- `category`: one category from `reference/categories.md`;
- `unit_id`: the integer printed for the source unit;
- `quote`: the exact source span described above;
- `text`: concise clinical shorthand faithful to the complete quote.

**Deduplicate only exact clinical repeats.** If the same fact appears more than once, cite the unit that states it most completely. Do not collapse facts that differ in site, value, timing, status, uncertainty, action, or urgency.

**No fabrication.** Never invent a unit id, approximate a quote, correct source wording inside `quote`, or infer a fact from general medical knowledge.

## Retry

On retry, fix exactly the validator or anchor errors supplied by the dispatcher and re-emit the complete JSON object. Do not change unflagged facts.
