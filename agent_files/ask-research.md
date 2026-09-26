# `ask` skill research and V1 recommendation

Scope: read the seven linked Google Drive files themselves and the local plugin checkout. This is a product and implementation recommendation, not independent medical or literature verification. No web pages, papers, or facts outside those files were consulted. All seven Drive files were readable. Google Docs locations below are native paragraph character-index spans in tab `t.0`; Sheets locations are tab and cell coordinates. Survey responses and the two compiled literature notes are treated as directional source material, not representative statistics or independently verified research findings.

## Decision

Build `ask` as a *visit-question composer* with two entry paths: (1) before a visit, gather the patient's chief concerns and produce a short, ordered agenda; (2) after a clinical document or a `simplify-med` run, generate questions about the specific facts, gaps, and next steps in that material. Share one question-ranking and output contract, but make the entry path explicit. V1 should support both because the “Prep the patient” file is explicitly a pre-appointment flow, while “Questions generation” explicitly starts with a result or diagnosis and proposes universal and topic-specific questions. [E1, E2] The existing plugin already has a source-anchored document pipeline and a future note for follow-up conversation, so the post-document path can reuse a narrower evidence surface without changing the existing care plan. [R1, R2]

User promise: “Bring the most useful questions to your next appointment, based on what matters to you and what your document actually says.” For pre-visit use, the promise is an organized agenda, not clinical interpretation. For post-document use, the promise is questions grounded in supplied material, not answers or new recommendations. The pre-visit document proposes a concise doctor-shareable summary and explicitly says people should answer only relevant prompts; the question document proposes a small universal layer plus expandable topics. [E1, E2]

## Inputs and interaction

- Accept free-text concerns and optional details: onset, location, duration/frequency, effect on daily life, what has been tried, and the patient's goal for the visit. Ask at most the few missing prompts that change the resulting questions; let users skip any prompt. Ask them to rank up to three concerns. The pre-visit source lists these fields, allows non-applicable prompts to be skipped, and suggests arranging concerns by priority. [E1]
- Accept one or more extracted clinical documents or the existing run folder/fact ledger and report. Reuse the existing source-text extraction boundary for PDF/image inputs if necessary; do not make `ask` parse unsupported binary formats by itself. The current plugin asks for extracted `.txt`, unitizes lines, and keeps anchored facts in the run folder. [R1]
- Ask one routing question only when the context is ambiguous: “Are you preparing for a visit, or asking about a document you already have?” If a clinical document is supplied, default to the document path. If the user lists symptoms and an upcoming appointment, default to pre-visit. This is an implementation judgment supported by the separate purposes of the two source drafts. [E1, E2]
- Keep the live exchange short. Let the user add, remove, reorder, and rewrite questions; then provide a clean share/copy version. A clinician response calls for written questions and concerns, an up-to-date medication list, and recent relevant data before the visit; another says summaries should be succinct and relevant. These are individual responses, not a measured consensus. [E5, E6]

## Question selection and priority

Generate candidates from a small, explicit taxonomy: main takeaway/certainty; next steps and timing; home plan; monitoring and when to contact the team; follow-up; medications; treatment options; daily life; referral. Include a category only when the patient's concern or document makes it relevant. The draft question bank contains these exact categories and examples. [E2]

Rank candidates in this order:

1. The patient's stated top concern or goal and unresolved question. The prep draft asks what the patient hopes to get from the visit and proposes patient-controlled priority order. [E1]
2. A consequential gap or ambiguity in the supplied document: who does what next, when, medication use, a test result's meaning, warning signs, follow-up. The question bank covers these domains. The existing plugin's factual rule is to mark unstated details rather than guess them. [E2, R1]
3. A decision the patient faces, such as options, benefits/risks, or what happens if they wait, only if the supplied material or user raises that decision. The question bank lists these as clinician-facing questions. [E2]
4. General universal questions only to fill a sparse list; avoid repeating context-specific questions. The source proposes five universal questions plus topic-specific layers, but presenting every item would violate its own expandable, selective pattern. [E2]

Target a **default of 3–5 primary questions**, with optional “More questions by topic” sections. The exact number is a V1 design choice to test, not a source-derived finding. In each question, prefer one issue and plain patient language. The compiled literacy review emphasizes common words, one idea per sentence, and putting important material first; its cited underlying material was not independently checked here. [E7] Patient responses include examples of missed questions and too much information during a visit, supporting a short initial list as a hypothesis to test rather than a quantified need. [E4]

## Output contract

The visible result should be a one-page, copyable Markdown/HTML “Questions for my visit” card:

1. **My top concern / goal** in the patient's own words, optionally a two-sentence symptom summary in pre-visit mode. Keep patient-reported material visibly labeled as such. [E1]
2. **Ask first**: ordered primary questions, each phrased to ask the clinician, not to imply an answer. If based on a document, show a compact “Why ask” note pointing to the source line, report section, or explicit missing field. [E2, R1]
3. **If there is time**: optional questions grouped by relevant topic, collapsed or lower in the page. The question draft's second layer calls for expandable topic boxes. [E2]
4. **Bring / confirm**: only patient-entered or document-stated items, such as medications, records, or measurements; no inferred medical checklist. This is supported by the prep draft and individual clinician comments. [E1, E5]

Persist a small machine-readable record alongside the display: `mode`, `patient_goal`, `reported_concerns`, ordered question objects with `text`, `topic`, `priority_reason`, `source_refs`, and `status` (`draft`, `chosen`, `removed`), plus source document/run identifiers and extraction quality notices. A deterministic renderer can create Markdown and HTML from this record, following the existing plugin's schema-validated run-folder convention. This is a proposed implementation shape. [R1]

## Grounding and safety

For document-derived questions, distinguish three origins: **document-stated** (cite exact source unit/fact), **document-gap** (identify a specific field absent from the available material without asserting that the clinician failed to discuss it), and **patient-supplied** (quote/paraphrase the user's words). Do not claim a diagnosis, severity, interaction, medication change, urgency threshold, or test interpretation from a generic question template. The existing skill says missing dose/cause/reason is “not stated” rather than guessed, and its pipeline validates fact anchors and citations. [R1]

Questions about concerning symptoms may be phrased as “What symptoms should prompt me to contact your office, and when?” when grounded in the encounter topic. The tool should not invent red flags or triage instructions from the question bank. The bank includes “When should I call your office?” and “When is this urgent?” as questions for a clinician. [E2]

Do not silently add outside medical information. The current plugin deliberately deferred external resources because they add information absent from the document, although a separate source note identifies MedlinePlus as a potential source. If an external-information feature is later approved, label it separately from patient/document facts and verify its citations and freshness in that separate feature. [R2, E3]

Do not present the compiled “Clinics reviews” or “Health Literacy Review” as verified efficacy claims. Their text is useful for design hypotheses (short written agenda, plain language, teach-back), but this work did not read the linked underlying papers. [E7, E8]

## Failure behavior

- No document and no concerns: ask for the appointment topic or one concern; offer a tiny generic starter list only when the user wants it, labeled generic. [E1, E2]
- Source text is missing, truncated, illegible, or low-confidence OCR: disclose that questions may miss details; use only legible source fragments, or switch to patient-supplied pre-visit mode with consent to use those details. The current pipeline already records extraction method and fatal input errors, so `ask` should propagate them rather than pretend coverage. [R1]
- Contradictory documents or dates: cite both, ask a reconciliation question, and avoid resolving the conflict. This extends the existing source-anchoring rule; the local futures list explicitly defers cross-report/longitudinal conclusions until identity and provenance rules exist. [R1, R2]
- No grounded candidate in a topic: omit that topic. If all document-grounded candidates fail verification, return a clear failure/limited result instead of a polished ungrounded list. This follows the current fact-first and citation-check conventions. [R1]

## V1 boundary, later options, and kill test

V1: two explicit modes; short optional pre-visit prompts; source-anchored post-document question generation; a ranked 3–5-question card; editing/reordering; deterministic schema validation and citation checks; Markdown plus self-contained HTML using existing packaging patterns. No live recording, real-time question prompting, diagnosis explanation from the internet, medication advice, longitudinal synthesis, or automatic EHR integration. Those exclusions reflect the two drafts' narrower agenda/question purpose and the existing plugin's source-boundary; they are scope choices, not claims that such features are unhelpful. [E1, E2, R1, R2]

Later: topic expanders with richer UI; vetted external reference links; multilingual output; caregiver-specific view; a bounded follow-up conversation over the existing fact ledger; and, only after distinct consent and product design, in-visit prompting. The current futures file already tracks external resources, translation, caregiver view, and fact-ledger follow-up as separate work. [R2]

Alternatives considered:

| Shape | Advantage | Cost / reason not chosen |
|---|---|---|
| Post-document only | Direct reuse of existing fact ledger and citation logic. [R1] | Leaves the explicit pre-appointment agenda concept uncovered. [E1] |
| Pre-visit only | Light inputs and immediate shareable agenda. [E1] | Leaves the result/diagnosis-specific question bank disconnected from the existing document workflow. [E2, R1] |
| Both modes, shared output (recommended) | Covers both linked use cases with a consistent user-facing artifact. [E1, E2] | Requires mode-specific grounding and separate validation fixtures; manageable if V1 avoids live visit features. [R1] |

Kill test before broad implementation: use a small set of consented/synthetic pre-visit cases and existing de-identified document fixtures. For each, have a patient and clinician reviewer mark (a) whether the top three questions match the patient's real agenda, (b) whether any question contains an unsupported medical assumption, (c) whether the list is short enough to use during a visit, and (d) whether source links point to the right line or a genuinely missing field. Stop or narrow the feature if any unsupported clinical claim survives review, if reviewers repeatedly cannot identify a useful top three, or if source gaps are presented as facts. The criteria operationalize the source drafts' selective question approach and the plugin's current fidelity contract; no numerical effectiveness threshold is claimed from the files. [E1, E2, R1]

Open decisions: exact triggering phrases and whether `ask` is a separate skill or a command inside `simplify-med`; whether a post-document run consumes the verified fact ledger only or also the rendered plan; whether the shareable card includes patient-entered medication lists; how many default questions users prefer; whether the HTML card should reuse the current report renderer; and whether existing report sections get a link to invoke `ask`. Resolve through implementation spike and user review; the source material does not decide these details. [R1, R2]

## Evidence ledger

Each ledger entry cites an actual source body or exact local file. `t.0` spans are native Google Docs paragraph indexes. Sheets coordinates refer to the visible `Form Responses 1` tab; no names, contact fields, or free-text clinical histories are reproduced here.

| ID | Source and stable ID | URL / path | Precise location | Support note |
|---|---|---|---|---|
| E1 | *Prep the patient for his appointment*, `1VOXDWw3CkfStygaqydvAc36zWGiCW_jPpJ4qJvdxnQY` | https://docs.google.com/document/d/1VOXDWw3CkfStygaqydvAc36zWGiCW_jPpJ4qJvdxnQY/edit | `t.0` 41–329, 353–611, 614–1805, 1808–1854 | Proposes pre-visit answers, skipping irrelevant prompts, ranked concerns, symptom details, and patient goal. |
| E2 | *Questions generation*, `1XEraB9pi37vqzsYVGrLUft0jSZfUYsDBEGe-_kEj9Y0` | https://docs.google.com/document/d/1XEraB9pi37vqzsYVGrLUft0jSZfUYsDBEGe-_kEj9Y0/edit | `t.0` 24–480; topic blocks 482–2133 | Universal questions, expandable topic-specific question categories, including monitoring, medications, referral, and timing. |
| E3 | *Sources of reliable information*, `1G1LD3sv-v_b4ZIRt3vZb_2UDiAmuxCh942YkviJ36kc` | https://docs.google.com/document/d/1G1LD3sv-v_b4ZIRt3vZb_2UDiAmuxCh942YkviJ36kc/edit | `t.0` 35–595, 804–1419 | Source note identifies MedlinePlus and its topic/test/drug sections; not consulted externally. |
| E4 | *Patients* survey, `1sSSo_FuikAfjAVb6Lc0L8hlxNyFY_Go9_4qVmDGvLBM` | https://docs.google.com/spreadsheets/d/1sSSo_FuikAfjAVb6Lc0L8hlxNyFY_Go9_4qVmDGvLBM/edit | `Form Responses 1`!D1:E1, D2:E2, D6:E6, D61:E61 | Question fields and example responses reporting missed questions, information overload, or incomplete understanding. Directional examples only. |
| E5 | *Clinicians and Doctors* survey, `1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE` | https://docs.google.com/spreadsheets/d/1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE/edit | `Form Responses 1`!E1:F2, F19:F19 | Individual clinician comments about preparing written questions, medication lists, relevant measurements, and visit data. |
| E6 | *Clinicians and Doctors* survey, same stable ID | https://docs.google.com/spreadsheets/d/1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE/edit | `Form Responses 1`!F2, O2:P2 | Individual clinician comment that AI summaries can be overinclusive and need to be succinct/relevant. |
| E7 | *Health Literacy Review*, `1v4ahswueTnQi72EDagXX21haumlaU6hOLBWl8L0siuc` | https://docs.google.com/document/d/1v4ahswueTnQi72EDagXX21haumlaU6hOLBWl8L0siuc/edit | `t.0` 5737–6124, 56532–56828, 67058–67897, 64666–65105 | Compiled notes on oral communication, plain wording, information order, and encouraging patient questions. Underlying linked sources not opened. |
| E8 | *Clinics reviews*, `1fqE6oHn7rOWoxgm7bvsbOVxhDU2OV_I9aA6-VHv8JoU` | https://docs.google.com/document/d/1fqE6oHn7rOWoxgm7bvsbOVxhDU2OV_I9aA6-VHv8JoU/edit | `t.0` 8297–9955, 2703–4696 | Compiled notes on patient agenda tools and teach-back; useful as design leads only because underlying linked papers were not opened. |
| R1 | Local `skills/simplify-med/SKILL.md`; repo `README.md` | `/root/projects/juno-projects/simplify-med-plugin-add-med-skills/skills/simplify-med/SKILL.md` and `/root/projects/juno-projects/simplify-med-plugin-add-med-skills/README.md` | Skill §§1–2, 5–11; README “How a run works,” “Input contract,” “Run folder layout” | Existing fact-first, source-anchor, extracted-text, schema/run-folder, and rendered-output conventions. |
| R2 | Local `docs/agent_files/2026-09-22-simplify-med-plugin-brief/futures.md` | `/root/projects/juno-projects/simplify-med-plugin-add-med-skills/docs/agent_files/2026-09-22-simplify-med-plugin-brief/futures.md` | “Follow-up conversation guidance,” “External resources,” “Translation,” “Caregiver view,” “Cross-report and longitudinal understanding” | Existing product boundaries and deferred possibilities. |

Access log: all five Docs and both Sheets returned readable content through the connected Google Drive tools. The Sheets were read by exact visible tab name and bounded ranges after metadata; the clinician survey has 21 populated rows in the inspected A:F range and the patient survey 165 in A:E, but no prevalence estimate is used because response completeness and recruitment are unclear from these cells. No external source was opened.
