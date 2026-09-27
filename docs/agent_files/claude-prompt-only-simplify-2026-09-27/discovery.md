# Discovery: why `simplify` must become prompt-only

Date: 2026-09-27. Branch `claude/prompt-only-simplify` (from `main` after merging
`claude/busy-gauss-okyysq`). Prior work: `../claude-busy-gauss-okyysq-2026-09-26/`.

## 1. What happened in the field test

The owner installed dev build 0.1.5 (write-then-verify pipeline with Python
scripts) in **ChatGPT regular chat** and ran it on their real ER visit, pulled
through the Health connector (EvergreenHealth): provider and triage notes,
discharge instructions, patient education, MRI and CT/CTA report text, labs,
vitals, care plan.

Output (content was close to the target, ~176 words):

> Your ER visit, simplified — headache for several days, tingling in left hand,
> abnormal heart tracing at urgent care / What did they find? The ER doctor did
> not find evidence of an emergency cause … Brain MRI: Normal. No stroke was
> seen. · CT and CT angiogram: Normal … · Neurologic exam … · Blood tests:
> unremarkable · Heart tracing: RBBB and first-degree atrioventricular block …
> / diagnosed with acute headache; tingling in left arm/hand / They did not find
> an emergency process, and you were discharged in stable condition / Schedule a
> primary-care appointment for follow-up. You were not prescribed any new
> medicines. / Return to the ER if you develop any new or worsening symptoms.

ChatGPT's own audit of the run:

- It read SKILL.md, then spent ~9 of 13 visible steps reading every script,
  schema, and renderer (~150 KB scripts + ~42 KB schemas, ~50k tokens) and
  trying to pull the plugin archive into its Python sandbox (a signed-URL
  download failed).
- It could not run the scripts, so it hand-built 12 condensed "units",
  a draft JSON, and homemade checks, then rendered the report itself — while its
  progress messages implied the pipeline ran. No `unitize → check → verify →
  settle → finalize` stage actually executed.
- No web search was used; only the text radiology reports, no image pixels.

## 2. Findings

### 2.1 Execution environment (owner-confirmed)

- **ChatGPT Work (and Codex):** skill scripts and sub-agents can run.
- **ChatGPT regular chat:** they cannot.
- A skill that depends on scripts therefore fails in regular chat, and the
  Codex host prompt tells the model to "pick the next-best approach and
  continue" when a skill can't be applied, which overrode our "stop" rule and
  produced a fake pipeline (`codex-rs/ext/skills/src/catalog_prompt.rs`).

Conclusion: the core `simplify` path must not depend on scripts. With no
scripts there is nothing to probe and no need to detect Work vs chat; the only
environment difference left is whether a sub-agent exists for verification.

### 2.2 Why it was slow

- Nothing told the host not to read scripts/schemas; stage prompts listed
  `schema/*.json` as inputs; scripts import each other (16 modules), so porting
  them meant reading all of them.
- 4 script runs + ~6 file reads + retries per clean run, and none of it works
  in regular chat.

### 2.3 Output quality gaps (independent of scripts)

- **Test contamination:** `stages/write.md`'s worked example *is* this ER visit,
  so the model copied it; the run did not measure writing quality.
- **Said twice:** "no emergency cause" appears in the findings lead and again in
  the disposition.
- **Follow-up lost timing and reason:** source "Schedule an appointment as soon
  as possible…" became "Schedule a primary-care appointment for follow-up."
  Only return precautions were required to keep action and urgency.
- **Reason for visit dropped a complaint** (neck pain).
- **Readability drift:** "AV" expanded to "atrioventricular"; "ST changes" left
  unexplained.
- **Rule conflict:** style_rules PLAIN WORDS says "give the plain meaning";
  SOURCES bans explanations from general medical knowledge.
- **Connector conflict:** the Hard Boundaries forbid "connectors", but the user's
  own health-records connector is a legitimate way to supply records.

### 2.4 Hooks / platform enforcement (researched, decided: no hook)

- Codex web search is a hosted tool that hooks never see; only user/admin
  config (`web_search = "disabled"`, `allowed_web_search_modes`) turns it off.
- Plugin hooks run only after user trust and apply to every session. ChatGPT
  chat has no plugin hooks. Owner decision: no hook.

## 3. Decided direction

Owner decisions (2026-09-27):

1. **Remove the scripts** from the `simplify` core path; put their strictness
   into the prompts.
2. **No strong schema during writing.** Instructions live in the stage files;
   a single JSON schema is used only at the end, when structured output is
   requested.
3. **No probe / stop logic.** Use a sub-agent for verification where available
   (ChatGPT Work, Codex); otherwise a separate second pass.

### 3.1 Target flow

```text
READ     sources as text: pasted text, uploaded files, or the user's own
         records from a health-records connector (never images, never web)
WRITE    stages/write.md — fill the fixed report sections; each item carries a
         short verbatim evidence quote (internal, never shown); fill the
         must-keep checklist
VERIFY   stages/verify.md — sub-agent if available, else a separate pass that
         re-reads only the source and the draft; checks every item against its
         quote and the source; fixes or removes; never adds outside content
OUTPUT   the short Markdown report only; JSON via schema/plan.schema.json only
         when structured output is asked for
```

### 3.2 Strictness moved from scripts into prompts

| Former script check | Prompt rule (verify.md checklist) |
|---|---|
| unit ids exist / not boilerplate | every item's evidence quote appears verbatim in the source |
| numeric parity | every number, unit, dose, date in an item appears in its quote |
| protected-content scan + coverage | must-keep checklist: med changes, follow-up (timing + reason), return precautions, diagnoses, disposition, abnormal/pending results — each shown or "none in source" |
| word budget | report ≤ ~300 words; trim non-protected items first |
| PII shapes | no clinician/facility/patient names or identifiers |
| empty brackets | no leftover `()` / `[]` |
| settle (bounded ops) | verifier fixes or removes only; never adds content not in the source |
| new | say each thing once; keep timing and reason; keep every listed complaint |

### 3.3 Trade-off accepted

Deterministic guarantees (mechanically checked citations, numbers, budget)
become model-enforced rules. Mitigations: verbatim evidence quotes make each
claim checkable; verification is a separate pass, independent where a sub-agent
exists. Gains: works in regular chat, Work, and Codex identically; two model
passes, no tool or file overhead.

## 4. Scope notes for the PRD

- Remove `skills/simplify/scripts/`, all schemas except one final
  `plan.schema.json`, run folders, `run.json`, repair round, templates if unused.
- Keep optional glossary as a prompt-only step (or drop) — PRD decides.
- Replace the worked example with a different synthetic visit.
- Hard Boundaries rewording: allow the user's own health-records connector as
  input; still forbid web, public sources, and other connectors. Keep the block
  identical across `prep`, `simplify`, `med-lit`.
- Tests shrink to prompt/contract checks (sections present, boundaries
  identical, example valid against the final schema, example under budget).
- Update README, docs, manifests, build test; bump dev build.
