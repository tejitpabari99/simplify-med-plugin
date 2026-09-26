# Category checklist

| Category | Criteria | Boundary rule |
|---|---|---|
| reason_for_visit | Why the patient presented -- complaint, symptom, or referral reason | Not the diagnosis. What they came WITH, not what was FOUND. |
| diagnosis | Conditions, findings and interpretations the clinician recorded | Includes imaging and lab findings stated as conclusions. Excludes the raw measurement, which belongs to the test. |
| medications | Substances the patient takes THEMSELVES, AT HOME | Anything administered DURING a test or procedure belongs to that item instead -- never to medications. Example: contrast dye given during a CT scan is a fact about the scan (category "tests" or "procedures"), never "medications". |
| tests | Diagnostic investigations -- labs, imaging, tracings | Covers both already-performed and newly-ordered tests. |
| procedures | Interventions performed ON the patient | Carries any substance administered during it (see the medications boundary rule above). |
| other | Instructions that are none of the above -- diet, activity, wound care, self-monitoring | If it names a date or an appointment, it is follow_up instead. |
| follow_up | A future appointment or contact, with timing | Not a general instruction. Must involve seeing or contacting someone. |
| warning_signs | Symptoms the note tells the patient to watch for | Must come with what to do, from the note. A side effect that is merely LISTED, with no instruction to act on it, is NOT a warning sign -- extract it as part of the medication's own fact instead. |

Every fact gets exactly one category; where two could apply, the boundary rules decide.

Billing codes, insurance details, appointment scheduling metadata, and other administrative text are not facts. Do not extract them.
