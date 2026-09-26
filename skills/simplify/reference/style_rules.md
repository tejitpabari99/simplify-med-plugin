# Style rules

PII -- replace every person's name and every facility's name with a generic form: a clinician's name becomes "your doctor" (or "your surgeon" / "your cardiologist" / etc. if the fact itself names that specialty); a hospital or clinic name becomes "the hospital" or "the clinic." Example: "Doctor Alok Singh" becomes "your doctor." This is the one case where you do not preserve a fact's exact wording -- a generic form loses the patient no clinical information. The patient's own name, date of birth, address, and insurance details must never appear either.

NUMERACY -- a number is the easiest place to silently add a judgement the source never made, so give every one in this document the same verbatim discipline PII gets for names, plus one allowance: copy a value and its unit exactly as the fact states them ("A1c 7.2%" stays "your A1c was 7.2%"), changing only spacing or spelling the way LANGUAGE RULES below already permits ("metoprolol 25mg" -> "metoprolol 25 mg" is fine; the number and the unit itself are not). Never add a normal/abnormal/elevated/low/high label to a bare value unless the fact itself uses that word -- a fact giving "blood pressure 158/96" is a number, not a verdict; do not write "high blood pressure" for it unless a fact says so. Never add a reference range that isn't in the fact -- "A1c 7.2%" does not become "A1c 7.2% (normal range 4.0-5.6%)." Never round, truncate, or otherwise adjust an already-exact number -- "ejection fraction 42%" stays "42%," never "about 40%" or "40%." Never convert a unit -- "creatinine 1.4 mg/dL" stays mg/dL, never becomes a value you compute yourself in µmol/L. Never reframe a percentage as a frequency or a frequency as a percentage -- "occurs in 30% of patients" does not become "happens 3 out of 10 times you take it," and "taken twice daily" does not become "100% compliance." Never attach a severity, urgency, or color ("critical," "dangerously high," "mild") to a number the fact does not itself grade. You may add an interpretation of a number ONLY when the fact itself already states that interpretation in its own words -- a fact reading "A1c 7.2%, indicating poor control" may carry "indicating poor control" into the rendered field, because the source made that judgement, not you.

LANGUAGE RULES -- apply to every field you write:
- Active voice. Address the patient as "you."
- One idea per sentence. Keep sentences under about 20 words.
- Expand every abbreviation. Never print "BID", "HTN", "f/u", or similar -- use the plain words.
- Never invent a number, and never convert vague wording ("a few weeks") into an exact one ("3 weeks") unless a fact states the exact number -- see NUMERACY above for the rest of this document's numeric rules.
- Never add urgency, prognosis, or medical advice beyond what a fact states.
- Start every patient action (in medications, tests, procedures, other, follow_up) with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop.
- Aim for about a 6th-grade reading level: short common words, one idea per sentence.
- Lead with the main message and the next action. Keep supporting detail out of the first view.
- Do not repeat a fact in multiple sections unless repetition is needed to prevent a safety error.
- Leave an optional field empty or null when the source does not state it. Do not write filler such as "not stated in your note" into patient-facing text.

CRITICAL VS SUPPORTING -- preserve what changes understanding, action, or safety:

The goal is not to display every extracted fact. The goal is a concise, source-grounded explanation of what happened, what matters now, and what the patient should do next. Concision is a requirement, not a reason to omit critical content.

Critical patient-facing content normally includes:
- the main reason for the visit;
- the clinician's main conclusion, documented diagnosis, or important unresolved finding;
- medication starts, stops, changes, exact doses, frequencies, timing, and home-use instructions;
- pending tests, referrals, appointments, monitoring, follow-up timing, and who to contact;
- explicit warning signs with the source's action and urgency;
- uncertainty, conflicts, declined or conditional treatment, and missing details that could change an action;
- a reassuring result when it directly explains the disposition or next step.

Supporting content normally stays out of the patient-facing report:
- technical test mechanics, including contrast names or doses, machine settings, sequences, and measurement metadata;
- raw normal values, incidental findings, or completed-test inventories that do not change the plan;
- repeated facts already represented clearly;
- rejected, non-actionable differential diagnoses;
- generic education, broad wellness guidance, or conditional advice that is not patient-specific;
- stable background history or medicines that did not change and do not explain the visit.

Generic education does not become patient-specific merely because it was attached to discharge paperwork. Include it only when the clinical record applies it to this patient, it changes this patient's documented action, or omitting it would change what the patient treats as urgent. When supporting content is omitted, keep it auditable through the structured omission disposition required by the care-plan schema; do not expand it into visible prose.

PLAIN WORDS -- `reference/ahrq_plain_language.json` lists medical words and their everyday alternatives. Prefer the everyday alternative; when a medical term must stay (a diagnosis name, a drug name), keep it and put the plain meaning next to it once.
