# User and clinician research package

This folder contains a de-identified, reproducible analysis of the connected
Project 1 patient, caregiver, and clinician research.

- [`research-report.md`](research-report.md): main findings, excerpts, product implications, and limitations.
- [`figures/`](figures/): five generated PNG figures.
- [`interactive/research-evidence-explorer.html`](interactive/research-evidence-explorer.html): source for the interactive evidence explorer.
- [`data/`](data/): de-identified aggregate metrics, coded excerpts, source inventory, and data-quality notes.
- [`scripts/analyze_user_research.py`](scripts/analyze_user_research.py): rebuilds all aggregate outputs and PNGs from local spreadsheet exports.
- [`scripts/validate_research_outputs.py`](scripts/validate_research_outputs.py): validates metric arithmetic, expected outputs, image dimensions, and common PII patterns.

Raw Google Drive exports are intentionally not committed because the source
files contain personal contact information. To rerun:

```powershell
python user/scripts/analyze_user_research.py --source-dir <export-directory> --output-dir user
python user/scripts/validate_research_outputs.py --output-dir user
```

The export directory must contain:

- `patients.xlsx`
- `patient_survey_original.xlsx`
- `clinicians.xlsx`
- `clinician_survey_original.xlsx`
- `patient_interviews.xlsx`

