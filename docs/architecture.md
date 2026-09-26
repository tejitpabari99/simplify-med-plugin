# simplify-med — architecture

This document describes the implemented schema-v2 pipeline: its execution
contract, three model responsibilities, deterministic safeguards, run
artifacts, rendering behavior, and compatibility boundary. Read
[overview.md](overview.md) first for the patient-facing behavior.

## Principles

- **Explicit invocation.** The `simplify` skill is not implicitly invoked.
  Once selected, it must run the complete workflow rather than answer with
  an ad hoc summary.
- **Fact-first.** Patient-facing claims originate as atomic facts anchored
  to complete source clauses.
- **Critical-first.** The report preserves what changes understanding,
  action, or safety without displaying every extracted detail.
- **Audited omissions.** Every verified fact is either cited by visible
  content or assigned exactly one structured omission reason.
- **Three model responsibilities.** The model grounds source chunks,
  assembles the concise draft, and performs one independent semantic review.
- **Deterministic enforcement.** Python owns source anchoring, schemas,
  citations, omission accounting, numeric parity, exact settlement, run
  identity, rendering, and final publication gates.
- **Fail closed.** A missing, failed, degraded, stale, or invalid core stage
  prevents clinical output. There is no draft fallback.
- **Immutable default output.** The default clinical response is the
  finalized `report.md`; the host does not create a second summary.

## Repository layout

```text
plugin.json                    portable OpenAI plugin manifest
.codex-plugin/plugin.json      Codex compatibility manifest
build.py                       allowlist-based OpenAI ZIP builder
skills/simplify/
  SKILL.md                     invocation contract and workflow
  agents/openai.yaml           UI metadata and explicit-invocation policy
  assets/                      skill icons
  stages/                      ground, assemble, review, optional glossary
  scripts/                     deterministic pipeline and renderers
  schema/                      schema-v2 data contracts
  reference/                   relevance, language, and lookup guidance
  templates/                   optional HTML report template
mcp/openai/                    retained future source; excluded from ZIP
tests/                         deterministic, integration, and package tests
docs/                          documentation and design history
simplify-runs/                 gitignored run folders
```

The distributable ZIP contains only `plugin.json`,
`.codex-plugin/plugin.json`, and `skills/`.

## Invocation contract

`skills/simplify/agents/openai.yaml` sets
`allow_implicit_invocation: false`. The user or host must explicitly select
the skill. The metadata prompt and both plugin manifests direct the host to
run the complete workflow and not summarize the documents directly.

After invocation:

1. No model stage may answer the user.
2. No clinical content may be presented before finalization succeeds.
3. Every required stage receives at most one retry for invalid model output.
4. A terminal core failure produces only a concise workflow error.
5. The host presents the finalized `report.md` without rewriting it.

This instruction contract is reinforced by deterministic finalization. It
is not merely a preferred prompting style.

## Model and Python boundary

The clean path has three model responsibilities:

1. **Ground `K` chunks.** Extract atomic facts with complete-clause quotes,
   preserving negation, uncertainty, conditions, numbers, units, status,
   timing, and urgency.
2. **Assemble once.** Create concise, cited patient content and assign every
   non-visible fact an omission disposition.
3. **Review once.** Independently evaluate every visible fact, every
   omission, and every numeric flag; return bounded operations or request
   reassembly for critical missing content.

Python does not decide medical meaning or write the explanation. It verifies
and constrains model output through deterministic algorithms. This preserves
the authoring rule in [openai-plugin.md](openai-plugin.md): language judgment
belongs in instructions; repeatable safety checks belong in scripts.

## Stage graph

```text
UNITIZE
  -> ground[1..K] in parallel
  -> ANCHOR_CHECK each chunk -> MERGE_FACTS
  -> assemble
  -> CITE_AND_DISPOSITION_CHECK + NUMERIC_PARITY
  -> combined independent review
  -> SETTLE_REVIEW
       -> exact bounded operations
       -> citation/disposition recheck
       -> numeric-resolution recheck
  -> FINALIZE
  -> optional glossary / HTML / audit
```

For `K` source chunks, the clean workflow uses `K + 2` model calls: one per
grounding chunk, one assembly call, and one review call. A one-chunk clean
run therefore uses three model calls.

The graph has three clean model latency waves: parallel grounding, assembly,
and review. Fewer calls and less repeated context are implemented properties;
wall-clock and token improvements are hypotheses until measured on
representative documents and hosts.

## Core workflow

### 1. Unitize

`unitize.py` creates a fresh run identity, copies source text under
`00_input/`, records SHA-256 input metadata in `run.json`, preserves page and
line locations, and writes numbered chunks. Starting an explicit run folder
clears stale downstream artifacts so results cannot cross run identities.

The pipeline accepts one UTF-8 text file per source document. Extraction
methods are `native`, `ocr`, or `pasted`; form-feed characters preserve known
page boundaries.

### 2. Ground and anchor

The host runs `stages/ground.md` once for every expected chunk and writes
`02_facts.<k>.raw.json`. `anchor_check.py` validates the raw schema and
requires each quote to match a complete clause in the numbered chunk.

Grounding chunks may run in parallel. Each failing chunk may be retried once.
`merge_facts.py` refuses missing chunks, invalid chunks, rejected facts, or
artifacts from another run. It writes the verified `02_facts.json` ledger;
assembly and review use that JSON ledger directly.

### 3. Assemble a concise draft

`stages/assemble.md` reads only the verified fact ledger plus the language
and relevance references. It writes `03_plan.raw.json` against the
agent-facing care-plan schema.

`cite_check.py` then:

- validates every patient-facing citation;
- rejects unsupported summary or changed-since text;
- requires every verified fact to be visible or omitted exactly once;
- rejects unknown, duplicate, or conflicting fact dispositions; and
- writes the system-owned `03_plan.draft.json`.

`numeric_parity.py` writes `03_flags.json` with stable flag IDs, preserving
numeric multiplicity so the reviewer can resolve each mismatch explicitly.
Assembly may be retried once if schema, citation, disposition, or numeric
preparation fails.

### 4. Combined independent review

`stages/review.md` replaces the former separate fidelity and coverage
reviews. It reads the verified ledger, checked draft, numeric flags, and
relevance rules, then writes `04_review.raw.json`.

The review must:

- enumerate every verified fact exactly once;
- mark visible facts `visible_accurate` or `visible_needs_correction`;
- mark omitted facts `omission_acceptable` or `must_include`;
- check fidelity, negation, uncertainty, medication status, urgency, and
  critical-versus-supporting relevance;
- resolve every numeric flag as equivalent, corrected, or removed; and
- emit only `replace`, `clear`, or `remove` operations on allowed paths.

Aggregate verdicts and counts are derived deterministically rather than
trusted from model-authored totals.

### 5. Settle exactly

`settle_review.py` validates the exhaustive review contract. It rejects
unknown paths, protected system fields, partial operation application,
unsupported replacement values, unresolved numeric flags, and review output
that belongs to another run.

Accepted operations apply exactly once. Settlement then reruns citation,
fact-disposition, and numeric assertions before writing:

- `04_review.json`, the sanitized review and derived counts; and
- `05_plan.settled.json`, the only clinical input accepted by finalization.

There is no model-authored whole-plan correction stage and no separate
additions artifact.

### 6. Bounded reassembly

When the independent reviewer marks an omitted fact `must_include`, it lists
the same fact ID in `reassemble_fact_ids`. Settlement stops instead of adding
unreviewed prose.

The host may reassemble once, using the accepted draft and only the verified
facts needed for the smallest patient-facing change. It reruns citation and
numeric checks, invokes a fresh independent review over the complete revised
draft, and settles again. A second reassembly request fails the run.

This boundary preserves speed on the clean path while ensuring every new
patient-facing sentence receives independent semantic review.

### 7. Fail-closed finalization

`finalize.py` is assertion-only for clinical content. It reads only
`05_plan.settled.json` and verifies:

- current schema, plugin, and run identities;
- required core stage records and `ok` statuses;
- required artifact declarations and files;
- structured schemas;
- exhaustive citations and omission dispositions;
- complete numeric resolutions; and
- settled content integrity.

It applies only the pipeline's bounded clinician-name substitution, computes
readability telemetry, and atomically writes `06_plan.final.json` and
`report.md`. It does not merge additions, silently drop content, repair a
draft, or publish a degraded result.

Core run stages are `unitize`, `ground`, `assemble`, `plan_check`,
`numeric_parity`, `review`, `settle_review`, and `finalize`. Core stages have
only `ok` or `failed` states. Optional stages may be skipped or degraded
without changing an already finalized plan.

## Critical-versus-supporting policy

The complete ledger is an audit resource, not a mandate to display every
fact. The report leads with the main outcome and next action.

Critical content normally remains visible:

- the reason for the visit and main clinician conclusion;
- documented diagnoses or important unresolved findings;
- medication starts, stops, changes, doses, timing, and instructions;
- pending tests, referrals, monitoring, follow-up timing, and contacts;
- explicit warning signs with the source's action and urgency;
- uncertainty, conflicts, declined or conditional treatment; and
- reassuring results that directly explain disposition or next steps.

Supporting content normally stays out of the patient report:

- technical test mechanics, contrast details, sequences, and metadata;
- raw normal values or incidental findings that do not change the plan;
- repeated facts already represented clearly;
- rejected, non-actionable differential diagnoses;
- generic education or wellness guidance not applied to this patient; and
- stable background history or unchanged medicines.

Generic discharge education is not patient-specific merely because it was
attached to the record. Supporting facts remain in `02_facts.json` and are
recorded in `omitted_facts` with one of these schema-defined reasons:

- `duplicate_or_already_represented`;
- `technical_detail`;
- `routine_non_actionable`;
- `rejected_non_actionable_differential`;
- `generic_not_patient_specific`; or
- `stable_unchanged_background`.

The reviewer examines every omission and can force bounded reassembly when a
supposedly supporting fact is actually critical.

## Clean artifact contract

A clean one-chunk schema-v2 run has approximately 13 core artifacts, excluding
copied source files:

```text
run.json
01_units.json
01_units.1.txt
02_facts.1.raw.json
02_facts.json
03_plan.raw.json
03_plan.draft.json
03_flags.json
04_review.raw.json
04_review.json
05_plan.settled.json
06_plan.final.json
report.md
```

Additional chunks add one numbered units file and one raw-facts file each.
Failed model attempts may leave attempt-suffixed raw artifacts for audit.
The raw fact, draft, and review files remain local pipeline evidence and are
not part of the default patient response.

## Data contracts

All schema-v2 JSON uses the current run and plugin identity where applicable.
The eleven bundled schemas comprise nine core contracts and two optional
glossary contracts:

- `units`: source locations, extraction methods, and chunk boundaries;
- `facts_raw` and `facts`: model extraction and verified ledger;
- `care_plan_agent` and `care_plan`: model-owned draft fields and the
  system-owned complete plan;
- `flags`: stable numeric mismatch IDs and thin-field telemetry;
- `review_raw` and `review`: exhaustive semantic review, exact operations,
  numeric resolutions, derived counts, and verdict;
- `run`: constrained core and optional stage records;
- `glossary_raw` and `glossary`: optional post-finalization terms.

Patient-facing questions are cited objects, not free strings. The plan's
`omitted_facts` array provides exhaustive non-visible fact dispositions.
System-owned metadata, notices, readability, source IDs, and omissions are
hidden from the default patient view.

## Default and optional outputs

`report.md` is the only default clinical output. `plan_view.py` constructs the
patient view, and `render_md.py` renders it without another model rewrite.
The host presents that file as-is.

After successful finalization, the user may request:

- **Glossary:** `stages/glossary.md` works only from visible finalized text;
  `glossary_check.py` writes `07_glossary.raw.json` and
  `07_glossary.json`.
- **HTML:** `render_html.py` writes `report.html` and may consume the optional
  validated glossary without modifying `06_plan.final.json`.
- **Audit:** `render_audit.py` writes `report.audit.md` with stage records,
  omission decisions, reviewer results, source quotes, locations, and
  extraction methods.

Optional output failure never invalidates or mutates a completed final plan.
It also never authorizes a host-authored substitute summary.

## Schema-v1 compatibility

Completed schema-v1 final reports remain renderable through the Markdown,
HTML, and audit views. Legacy glossary data is supported for those completed
reports.

Schema-v1 intermediate artifacts are not resumable. `finalize.py` rejects a
partial schema-v1 run and directs the user to restart from source through the
schema-v2 workflow. This avoids mixing stage names, schemas, run identities,
or safety guarantees across versions.

## Retries, concurrency, and failure

- Grounding chunks may run concurrently.
- Assembly waits for every expected chunk and a valid merged ledger.
- Review waits for checked draft and numeric flags.
- Each model stage receives one retry using deterministic validator errors.
- Reassembly is allowed once and always requires a fresh complete review.
- There is no unbounded repair loop, skipped review, degraded core stage, or
  draft fallback.
- Required command unavailability is a workflow failure; the host does not
  reproduce deterministic checks by inspection.

`runlog.py` serializes updates with file and thread locks, records attempts,
checks, artifacts, timestamps, and run identity, and constrains recognized
stage names through the schema-v2 run contract.

## Testing

The standard-library test suite covers each deterministic boundary plus the
end-to-end script chain, stage documentation, status lines, fixtures, skill
consistency, and package contents:

```bash
python3 -m unittest discover -s tests -v
```

Important regression areas include missing chunks, invalid anchors,
unsupported citations, duplicate or missing fact dispositions, numeric
multiplicity, exhaustive review, exact settlement, protected paths,
reassembly refusal, stale run identity, fail-closed finalization, explicit
invocation metadata, optional renderers, and schema-v1 compatibility.

## Performance interpretation

The schema-v2 design fixes the clean call count at `K + 2` and targets about
13 core artifacts for one chunk. Those are architectural counts, not latency
benchmarks. The removal of a full-source glossary call, a second semantic
review, whole-plan correction, and additions generation should reduce model
tokens and scheduling overhead, but p50/p95 latency, retries, token use, fact
recall, unsupported claims, and omission quality must be measured on
representative clinical documents before making quantitative speed or quality
claims.
