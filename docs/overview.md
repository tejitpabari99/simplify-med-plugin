# simplify-med — overview

simplify-med is a plugin (one portable Agent Skill plus thin platform wrappers) that
turns a clinical document — a visit note, discharge summary, lab report, or
imaging report — into a plain-language, fact-checked care plan. The pipeline
first breaks the document into atomic facts, each one anchored to a specific
line of the source text and carrying a verbatim quote from it; only those
facts are ever assembled into the plan. Nothing is invented: a reason, dose,
or cause the document does not state is shown to the patient as "not stated,"
never guessed. The plan is reviewed and corrected against its own facts
before it is shown to anyone, and every interim file the pipeline writes is
kept in a run folder as an audit trail from source text to final report.

## Who it's for, and who it's not

A patient or caregiver who has a clinical document and a session with a
model that can run this skill, with no clinician in the loop. It is a
reading aid, not medical advice — the report says so on every page. It does
not diagnose, does not recommend treatment beyond what the source document
already states, and does not replace a conversation with a clinician. If a
clinical judgement the source doesn't already contain is needed, the
pipeline will not fill that gap — it shows "not stated" and, where relevant,
lists it as a question to ask a doctor.

The medical pipeline has no backend. Every pipeline script is Python 3 standard library
only — no pip installs and no network access — and reads or writes only the run folder
(plus its inputs). Everything medical happens wherever the model runs the skill, and
deleting the run folder removes that local audit trail.

The OpenAI package optionally adds a separately hosted, presentation-only MCP endpoint
after the final report exists. The endpoint serves a static widget and receives a
temporary OpenAI file reference, but is designed not to download or process the medical
document or report bytes. See [openai.md](openai.md); this presentation layer does not
change the pipeline above.

## Install and run

**Claude Code, local dev:**

```
claude --plugin-dir /path/to/simplify-med-plugin
```

Then invoke the `simplify` skill from within Claude Code.

**Packaged install**, built from the root dispatcher:

```
python3 build.py claude-code
python3 build.py claude-ai
python3 build.py openai
```

`claude-code` zips the whole plugin (wrapped in a top-level `simplify-med/`
folder) for use as a Claude Code plugin. `claude-ai` zips just the portable
skill (also wrapped in `simplify-med/`) for upload as a standalone skill on
claude.ai.

The OpenAI ZIP contains the same skill plus portable manifests and viewer handoff
instructions. Its MCP viewer must be deployed separately to a stable HTTPS endpoint;
building the archive alone does not host it.

**claude.ai**: upload the `claude-ai` zip as a skill.

### What to give it

One `.txt` file per source document. Insert a form-feed character (`\f`)
between pages when page boundaries are known. If the user supplied a PDF,
DOCX, image, or scan, the skill does not convert it — per `SKILL.md` section
2, the model running the skill is instructed to extract the text itself with
its own tools first and save the result as `.txt`, before the pipeline ever
starts. Several files given for one request are treated as one visit; the
grounder sees all of them together.

### What you get back

`report.html` (one self-contained file: inline CSS and JS, no external
assets, works offline, checkboxes that remember their state) and `report.md`
(the same content as plain text). Also a one-line reading-level result, and
any notices (see below).

### Where it lands

Each run is written to `simplify-runs/<run-id>/` in the current working
directory (gitignored). That folder is the full audit trail, from the
numbered source units through `report.html`.

## The report

`plan_view.py` is the single view model both renderers read from. It builds,
in this fixed order, whichever of these seven sections have content (a
section with nothing to show is omitted entirely):

1. **What you need to know** — the one-paragraph summary.
2. **Why you were seen** — the reason(s) for the visit.
3. **What the doctor found** — diagnoses and findings, plus "what changed
   since last time" when the source states it.
4. **Your next steps** — medications, tests, procedures, appointments, and
   other instructions, grouped "To do" first and "Already done" second; each
   row is labelled by type (Medication / Test / Procedure / Appointment /
   Instruction) in that fixed precedence within each group.
5. **What to watch for** — warning signs, sorted stated-urgency first
   (emergency, then call-the-doctor, then monitor, then normal-side-effect),
   ungraded signs last; a warning sign is never dropped for being ungraded.
6. **Questions to ask your doctor** — at most three, only genuine gaps.
7. **Medical terms explained** — the glossary.

`low_priority` items (routine findings, normal results, administrative
detail), every `*_fact_ids` citation field, `meta`, and `run_id` are never
shown to the patient — they stay in the JSON for the audit trail only.

### Checkboxes

Every "Your next steps" row has a checkbox reflecting its `status` field
(`to_do` / `done`). In `report.html`, ticking a box is saved to the browser's
`localStorage` under a key scoped to that run's id, so the state survives a
reload of the same file — it is never written back to the run folder and
never seen by anyone else. `report.md`'s checkboxes are static `[ ]` / `[x]`
marks reflecting the plan's own status at render time.

### The glossary

The glossary agent proposes medical terms worth defining for a general
reader, from the source document alone. A term only survives into the final
report if two things both hold: `glossary_check.py` found it (as a
normalized substring) somewhere in the source units, and `finalize.py`'s
re-detection found it again in the *final rendered plan text* — a term
proposed from source language that got simplified away, or a term whose
plan text was corrected, is dropped rather than shown as a stale reference.
In `report.html`, the first occurrence of each surviving term in specific
sections (the summary, findings, next-steps, and watch sections) is wrapped
in a highlighted span; tapping or focusing it reveals its definition. In
`report.md` the glossary is a plain definition list at the end.

### Notices

When a non-fatal stage degraded, or a deterministic check dropped or
flagged content, the report carries one or more plain-language notices at
the top, rendered once, before the reading-level line. They never name a
fact id, a stage, or any other run internal — for example, "We could not
fully verify every part of this summary against your document. Please
compare important details, like medicine doses and dates, with your
original paperwork." Details of what actually happened stay in `run.json`.

### The reading-level line

One line: "Reading level: grade X before, grade Y after." (or "about grade
Y" if the before-score couldn't be computed; the line is omitted entirely
if the after-score can't be computed). Both scores are a stdlib
Flesch-Kincaid grade-level estimate (`readability.py`), computed on the raw
input text and on the patient-visible rendered text, and require at least
30 words to produce a number. Per the script's own docstring, this is "a
reading-level estimate only, not a measure of quality, clarity, or medical
accuracy" — it is never a claim about correctness and never gates anything.

## The audit view

`render_audit.py`, run only on request (never as part of a normal
`finalize.py` run), produces `report.audit.md`: every plan item paired with
the fact(s) behind it, each shown as `file:page:line "quote"`; a table of
every stage's status, attempts, and checks; the list of facts the coverage
check found nowhere in the plan; and the facts dropped at grounding, with
their drop reason. This is the file to read (or point a curious user to) to
answer "how was this verified?" or "show your sources."

## Guarantees and limits

Mechanically enforced by a deterministic script, not by prompt instruction
alone:

- A fact's quote must be a normalized (case-folded, accent-stripped,
  whitespace-collapsed) substring of its cited source line, or the fact is
  dropped (`anchor_check.py`).
- Every plan item must cite at least one surviving fact id, or it is dropped
  (`cite_check.py`'s guards, applied at assemble and again at finalize).
- A correction from the fidelity reviewer may only touch the exact field
  path it names, plus a bounded (at most 4 changed word-tokens) name/facility
  substitution in an eligible field; anything else is rejected, and a
  rejected correction set falls back to the pre-correction plan with a
  notice rather than shipping an unbounded edit (`diff_guard.py`).
- Every fact is checked against the assembled plan by an enumerate-then-check
  coverage pass; any fact the agent's walk skipped is conservatively
  backfilled as not present, and every fact still missing gets a chance to
  be added as a new item — citing only that missing fact (`sanitize_review.py`,
  `cite_check.py --additions`).
- A glossary term is kept only if it is found, by normalized substring
  match, in both the source document and the final rendered plan text
  (`glossary_check.py`, `finalize.py`'s re-detect).
- A clinician or facility name is swept for at finalize with a bounded regex
  ("Dr./Doctor \<Name\>", "\<Name\>, MD/DO/NP/PA/RN" → "your doctor") on top
  of the style rules the assemble and correct stages are instructed to
  follow.

Numbers and units are checked (`numeric_parity.py` compares every rendered
field's number/unit tokens against its cited facts' tokens), but this is a
**hint** surfaced to the fidelity reviewer, not a mechanical block — no
script refuses to ship a number that doesn't match its fact. Kill test 1
(`docs/agent_files/2026-09-22-simplify-med-plugin-brief/kill-test-1.md`)
found exactly this failure mode (a dropped "mmHg" unit reached the report);
the instruction gap that let it through was fixed and kill test 2 found the
mechanism working correctly, but the underlying design — LLM judgement
downstream of a deterministic flag, not a hard gate — is unchanged.

What this pipeline cannot guarantee: an LLM stage can still miss or misread
something no deterministic check is positioned to catch (kill test 2 found
one such case: a medication's `why` field stated a plausible-sounding but
unsupported reason). No clinician reviews the output. There is one language
and one simplification level (`standard`, ~6th-grade reading level) — see
`futures.md` in `agent_files/` for what was deliberately left out.

## Versioning

`plugin.meta.json` is the single source of truth for the plugin's version —
currently `0.1.0`, semantic versioning starting from there. `.claude-plugin/plugin.json`
and `skills/simplify/scripts/_version.py`'s `PLUGIN_VERSION` must both
match it; `packaging/build.py` checks all three and refuses to build (exit
status 2) on any mismatch. Every JSON file a run produces carries its own
`schema_version` and `plugin_version`.

## More

- [architecture.md](architecture.md) — the stage graph, every deterministic
  check, the data contracts, and the two kill tests in detail.
- [plugins.md](plugins.md) — how to add support for another platform.
- [openai.md](openai.md) — how the OpenAI package and MCP report viewer work.
- [agent_files/](agent_files/) — the original design brief, the decision
  log, the futures list, and the kill-test reports.
