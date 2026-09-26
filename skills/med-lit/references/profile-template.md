# Profile Template

Produce the Markdown profile, then the structured block. Omit empty optional sections. Keep it short.

## Markdown profile

```markdown
# My health-information profile

**Date:** <YYYY-MM-DD> · **Answered by:** <me / caregiver on my behalf> · **Language:** <preferred language>

## Brief screen (BHLS)
<one of the following>
- **Total: <N>/15** (<i1> + <i2> + <i3>). Higher totals mean fewer reported difficulties with written health information and forms.
- **No score.** <reason: skipped item / not administered / deviation>.

What I reported:
- Filling out medical forms by myself: <option>
- Having someone help me read hospital materials: <option>
- Problems learning about my condition from written information: <option>

<If any item scored 3 or less:> Areas where I reported difficulty: <items in plain words>.

## What helps me
- Preferred format: <as stated>
- Tasks I find hard: <as stated>
- Supports I would like: <as stated>
- Usually helped by: <relationship, if stated>

## About this profile
- A brief self-report screen, taken in chat. Published BHLS cutoffs may not apply to this chat administration.
- Not assessed: numbers and numeracy, finding or judging health information, talking with clinicians, digital skills.
- Not a diagnosis and not a measure of intelligence. Answers can reflect the materials and healthcare system as much as personal skill.
```

For the support-needs-only path, replace the screen section with: "**No validated literacy level measured.** This is a profile of self-reported support needs and preferences."

## Structured profile

Include this JSON after the Markdown so the profile can be reused later. Use `null` for unknown values and empty arrays for empty lists. Never add a universal level field.

```json
{
  "profile_version": 1,
  "subject": "patient_self_report",
  "assessment_date": "YYYY-MM-DD",
  "instrument": "BHLS",
  "instrument_source": "Brief Health Literacy Screen; Sand-Jecklin & Coyle 2014; Wallston et al. 2014",
  "language": "English",
  "administration": {
    "mode": "chat_text",
    "validated_mode": false,
    "deviations": []
  },
  "responses": [
    {"item_id": "bhls_confidence_forms", "option": "Somewhat", "points": 3},
    {"item_id": "bhls_help_reading", "option": "None of the time", "points": 5},
    {"item_id": "bhls_problems_learning", "option": "A little of the time", "points": 4}
  ],
  "score": 12,
  "score_range": [3, 15],
  "score_direction": "higher_means_fewer_reported_difficulties",
  "score_eligible": true,
  "interpretation": {
    "label": null,
    "scope": "Self-report screen of difficulty with written health information and forms.",
    "cutoff_source": null
  },
  "observed_task_needs": [
    {"task": "understanding test results or numbers", "basis": "self_reported"}
  ],
  "patient_preferences": {
    "information_language": "English",
    "conversation_language": "English",
    "formats": ["written", "pictures or diagrams"],
    "supports": ["plain-language summaries", "written question list"],
    "helper_relationship": null
  },
  "coverage_limits": [
    "chat administration not validated; published cutoffs may not apply",
    "numeracy not assessed",
    "finding and appraising information not assessed",
    "oral communication not assessed",
    "digital skills not assessed"
  ]
}
```

The example values are illustrative, not a patient result.

Field rules:

- `subject`: `patient_self_report` or `proxy_report`.
- `instrument`: `BHLS`, `SILS`, or `none`.
- `responses[].option`: the exact option text, or `"not_answered"` with `points: null`.
- `score`: the sum of points, or `null` when `score_eligible` is `false`.
- `interpretation.label`: always `null` for chat administration.
