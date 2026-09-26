"""Validate de-identified research outputs after generation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd
from PIL import Image


EXPECTED_FIGURES = [
    "01_current_skill_support.png",
    "02_patient_problem_signals.png",
    "03_clinician_appointment_barriers.png",
    "04_unmet_needs.png",
    "05_connected_care_journey.png",
]

EXPECTED_DATA = [
    "analysis_snapshot.json",
    "current_skill_support.csv",
    "data_quality.csv",
    "evidence_ledger.csv",
    "metrics.csv",
    "source_inventory.csv",
    "unmet_needs.csv",
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Generated user research directory.",
    )
    args = parser.parse_args()
    root = args.output_dir.resolve()

    missing = [
        str(root / "figures" / name)
        for name in EXPECTED_FIGURES
        if not (root / "figures" / name).exists()
    ]
    missing.extend(
        str(root / "data" / name)
        for name in EXPECTED_DATA
        if not (root / "data" / name).exists()
    )
    if missing:
        raise SystemExit("Missing expected outputs:\n" + "\n".join(missing))

    metrics = pd.read_csv(root / "data" / "metrics.csv")
    if (metrics["count"] > metrics["denominator"]).any():
        raise SystemExit("A metric numerator exceeds its denominator.")
    expected_percent = (100 * metrics["count"] / metrics["denominator"]).round(1)
    if not expected_percent.equals(metrics["percent"].round(1)):
        raise SystemExit("Metric percentage arithmetic is inconsistent.")

    snapshot = json.loads((root / "data" / "analysis_snapshot.json").read_text())
    if snapshot["source_checks"]["patient_unique_submissions"] != 164:
        raise SystemExit("Unexpected patient unique-submission count.")
    if snapshot["source_checks"]["patient_interview_unique_units"] != 21:
        raise SystemExit("Unexpected patient interview-unit count.")
    if snapshot["source_checks"]["clinician_qualitative_units"] != 19:
        raise SystemExit("Unexpected clinician qualitative-unit count.")

    for name in EXPECTED_FIGURES:
        path = root / "figures" / name
        with Image.open(path) as image:
            if image.width < 1200 or image.height < 400:
                raise SystemExit(f"Figure is unexpectedly small: {path}")

    interactive = root / "interactive" / "research-evidence-explorer.html"
    interactive_text = interactive.read_text(encoding="utf-8")
    if interactive.stat().st_size >= 1_000_000:
        raise SystemExit("Interactive visualization exceeds 1 MB.")
    forbidden_fragment_tokens = ["<!doctype", "<html", "<head", "<body", "fetch("]
    if any(token in interactive_text.lower() for token in forbidden_fragment_tokens):
        raise SystemExit("Interactive visualization is not a safe HTML fragment.")

    scan_paths = [
        *sorted((root / "data").glob("*.csv")),
        *sorted((root / "data").glob("*.json")),
        root / "research-report.md",
    ]
    findings: list[str] = []
    for path in scan_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if EMAIL_PATTERN.search(text):
            findings.append(f"email-like value in {path}")
        if PHONE_PATTERN.search(text):
            findings.append(f"phone-like value in {path}")
    if findings:
        raise SystemExit("Potential PII found:\n" + "\n".join(findings))

    print(
        json.dumps(
            {
                "status": "ok",
                "metrics": len(metrics),
                "figures": len(EXPECTED_FIGURES),
                "interactive_visualizations": 1,
                "patient_unique_submissions": 164,
                "patient_interview_units": 21,
                "clinician_qualitative_units": 19,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
