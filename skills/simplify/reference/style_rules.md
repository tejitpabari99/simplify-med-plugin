# Style rules

These rules apply to every patient-visible string the writer produces and every
replacement value the verifier proposes.

PII -- replace every person's name and every facility's name with a generic form: a clinician's name becomes "your doctor" (or "your surgeon" / "your cardiologist" / "the ER doctor" when the source names that role); a hospital or clinic name becomes "the hospital" or "the clinic." Example: "Doctor Alok Singh" becomes "your doctor." This is the one case where you do not keep the source's exact wording -- a generic form loses the patient no clinical information. The patient's own name, date of birth, medical record number, address, phone number, and insurance details must never appear.

NUMERACY -- a number is the easiest place to silently add a judgement the source never made, so give every number the same verbatim discipline PII gets for names. Copy a value and its unit exactly as the cited source unit states them ("A1c 7.2%" stays "your A1c was 7.2%"), changing only spacing or spelling the way LANGUAGE RULES below permit ("metoprolol 25mg" -> "metoprolol 25 mg" is fine; the number and the unit itself are not). Never add a normal/abnormal/elevated/low/high label to a bare value unless the source uses that word -- "blood pressure 158/96" is a number, not a verdict. Never add a reference range the source does not give. Never round, truncate, or adjust an exact number -- "ejection fraction 42%" stays "42%," never "about 40%." Never convert a unit. Never reframe a percentage as a frequency or a frequency as a percentage. Never attach a severity, urgency, or color ("critical," "dangerously high," "mild") to a number the source does not grade. You may carry an interpretation of a number only when the source states it in its own words ("A1c 7.2%, indicating poor control"). Show a number only when the number itself matters to the patient: a dose, a date, a follow-up interval, or a value the clinician calls out or that drives the plan.

LANGUAGE RULES -- apply to every visible string:
- Active voice. Address the patient as "you."
- One idea per sentence. Keep sentences under about 20 words.
- Expand clinical shorthand. Never print "BID", "HTN", "f/u", "RBBB", or similar -- use the plain words. Names patients already know, such as ER, CT, and MRI, may stay. `reference/abbreviations.json` is an optional lookup.
- Never invent a number, and never turn vague wording ("a few weeks") into an exact one ("3 weeks").
- Translate, don't interpret. Plain words for a term the source uses are fine ("infarct" -> "stroke", "paresthesias" -> "tingling"). Adding a diagnosis, label, cause, purpose, urgency, prognosis, range, or "normal"/"reassuring" verdict the source does not state is not.
- Keep the source's exact conclusion word. "Significant" is not "major"; "possible" is not "likely"; "cannot exclude" is not "ruled out"; "not concerning for" is not "normal."
- Preserve negation and uncertainty exactly. Unknown is not negative: if the source does not say something, leave it out rather than stating that it did not happen.
- Start every patient action with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop / Return.
- Aim for about a 6th-grade reading level: short common words.
- Say each thing once. Do not repeat a point in two sections unless repetition prevents a safety error.
- Leave an optional slot empty or null when the source does not support it. Never write filler such as "not stated in your note."
- Never leave empty brackets such as "()" or "[]" in visible text.

SHOW -- the report answers four questions: what happened, what did they find, what do I do now, and when do I come back. Show, in a few words each:
- why the patient came (complaint and referral reason);
- the bottom line of each important test or exam area, taken from the source's conclusion (radiology Impression, clinician assessment), one bullet per area;
- diagnoses stated for this visit;
- the disposition as stated (discharged, admitted, stable condition, no emergency cause found);
- follow-up, tests to schedule, and home instructions stated for this patient;
- medicine starts, stops, dose changes, and home instructions -- or one statement that no new medicines were prescribed, when the source says so;
- return precautions with the source's own action and urgency;
- abnormal or pending results the clinician calls out or that change what the patient does;
- a disagreement between sources that matters (for example, an urgent-care read and the ER read of the same test), in one sentence.

SKIP -- keep out of the report:
- sub-findings, sequences, technique, reconstructions, criteria names, and contrast or other agents given during a test;
- lab inventories and vital signs -- use the clinician's summary word ("unremarkable") in one grouped bullet, or a specific value only when the clinician calls it out or it drives the plan;
- empty or unchanged medication lists, "no medications on file," "no known allergies," and "no past medical history on file" rows;
- charted background, old problem-list items, and history not addressed this visit;
- superseded or conditional plans the source later replaced;
- generic radiology or form boilerplate ("correlate clinically," "discuss imaging findings with the ordering provider") -- never turn it into an appointment or action;
- generic education not applied to this patient, even when it was attached to the discharge paperwork;
- portal headers, page counters, URLs, billing, and other administrative text;
- anything already said elsewhere in the report.

PLAIN WORDS -- `reference/ahrq_plain_language.json` is an optional lookup of medical words and everyday alternatives. Prefer the everyday word; when a medical term must stay (a diagnosis name, a drug name), keep it and give the plain meaning once.
