# Style rules

These rules apply to every patient-visible string the writer produces and every
fix the verifier makes.

SOURCES -- the source text is the only evidence: what the user pasted, the text of files they uploaded, and their own records retrieved at their request from a connected health-records app. Never search the web, open links, or look anything up in any outside source, and never add a detail, value, reason, or explanation from general medical knowledge. Never describe or interpret a medical image (X-ray, CT, MRI, ultrasound, ECG tracing, photo of the body); only the written words in the source count. If the source does not state something, leave it out or empty.

PII -- replace every person's name and every facility's name with a generic form: a clinician's name becomes "your doctor" (or "your surgeon" / "your cardiologist" / "the ER doctor" when the source names that role); a hospital or clinic name becomes "the hospital" or "the clinic." Example: "Doctor Alok Singh" becomes "your doctor." This is the one case where you do not keep the source's exact wording -- a generic form loses the patient no clinical information. The patient's own name, date of birth, medical record number, account number, address, phone number, and insurance details must never appear.

NUMERACY -- a number is the easiest place to silently add a judgement the source never made, so give every number the same verbatim discipline PII gets for names. Every number in an item must appear in that item's evidence quote. Copy a value and its unit exactly as the source states them ("A1c 7.2%" stays "your A1c was 7.2%"), changing only spacing or spelling ("metoprolol 25mg" -> "metoprolol 25 mg" is fine; the number and the unit are not). Writing a frequency code as words is fine ("TID" -> "three times a day"). Never add a normal/abnormal/elevated/low/high label to a bare value unless the source uses that word -- "blood pressure 158/96" is a number, not a verdict. Never add a reference range the source does not give. Never round, truncate, or adjust an exact number -- "ejection fraction 42%" stays "42%," never "about 40%." Never convert a unit. Never reframe a percentage as a frequency or a frequency as a percentage. Never attach a severity, urgency, or color ("critical," "dangerously high," "mild") to a number the source does not grade. Show a number only when the number itself matters to the patient: a dose, a date, a follow-up interval, or a value the clinician calls out or that drives the plan.

LANGUAGE RULES -- apply to every visible string:
- Active voice. Address the patient as "you."
- One idea per sentence. Keep sentences under about 20 words.
- Write clinical shorthand out in full ("BID", "HTN", "f/u", "RBBB" become plain words). Names patients already know, such as ER, CT, MRI, and COVID-19, may stay. If the report uses a term again, the first mention may add its short name in parentheses and later mentions may use it ("first-degree atrioventricular (AV) block", then "AV block"). `reference/abbreviations.json` is an optional lookup for common shorthand.
- Never expand a short name into a longer, harder word for no gain, and never leave jargon unexplained: if a term cannot be put in plain words from the source, state what the source concluded about it and leave the term out.
- Never invent a number, and never turn vague wording ("a few weeks") into an exact one ("3 weeks").
- Translate, don't interpret. Replacing a term with everyday words that mean the same thing is translation and is fine ("infarct" -> "stroke", "paresthesias" -> "tingling"). Adding a diagnosis, label, cause, purpose, urgency, prognosis, range, or "normal"/"reassuring" verdict the source does not state is interpretation and is not allowed.
- Keep the source's exact conclusion word. "Significant" is not "major"; "possible" is not "likely"; "cannot exclude" is not "ruled out"; "not concerning for" is not "normal."
- Preserve negation and uncertainty exactly. Unknown is not negative: if the source does not say something, leave it out rather than stating that it did not happen.
- Start every patient action with a clear verb: Take / Call / Schedule / Get / Ask / Bring / Watch / Avoid / Continue / Stop / Return / Go. Keep the source's timing and reason for the action.
- Aim for about a 6th-grade reading level: short common words.
- Say each thing once. Do not repeat a point in two sections unless repetition prevents a safety error.
- Leave an optional slot empty or null when the source does not support it. Never write filler such as "not stated in your note."
- Never leave empty brackets such as "()" or "[]" in visible text.

PLAIN WORDS -- prefer the everyday word for a medical term the source uses (translation, above). When a medical term must stay (a diagnosis name, a drug name), keep it; give its plain meaning only when the source itself states that meaning (an education sheet, the discharge instructions, the clinician's words), and give it once. Never explain a term from general medical knowledge. This rule and SOURCES never conflict: translation swaps words, explanation needs the source.

SHOW -- the report answers four questions: why did I go, what did they find, what do I do now, and when do I get help. Show, in a few words each:
- why the patient came: every complaint and referral reason the source lists;
- the bottom line of each important test or exam area, taken from the source's conclusion (radiology Impression, clinician assessment), one bullet per area;
- diagnoses stated for this visit;
- the disposition as stated (discharged, admitted, stable condition);
- follow-up, tests to schedule, and home instructions stated for this patient, with their timing and reason;
- medicine starts, stops, dose changes, and home instructions -- or one statement that no new medicines were prescribed, when the source says so;
- return precautions with the source's own action and urgency;
- abnormal or pending results the clinician calls out or that change what the patient does, with when and how a pending result will be shared;
- a disagreement between sources that matters (for example, an urgent-care read and the ER read of the same test), in one sentence.

SKIP -- keep out of the report:
- sub-findings, sequences, technique, reconstructions, criteria names, and contrast or other agents given during a test;
- lab inventories and vital signs -- use the clinician's summary word ("unremarkable") in one grouped bullet, or a specific value only when the clinician calls it out or it drives the plan;
- empty or unchanged medication lists, "no medications on file," "no known allergies," and "no past medical history on file" rows;
- charted background, old problem-list items, and history not addressed this visit;
- superseded or conditional plans the source later replaced, and another clinic's earlier advice unless this visit repeats it;
- generic radiology or form boilerplate ("correlate clinically," "discuss imaging findings with the ordering provider") -- never turn it into an appointment or action;
- generic education not applied to this patient, even when it was attached to the discharge paperwork;
- portal headers, page counters, URLs, repeated pages, signatures, billing, and other administrative text;
- anything already said elsewhere in the report.
