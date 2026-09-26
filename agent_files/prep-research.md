# Prep skill research brief

## Scope and source discipline

This brief recommends a pre-appointment `prep` skill for the simplify-med plugin. It uses the actual contents of the six supplied Drive files and the checked-out repository. No web pages, linked studies, or other external facts were used. Bracketed evidence IDs point to the ledger below. Product choices are marked as recommendations; they are not claims that a source has validated the design.

All six supplied files were readable. The Google Docs and Sheets were read through their native content tools; the AHRQ PDF was read through its Drive text extraction. The Health Literacy Review is an internal literature compilation, so its citations and summaries are treated as that document's content, not as independent verification of the underlying studies. [E1–E8]

## Recommendation

**User promise (proposed):** “Turn what you want to discuss into a short, editable visit brief and a few questions to bring to your appointment.” This matches the prep proposal's explicit idea: the patient answers only relevant questions and receives a concise summary to share with the doctor. [E1] It also follows the toolkit's advice to encourage questions and prioritize limited, important information. [E6]

The skill should serve a patient or caregiver preparing for a scheduled visit. Its primary output is a patient-owned briefing aid, not a clinical intake form, diagnosis, treatment plan, or replacement for direct conversation. The source proposal asks about concerns, location, start, pattern, severity, effect on life, what helps or worsens it, what has been tried, and the hoped-for outcome. [E1] Patient survey responses include people who selected that they missed critical questions or had too much information to formulate questions, while others selected that they could ask critical questions; the experience is varied. [E3] A small set of clinician responses called symptom logs “Very helpful,” while one free-text response emphasized brevity and relevance. [E4]

## Inputs and interaction

**Required input:** one or more concerns in the patient's own words, plus what they hope to get from the visit. The source proposal begins and ends with those prompts. [E1] Everything else is optional, skippable, and editable. No question should block generation merely because the patient cannot answer it; the proposal explicitly says some questions will not apply. [E1]

**Recommended flow:**

1. Ask what the appointment is for and whether the person is preparing for themself or helping someone else. Offer broad visit paths such as a new concern, ongoing concern or follow-up, preventive visit, injury, or pre/post-procedure visit. These are navigation aids drawn from the categorization document, not diagnoses or mandatory coding. If the visit spans paths, allow “several things” and keep the patient's own label. [E2]
2. Ask for up to three main concerns or questions and let the patient order them. The prep proposal suggests ordering symptoms by priority, and the toolkit advises prioritizing what to discuss and bringing written questions. The “up to three” cap is a V1 design choice, not a demonstrated optimal number for a visit brief. [E1, E6]
3. For each concern, invite targeted follow-ups only where relevant: where it happens, when it began, sudden/gradual onset, duration/frequency, severity if useful, effect on daily life, what changes it, and what the patient has tried and whether it helped. Allow “not sure,” “prefer not to say,” and free text. These prompts come directly from the prep proposal. [E1]
4. Ask what the patient most wants to know or decide at the visit. Turn their goals into editable, plain-language questions. Offer no more than a few candidate questions and label them as suggestions, because the patient's priorities must remain visible. The toolkit recommends inviting questions and reminding people to bring a written list. [E1, E6]
5. Show a draft for correction and let the patient remove any item before sharing. Ask once whether anything important was left out. The patient survey includes varied ways of tracking visit information and symptoms; the output should accommodate a quick review rather than demand a particular tracking habit. [E3]

If the user already provides a structured symptom log, message, or prior note, extract only relevant details from that supplied material and preserve exact wording when uncertainty matters. The existing plugin's document pipeline already works from source text and anchors statements to source units; the prep skill should retain the same “source first” discipline even though its output format differs. [E8]

## Output contract

Produce two views from the same draft:

- **Visit brief:** appointment purpose as stated; ordered concerns; for each, a compact timeline and impact; relevant tried measures; 2–3 patient-approved questions; and the patient's desired outcome. Mark unknowns as “not sure” only when they matter to a question. Keep patient wording visible. This structure is based on the prep prompts and the toolkit's guidance to use the patient's words and limit information load. [E1, E6]
- **Conversation view:** a short list the patient can read aloud or show on a phone, with the top concern and questions first. This is a proposed format responding to the source request for a concise shareable summary and the toolkit's written-question guidance. [E1, E6]

The skill should explicitly identify the content as **prepared from what the patient supplied** and distinguish direct patient statements from generated question suggestions. Do not imply that a clinician has reviewed it. Provide copyable Markdown or plain text in V1; a polished HTML or printable page can follow if user testing finds it helpful. The current simplify-med plugin renders Markdown and HTML after fact checking, but `prep` does not need the existing clinical-document pipeline wholesale. [E8]

## Grounding and safety boundaries

- Do not infer a condition, cause, urgency level, treatment, dose, or test from a symptom description. The source proposal includes a *patient question* about possible contributing events; it does not authorize a generated explanation. [E1]
- Preserve uncertainty, approximate dates, and negative or conflicting statements as given. If the patient says “I think it started last week,” do not convert that to a precise date. This is a proposed rule aligned with the repository's existing “not stated, never guessed” approach. [E8]
- Keep patient-authored facts separate from assistant-authored wording. The assistant may shorten or organize only after the patient can review the result. The toolkit advises using the patient's words and clear language. [E6]
- Do not ask for a full medical history or every medication by default. Allow a patient to add context that they believe matters, especially if a visit is a follow-up. A small clinician survey has comments about missing documents and time constraints, but its sparse responses do not justify making an exhaustive intake mandatory. [E4]
- If the user describes an emergency or asks for urgent triage, step out of the prep flow and tell them to seek immediate local medical help. Do not assert that a generated brief makes waiting safe. This is a proposed product boundary; the appointment categorization document includes emergency encounters but provides no validated triage algorithm for this skill. [E2]
- Treat the brief as sensitive personal information: write only to the requested local run folder, avoid automatic external sharing, and keep the share action patient controlled. This is a product requirement, not an empirical finding from the supplied studies.

## Failure and incomplete-input behavior

- **Only a vague concern supplied:** return a useful minimal brief with that concern and a short prompt for the one missing detail that would most improve the visit conversation. Do not force a questionnaire. [E1]
- **Many concerns or a long pasted log:** preserve all source content in a draft record, but summarize the selected priorities and disclose that the brief omits lower-priority details. Do not silently discard a concern. The priority mechanism is supported by the prep proposal; the exact cap needs testing. [E1]
- **Contradictory or ambiguous details:** show them as unresolved for patient correction; never choose one silently. This follows the repository's source-anchored approach. [E8]
- **No date, severity, or attempted treatment:** omit that field or say “not sure” if the absence itself is useful; never fill from typical cases. [E1, E8]
- **Cannot safely interpret an attachment:** state which input could not be read, use the readable patient-provided content, and request a pasted excerpt or clearer file. Do not claim complete coverage.
- **Potentially urgent issue:** interrupt the normal brief workflow with the safety message above; if the patient still wants a brief after addressing the urgent need, use only their reported details.

## V1 and later

**Minimal V1:** one patient session; optional adaptive prompts; ordered concerns; editable one-page text brief; editable question suggestions; explicit patient-source labels; no diagnosis or clinical scoring; local run artifacts and simple source trace for each output line. This scope directly covers the prep proposal and can be validated without clinician integration. [E1]

**Later, only if validated:** save/reuse recurring symptom logs, import documents with an explicit source map, caregiver collaboration, language variants, print/HTML layouts, and visit-type-specific prompt sets. The patient survey includes a question about how people record symptoms between recurring appointments, and the toolkit discusses language and accessible written materials; those sources suggest directions for exploration, not proof that any particular implementation will be used. [E5, E7]

**Avoid in V1:** automatic clinical coding from the categorization document, EHR upload, full-history intake, generated differential diagnoses, and automated emergency triage. The categorization source inventories categories and codes; it does not establish that coding improves a patient-owned prep brief. [E2]

## Validation and tests

1. **Source fidelity:** on synthetic cases, every factual sentence in the brief maps to patient input; question suggestions are clearly marked. Include conflicting dates, uncertain wording, multiple symptoms, and a caregiver speaking for someone else. This matches the existing plugin's fact-first convention. [E8]
2. **Coverage and editability:** test that each concern, its priority, and the patient's desired outcome survive the draft and revision cycle, while optional unanswered prompts stay optional. [E1]
3. **Plain-language review:** check that summaries keep patient vocabulary, lead with important information, use short chunks, and avoid unnecessary medical jargon. The toolkit's Tool #4 provides those communication principles; Tool #14 supports a written list of questions. [E6]
4. **Usability study:** ask patients to prepare a brief from a realistic appointment scenario, then ask whether the brief captures what they would bring, whether any question feels intrusive, and whether they can remove or correct an item. Include participants with different communication and language preferences. The toolkit recommends getting patient feedback on materials; the surveys show heterogeneous responses. [E3, E7]
5. **Clinician review:** have clinicians judge a small blinded set for brevity, relevance, and whether the patient's priority is obvious. The clinician survey's relevant response count is too small to set acceptance thresholds. [E4]
6. **Failure cases:** verify that unreadable files, empty input, contradictory details, and potential urgency produce explicit safe behavior. This is a proposed test requirement.

Suggested acceptance gates for a prototype (targets to set before testing, not source-derived facts): zero invented clinical facts in the synthetic evaluation set; no loss of a user-marked top concern; every output editable before sharing; and no automatic external transmission. Completion time and preferred length should be measured with users rather than stipulated from these sources.

## Alternatives and tradeoffs

| Option | Benefit | Cost / reason for recommendation |
| --- | --- | --- |
| Fixed long questionnaire | Uniform fields | Conflicts with the prep proposal's optional-question rule and risks burying the patient's priority. Use adaptive prompts. [E1] |
| Free-form chat only | Low initial friction | Can leave useful timing and impact details unstated. Use a few targeted follow-ups drawn from the proposal. [E1] |
| Visit-type-specific forms from day one | May make prompts feel relevant | The categorization source is broad and includes coding detail beyond a patient brief; first test one common flow with optional branching. [E2] |
| Auto-generated “doctor-ready” medical summary | Could look polished | Risks overclaiming authority and losing the patient's voice. Keep it visibly patient-authored and editable. [E1, E6] |
| Reuse simplify-med's full fact pipeline | Strong existing audit machinery | Its input/output are designed for existing clinical documents and care plans, while prep begins with patient-entered concerns. Reuse grounding principles and small validators, not the entire stage graph. [E8] |

## Kill test and open decisions

**Kill test:** In a small observed trial, if patients cannot recognize their own top concern in the generated brief, or clinicians consistently find the brief too long or misleading after edits, do not ship the generated-summary feature. Retain a simple editable question list. This is a proposed go/no-go test, not a result claimed by the sources. The clinician survey contains a direct concern about overinclusive summaries, making brevity a worthwhile test target. [E4]

Open product decisions before implementation:

1. Is V1 for patients only, or should a caregiver be able to label whose words and observations each item represents? The patient survey includes a caregiver question but does not settle the workflow. [E3]
2. What is the exact default length and number of priority questions after usability testing? The sources favor concision but give no validated threshold for this product. [E1, E6]
3. Should an existing appointment category be shown to the patient, or used only to route prompts? The categorization document supplies possible categories but no tested patient wording. [E2]
4. Which local artifact contract should `prep` use, and should it share any scripts with `simplify-med`? The current plugin has run folders, schema checks, and Markdown/HTML output, but those contracts were built for document simplification. [E8]
5. How will the product handle translation and non-English user input, including review by a qualified human when clinical nuance matters? The toolkit discusses language differences, but this source set does not validate an automated translation workflow. [E5]

## Evidence ledger

Each ledger entry names the actual file read. Locations are native Doc indexes, Sheet ranges, PDF printed page/tool labels, or repository lines. The support note limits what can be concluded. Survey figures refer to response cells, not a population estimate; empty cells and mixed-choice answers are not treated as negative responses.

| ID | Source name and stable ID | URL | Location | Support note |
| --- | --- | --- | --- | --- |
| E1 | “Prep the patient for his appointment”; Doc `1VOXDWw3CkfStygaqydvAc36zWGiCW_jPpJ4qJvdxnQY` | https://docs.google.com/document/d/1VOXDWw3CkfStygaqydvAc36zWGiCW_jPpJ4qJvdxnQY/edit | Tab `t.0`, indexes 41–1854, especially 41–329, 353–611, 746–1805, 1808–1854 | Proposes relevant optional questions, patient priorities, symptom details, and concise doctor-shareable summary. A design proposal, not evidence of efficacy. |
| E2 | “Categorization of appointments and tests results”; Doc `1D9D7s54w7q1zFnyLQWEEYlW_Pji3PBfFd3DxRYsfq-o` | https://docs.google.com/document/d/1D9D7s54w7q1zFnyLQWEEYlW_Pji3PBfFd3DxRYsfq-o/edit | Tab `t.0`, indexes 54–875 and 3311–3595 | Lists broad appointment purposes and appointment-reason codes. Internal compilation; not an independently checked clinical standard or triage rule. |
| E3 | “Patients”; Sheet `1sSSo_FuikAfjAVb6Lc0L8hlxNyFY_Go9_4qVmDGvLBM`, tab ID `242813098` | https://docs.google.com/spreadsheets/d/1sSSo_FuikAfjAVb6Lc0L8hlxNyFY_Go9_4qVmDGvLBM/edit | `Form Responses 1`!B1:E166, H1:K166, S1:T166; notably D2:D166 and E2:E166 | Actual response cells: D has 162 nonblank answers, including 53 exact “some questions, but missed critical questions,” 16 exact “too much information,” and 66 exact “critical questions”; E has 160 nonblank answers, including 76 exact “understood some of it, had some follow ups.” Other ranges show varied tracking methods. These are descriptive counts, not representative rates. |
| E4 | “Clinicians and Doctors”; Sheet `1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE`, tab ID `580828990` | https://docs.google.com/spreadsheets/d/1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE/edit | `Form Responses 1`!B1:E15 and N1:Q17 | N has four nonblank “Very helpful” responses on symptom logs. E has eight nonblank barrier responses, several mentioning missing records or time. P includes one comment warning about overinclusive, irrelevant summaries. Sparse, qualitative product signal only. |
| E5 | AHRQ Health Literacy Universal Precautions Toolkit, 3rd ed.; PDF `18u5e2H1ZSDIeQRiT_pes8x0sAUvcsUVL` | https://drive.google.com/file/d/18u5e2H1ZSDIeQRiT_pes8x0sAUvcsUVL/view | Introduction pp. vii–ix; Tool #9 p.31 and Tool #11 p.41 in PDF text/table of contents | Toolkit explicitly covers universal precautions, language differences, and easy-to-understand written materials. Used for design considerations, not quantitative efficacy claims. |
| E6 | Same AHRQ PDF `18u5e2H1ZSDIeQRiT_pes8x0sAUvcsUVL` | https://drive.google.com/file/d/18u5e2H1ZSDIeQRiT_pes8x0sAUvcsUVL/view | Tool #4 printed pp.11–13; Tool #14 printed pp.54–55 | Recommends listening to the patient's story, prioritizing key points, using patient's words/plain language, inviting questions, and reminding patients to bring a written question list. |
| E7 | “Health Literacy Review”; Doc `1v4ahswueTnQi72EDagXX21haumlaU6hOLBWl8L0siuc` | https://docs.google.com/document/d/1v4ahswueTnQi72EDagXX21haumlaU6hOLBWl8L0siuc/edit | Tab `t.0`, indexes 55916–65699, especially 56238–56997, 57575–58281, 64666–65105, 65413–65699 | Internal compilation restates clear-language, written-question, and patient-feedback guidance. Underlying linked studies and external resources were not opened or treated as independently verified. |
| E8 | Repository README and `simplify-med` skill at commit `6c0baff770deed6f9e9e842b87a073ac931acc3e` | https://github.com/tejitpabari99/simplify-med-plugin/blob/6c0baff770deed6f9e9e842b87a073ac931acc3e/README.md ; https://github.com/tejitpabari99/simplify-med-plugin/blob/6c0baff770deed6f9e9e842b87a073ac931acc3e/skills/simplify-med/SKILL.md | README lines 1–9, 47–79, 103–121; SKILL.md lines 18–36, 110–185 | Existing implementation is a source-anchored clinical-document simplifier with `.txt` input, staged checks, run artifacts, and Markdown/HTML output. This is implementation context, not prep product validation. |

No external facts were added. No source was unreadable. The report does not claim that the surveys are representative, that the proposed prep flow improves outcomes, or that the appointment codes are a validated triage system.
