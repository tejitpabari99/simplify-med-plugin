"""Build de-identified research metrics and static PNG figures.

The script intentionally reads raw Google Sheets exports from a temporary
directory and writes only aggregates, coded row references, and short
de-identified excerpts into the repository.

Usage:
    python analyze_user_research.py --source-dir <export-dir> --output-dir ../
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PATIENTS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1sSSo_FuikAfjAVb6Lc0L8hlxNyFY_Go9_4qVmDGvLBM/edit"
)
CLINICIANS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1IYGhg7QleCuXmskUatl28-I-xBD-cMxeVKsjSP4zDxE/edit"
)
PATIENT_INTERVIEWS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1V1wd-FOJdwuaMUajr430MmvDHlbUWPcuhFRKGXaCFh0/edit"
)


def find_col(df: pd.DataFrame, prefix: str) -> str:
    exact = [str(col) for col in df.columns if str(col) == prefix]
    if len(exact) == 1:
        return exact[0]
    matches = [str(col) for col in df.columns if str(col).startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one column beginning {prefix!r}; found {matches}")
    return matches[0]


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\ufffd", "'")
    return re.sub(r"\s+", " ", text).strip()


def count_contains(series: pd.Series, pattern: str) -> tuple[int, int]:
    valid = series.dropna().astype(str)
    return int(valid.str.contains(pattern, case=False, regex=True).sum()), int(len(valid))


def score_count(
    series: pd.Series, predicate: Callable[[pd.Series], pd.Series]
) -> tuple[int, int, float, float]:
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    return (
        int(predicate(valid).sum()),
        int(valid.shape[0]),
        float(valid.mean()),
        float(valid.median()),
    )


def metric_row(
    metric_id: str,
    audience: str,
    category: str,
    label: str,
    count: int,
    denominator: int,
    basis: str,
    source: str,
) -> dict[str, object]:
    return {
        "metric_id": metric_id,
        "audience": audience,
        "category": category,
        "label": label,
        "count": count,
        "denominator": denominator,
        "percent": round(100 * count / denominator, 1) if denominator else None,
        "basis": basis,
        "source": source,
    }


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(44, bold=True)
FONT_SUBTITLE = load_font(24)
FONT_LABEL = load_font(25)
FONT_SMALL = load_font(20)
FONT_VALUE = load_font(24, bold=True)
FONT_NOTE = load_font(18)

COLORS = {
    "navy": "#123B5D",
    "blue": "#3274A1",
    "teal": "#3A8D8A",
    "orange": "#D9822B",
    "gold": "#E0AA3E",
    "pink": "#B85C7A",
    "ink": "#1F2933",
    "muted": "#667785",
    "grid": "#D9E2E8",
    "soft": "#F3F6F8",
    "white": "#FFFFFF",
}


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    width_chars: int,
    spacing: int = 5,
) -> int:
    wrapped = textwrap.fill(text, width=width_chars)
    draw.multiline_text(xy, wrapped, font=font, fill=fill, spacing=spacing)
    box = draw.multiline_textbbox(xy, wrapped, font=font, spacing=spacing)
    return box[3] - box[1]


def save_bar_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    footnote: str,
    width: int = 1750,
) -> None:
    row_height = 105
    top = 185
    bottom = 100
    height = top + row_height * len(rows) + bottom
    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    draw.text((70, 45), title, font=FONT_TITLE, fill=COLORS["ink"])
    draw.text((72, 108), subtitle, font=FONT_SUBTITLE, fill=COLORS["muted"])

    label_x = 72
    bar_x = 565
    bar_w = width - bar_x - 190
    for idx, row in enumerate(rows):
        y = top + idx * row_height
        label = str(row["label"])
        draw_wrapped(draw, (label_x, y + 3), label, FONT_LABEL, COLORS["ink"], 34)
        draw.rounded_rectangle(
            (bar_x, y + 9, bar_x + bar_w, y + 52),
            radius=10,
            fill=COLORS["soft"],
        )
        value = float(row["percent"])
        fill_w = max(2, int(bar_w * value / 100))
        draw.rounded_rectangle(
            (bar_x, y + 9, bar_x + fill_w, y + 52),
            radius=10,
            fill=str(row.get("color", COLORS["blue"])),
        )
        annotation = f'{int(row["count"])}/{int(row["denominator"])}  ({value:.1f}%)'
        draw.text(
            (bar_x + bar_w + 18, y + 13),
            annotation,
            font=FONT_VALUE,
            fill=COLORS["ink"],
        )
        if row.get("note"):
            draw.text(
                (bar_x, y + 63),
                str(row["note"]),
                font=FONT_SMALL,
                fill=COLORS["muted"],
            )

    draw.line(
        (70, height - 75, width - 70, height - 75),
        fill=COLORS["grid"],
        width=2,
    )
    draw_wrapped(
        draw,
        (72, height - 60),
        footnote,
        FONT_NOTE,
        COLORS["muted"],
        145,
    )
    image.save(path, format="PNG", optimize=True)


def save_grouped_bar_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    series: list[tuple[str, str, str]],
    footnote: str,
    width: int = 1700,
) -> None:
    row_height = 128
    top = 220
    bottom = 120
    height = top + row_height * len(rows) + bottom
    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    draw.text((70, 42), title, font=FONT_TITLE, fill=COLORS["ink"])
    draw.text((72, 106), subtitle, font=FONT_SUBTITLE, fill=COLORS["muted"])

    legend_x = 72
    for label, _, color in series:
        draw.rounded_rectangle(
            (legend_x, 155, legend_x + 28, 178), radius=5, fill=color
        )
        draw.text((legend_x + 39, 150), label, font=FONT_SMALL, fill=COLORS["ink"])
        legend_x += 275

    label_x = 72
    bar_x = 570
    bar_w = width - bar_x - 205
    for row_idx, row in enumerate(rows):
        y = top + row_idx * row_height
        draw_wrapped(
            draw, (label_x, y + 10), str(row["label"]), FONT_LABEL, COLORS["ink"], 34
        )
        for series_idx, (_, key, color) in enumerate(series):
            item = row.get(key)
            if not item:
                continue
            bar_y = y + 7 + series_idx * 49
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + bar_w, bar_y + 33),
                radius=8,
                fill=COLORS["soft"],
            )
            value = float(item["percent"])
            fill_w = max(2, int(bar_w * value / 100))
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + fill_w, bar_y + 33),
                radius=8,
                fill=color,
            )
            annotation = (
                f'{int(item["count"])}/{int(item["denominator"])} ({value:.1f}%)'
            )
            draw.text(
                (bar_x + bar_w + 15, bar_y + 2),
                annotation,
                font=FONT_SMALL,
                fill=COLORS["ink"],
            )

    draw.line(
        (70, height - 88, width - 70, height - 88),
        fill=COLORS["grid"],
        width=2,
    )
    draw_wrapped(
        draw,
        (72, height - 70),
        footnote,
        FONT_NOTE,
        COLORS["muted"],
        150,
    )
    image.save(path, format="PNG", optimize=True)


def save_journey_figure(path: Path) -> None:
    width, height = 1750, 480
    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    draw.text(
        (70, 42),
        "The research points to one connected care journey",
        font=FONT_TITLE,
        fill=COLORS["ink"],
    )
    draw.text(
        (72, 105),
        "The four planned skills cover the first half; the largest unmet needs begin after understanding.",
        font=FONT_SUBTITLE,
        fill=COLORS["muted"],
    )
    stages = [
        ("Prepare", "prep"),
        ("Ask", "prep"),
        ("Understand", "simplify + med-lit"),
        ("Act", "gap"),
        ("Track", "gap"),
        ("Share", "gap"),
        ("Follow up", "gap"),
    ]
    x0, y, box_w, gap = 70, 220, 205, 30
    for idx, (label, status) in enumerate(stages):
        x = x0 + idx * (box_w + gap)
        fill = COLORS["blue"] if status != "gap" else COLORS["orange"]
        draw.rounded_rectangle(
            (x, y, x + box_w, y + 115), radius=18, fill=fill
        )
        bbox = draw.textbbox((0, 0), label, font=FONT_LABEL)
        draw.text(
            (x + (box_w - (bbox[2] - bbox[0])) / 2, y + 25),
            label,
            font=FONT_LABEL,
            fill=COLORS["white"],
        )
        detail = status if status != "gap" else "Uncovered"
        bbox2 = draw.textbbox((0, 0), detail, font=FONT_SMALL)
        draw.text(
            (x + (box_w - (bbox2[2] - bbox2[0])) / 2, y + 68),
            detail,
            font=FONT_SMALL,
            fill=COLORS["white"],
        )
        if idx < len(stages) - 1:
            arrow_x = x + box_w + 7
            draw.line(
                (arrow_x, y + 57, arrow_x + gap - 13, y + 57),
                fill=COLORS["muted"],
                width=4,
            )
            draw.polygon(
                [
                    (arrow_x + gap - 13, y + 49),
                    (arrow_x + gap - 2, y + 57),
                    (arrow_x + gap - 13, y + 65),
                ],
                fill=COLORS["muted"],
            )
    draw.text(
        (72, 390),
        "Recommendation: connect the skills through a shared, consented longitudinal record rather than shipping four isolated utilities.",
        font=FONT_SMALL,
        fill=COLORS["ink"],
    )
    image.save(path, format="PNG", optimize=True)


def write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    pd.DataFrame(list(rows)).to_csv(path, index=False, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    data_dir = output_dir / "data"
    figures_dir = output_dir / "figures"
    data_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    patients_raw = pd.read_excel(source_dir / "patients.xlsx").dropna(how="all")
    clinicians = pd.read_excel(source_dir / "clinicians.xlsx").dropna(how="all")
    patient_interviews = pd.read_excel(
        source_dir / "patient_interviews.xlsx"
    ).dropna(how="all")
    patients_original = pd.read_excel(
        source_dir / "patient_survey_original.xlsx"
    ).dropna(how="all")
    clinicians_original = pd.read_excel(
        source_dir / "clinician_survey_original.xlsx"
    ).dropna(how="all")

    patient_answer_columns = [
        col for col in patients_raw.columns if not str(col).startswith("Timestamp")
    ]
    duplicate_patient_rows = int(
        patients_raw.duplicated(
            subset=patient_answer_columns, keep="first"
        ).sum()
    )
    patients = patients_raw.drop_duplicates(
        subset=patient_answer_columns, keep="first"
    ).copy()

    patient_platform = find_col(patients_raw, "Survey platform")
    patient_interview_rows_raw = patients_raw[
        patients_raw[patient_platform].map(normalize_text).eq("Interview")
    ].copy()
    patient_interview_rows = patients[
        patients[patient_platform].map(normalize_text).eq("Interview")
    ].copy()
    duplicate_subset = [
        col
        for col in patients_raw.columns
        if not str(col).startswith("Timestamp")
        and "email" not in str(col).lower()
        and "state" not in str(col).lower()
    ]
    duplicate_interview_rows = int(
        patient_interview_rows_raw.duplicated(
            subset=duplicate_subset, keep="first"
        ).sum()
    )
    patient_interview_unique_n = len(patient_interview_rows)
    qualitative_patient_n = 21
    qualitative_clinician_n = 19

    metrics: list[dict[str, object]] = []

    def add_contains(
        metric_id: str,
        category: str,
        label: str,
        prefix: str,
        pattern: str,
        basis: str,
    ) -> None:
        column = find_col(patients, prefix)
        count, denominator = count_contains(patients[column], pattern)
        metrics.append(
            metric_row(
                metric_id,
                "Patient survey",
                category,
                label,
                count,
                denominator,
                basis,
                f"{PATIENTS_URL} | Form Responses 1 | {column}",
            )
        )

    add_contains(
        "patient_question_gap",
        "Current skills",
        "Missed critical questions or were too overloaded to formulate them",
        "Were you able to ask",
        r"missed critical|too much information",
        "Explicit structured answer text; multi-label responses counted once.",
    )
    add_contains(
        "patient_not_full_understanding",
        "Current skills",
        "Reported only partial understanding or too little information",
        "Were you able to fully",
        r"understood some|very little information",
        "Counts the two standard non-full-understanding response options.",
    )
    add_contains(
        "patient_relied_on_memory",
        "Current skills",
        "Included memorization in their appointment information method",
        "How did you store",
        r"memorize",
        "Multi-select text; memorization may be combined with another method.",
    )
    add_contains(
        "patient_search_before",
        "Current skills",
        "Searched online before the appointment",
        "Did you Google Search / Chat GPT to better understand your condition BEFORE",
        r"searched for few|searched extensively|shed extensively",
        "Counts explicit standard search responses; custom search descriptions are excluded.",
    )
    add_contains(
        "patient_chronic_condition",
        "Context",
        "Reported a current or past chronic condition",
        "Do you have/had",
        r"^yes",
        "Current and past chronic conditions combined.",
    )
    add_contains(
        "patient_symptom_tracking_not_full",
        "Unmet needs",
        "Symptom tracking was only partly effective or ineffective",
        "Is the above method effective?",
        r"mostly keep track|cannot keep track",
        "Combines 'mostly' and 'cannot' responses; one custom response excluded.",
    )
    add_contains(
        "patient_family_verbal_relay",
        "Unmet needs",
        "Relayed visit information verbally from memory to family",
        "Have you every had to share",
        r"verbally explained",
        "Multi-select response; may also include notes or documents.",
    )
    add_contains(
        "patient_recording_socially_awkward",
        "Trust constraints",
        "Said asking to record feels socially awkward",
        "[IF NO]",
        r"socially awkward",
        "Multi-select/free-text recording barrier.",
    )
    add_contains(
        "patient_recording_not_known_option",
        "Trust constraints",
        "Did not think recording was an option",
        "[IF NO]",
        r"didn.?t think it was an option|not an option",
        "Multi-select/free-text recording barrier.",
    )
    add_contains(
        "patient_recording_long_audio",
        "Trust constraints",
        "Did not want to search through a long recording",
        "[IF NO]",
        r"long recordings",
        "Multi-select/free-text recording barrier.",
    )
    add_contains(
        "patient_recording_wants_transcript",
        "Trust constraints",
        "Wanted a transcript, not audio alone",
        "[IF NO]",
        r"transcript",
        "Multi-select/free-text recording barrier.",
    )
    add_contains(
        "patient_recording_privacy",
        "Trust constraints",
        "Raised privacy as a recording barrier",
        "[IF NO]",
        r"privacy",
        "Multi-select/free-text recording barrier.",
    )
    add_contains(
        "patient_search_after",
        "Unmet needs",
        "Searched online after the appointment",
        "Did you Google Search / Chat GPT to better understand your condition AFTER",
        r"searched for few|searched extensively",
        "Late survey-version field; denominator is much smaller than the full sample.",
    )
    add_contains(
        "patient_english_not_first",
        "Context",
        "Did not report English as a first language",
        "Is english your first language?",
        r"^no",
        "Late survey-version field; includes respondents who understand English well.",
    )
    add_contains(
        "caregiver_information_not_full",
        "Unmet needs",
        "Caregiver information capture was only partial or ineffective",
        "Is the above method effective? 2",
        r"keep track of most|cannot store",
        "Late survey-version field; combines 'most' and 'cannot' responses.",
    )
    add_contains(
        "patient_followup_contacted_clinician",
        "Unmet needs",
        "Reached out to the clinician again after the appointment",
        "Did you have any follow ups",
        r"reach out to the doctor again",
        "Counts the standard clinician-contact response; custom contact descriptions are excluded.",
    )
    add_contains(
        "patient_followup_saved_for_later",
        "Unmet needs",
        "Saved a post-visit question for the next appointment",
        "Did you have any follow ups",
        r"note it down for next appointment",
        "Counts the standard save-for-next-visit response; custom descriptions are excluded.",
    )
    add_contains(
        "patient_followup_searched_online",
        "Unmet needs",
        "Used Google or ChatGPT for a post-visit question",
        "Did you have any follow ups",
        r"google / chat gpt it",
        "Counts the standard online-search response; custom descriptions are excluded.",
    )
    symptom_method_col = find_col(
        patients, "Between two recurring appointments"
    )
    symptom_effectiveness_col = find_col(patients, "Is the above method effective?")
    explicit_tracking_failure = (
        patients[symptom_method_col]
        .fillna("")
        .astype(str)
        .str.contains(r"don.?t keep track", case=False, regex=True)
        | patients[symptom_effectiveness_col]
        .fillna("")
        .astype(str)
        .str.contains(r"cannot keep track", case=False, regex=True)
    )
    metrics.append(
        metric_row(
            "patient_explicit_tracking_failure",
            "Patient survey",
            "Unmet needs",
            "Explicitly did not keep track or could not keep track",
            int(explicit_tracking_failure.sum()),
            len(patients),
            "Conservative corpus count across two conditional symptom-tracking fields; "
            "the full-sample denominator is shown only to prevent double counting.",
            f"{PATIENTS_URL} | Form Responses 1 | {symptom_method_col} + "
            f"{symptom_effectiveness_col}",
        )
    )

    score_specs = [
        (
            "patient_forget_3_to_5",
            "Current skills",
            "Rated forgetting critical visit information 3–5 on a 5-point scale",
            "How often do you forget",
            lambda x: x >= 3,
        ),
        (
            "patient_worry_4_to_5",
            "Current skills",
            "Rated worry about missing visit information 4–5",
            "How much does missing",
            lambda x: x >= 4,
        ),
        (
            "patient_followup_4_to_5",
            "Unmet needs",
            "Rated need to follow up 4–5",
            "how often do you feel",
            lambda x: x >= 4,
        ),
        (
            "patient_app_interest_4_to_5",
            "Concept interest",
            "Rated the bundled record/transcript/question concept 4–5",
            "If an app helped",
            lambda x: x >= 4,
        ),
        (
            "patient_smartphone_4_to_5",
            "Context",
            "Rated smartphone comfort 4–5",
            "How comfortable are you with a smartphone",
            lambda x: x >= 4,
        ),
        (
            "patient_search_reliability_1_to_3",
            "Trust constraints",
            "Rated online search reliability only 1–3",
            "How reliable",
            lambda x: x <= 3,
        ),
    ]
    score_details: dict[str, dict[str, float]] = {}
    for metric_id, category, label, prefix, predicate in score_specs:
        column = find_col(patients, prefix)
        count, denominator, mean, median = score_count(patients[column], predicate)
        metrics.append(
            metric_row(
                metric_id,
                "Patient survey",
                category,
                label,
                count,
                denominator,
                "Threshold applied to numeric 1–5 responses; scale wording was not available in the export.",
                f"{PATIENTS_URL} | Form Responses 1 | {column}",
            )
        )
        score_details[metric_id] = {"mean": round(mean, 2), "median": median}

    clinician_barriers = [
        ("Missing medical history/documents", 6, 8),
        ("Limited or insufficient visit time", 4, 8),
        ("Patient too overwhelmed to ask questions", 3, 8),
        ("Language or communication barriers", 3, 8),
        ("Patient lateness", 1, 8),
        ("Need for translation in the summary", 1, 8),
    ]
    for idx, (label, count, denominator) in enumerate(clinician_barriers, start=1):
        metrics.append(
            metric_row(
                f"clinician_barrier_{idx}",
                "Clinician structured responses",
                "Appointment barriers",
                label,
                count,
                denominator,
                "Human-normalized multi-select/free-text coding; percentages do not sum to 100%.",
                f"{CLINICIANS_URL} | Form Responses 1 | barrier question",
            )
        )

    current_skill_counts = [
        {
            "skill": "Simplify",
            "patient_count": 15,
            "patient_denominator": qualitative_patient_n,
            "patient_basis": "Interviewees explicitly describing overload or recall failure.",
            "clinician_count": 18,
            "clinician_denominator": qualitative_clinician_n,
            "clinician_basis": "Clinicians explicitly describing need for concise visit information.",
        },
        {
            "skill": "Prep",
            "patient_count": 16,
            "patient_denominator": qualitative_patient_n,
            "patient_basis": "Interviewees mentioning preparation across questions, research, history, symptoms, or support.",
            "clinician_count": 14,
            "clinician_denominator": qualitative_clinician_n,
            "clinician_basis": "Clinicians explicitly describing pre-visit preparation needs.",
        },
        {
            "skill": "Question generation / prioritization",
            "patient_count": 15,
            "patient_denominator": qualitative_patient_n,
            "patient_basis": "Interviewees whose questions were missed or emerged after reflection.",
            "clinician_count": 6,
            "clinician_denominator": qualitative_clinician_n,
            "clinician_basis": "Clinicians explicitly asking for question support or prioritization.",
        },
        {
            "skill": "Medical-literacy identifier",
            "patient_count": 13,
            "patient_denominator": qualitative_patient_n,
            "patient_basis": "Interviewees describing difficulty with terminology, results, or instructions.",
            "clinician_count": 15,
            "clinician_denominator": qualitative_clinician_n,
            "clinician_basis": "Clinicians describing differences in literacy, cognition, language, stress, or desired depth.",
        },
    ]
    for row in current_skill_counts:
        row["patient_percent"] = round(
            100 * row["patient_count"] / row["patient_denominator"], 1
        )
        row["clinician_percent"] = round(
            100 * row["clinician_count"] / row["clinician_denominator"], 1
        )

    unmet_needs = [
        {
            "opportunity": "Permissioned care circle",
            "patient_count": 16,
            "patient_denominator": 21,
            "clinician_count": 12,
            "clinician_denominator": 19,
            "ask": "Granular, revocable sharing and caregiver participation before and after visits.",
        },
        {
            "opportunity": "Medication and action adherence",
            "patient_count": 8,
            "patient_denominator": 21,
            "clinician_count": 13,
            "clinician_denominator": 19,
            "ask": "Confirmed tasks, medication reconciliation, reminders, and between-visit check-ins.",
        },
        {
            "opportunity": "Portal and record aggregation",
            "patient_count": 12,
            "patient_denominator": 21,
            "clinician_count": 11,
            "clinician_denominator": 19,
            "ask": "Unify relevant notes, labs, images, device data, and follow-up questions.",
        },
        {
            "opportunity": "Privacy, consent, and recording governance",
            "patient_count": 12,
            "patient_denominator": 21,
            "clinician_count": 11,
            "clinician_denominator": 19,
            "ask": "Consent workflow, policy checks, audit trail, and control over downstream use.",
        },
        {
            "opportunity": "Accuracy and evidence provenance",
            "patient_count": 13,
            "patient_denominator": 21,
            "clinician_count": 9,
            "clinician_denominator": 19,
            "ask": "Citations, uncertainty cues, concise output, and clinician review where needed.",
        },
        {
            "opportunity": "Longitudinal symptom and decision timeline",
            "patient_count": 12,
            "patient_denominator": 21,
            "clinician_count": 11,
            "clinician_denominator": 19,
            "ask": "A single timeline for symptoms, photos, decisions, tasks, and unresolved questions.",
        },
    ]
    for row in unmet_needs:
        row["patient_percent"] = round(
            100 * row["patient_count"] / row["patient_denominator"], 1
        )
        row["clinician_percent"] = round(
            100 * row["clinician_count"] / row["clinician_denominator"], 1
        )

    evidence_ledger = [
        {
            "audience": "Patient interview",
            "theme": "Simplify",
            "source_ref": "Patients index 153 / sheet row 155",
            "excerpt": "I kind of go dumb when they start talking.",
            "supports": "Stress and overload reduce in-visit comprehension and recall.",
        },
        {
            "audience": "Patient interview",
            "theme": "Simplify",
            "source_ref": "Patients index 164 / sheet row 166",
            "excerpt": "It is hard to search things.",
            "supports": "Users need searchable key points rather than another long record.",
        },
        {
            "audience": "Patient interview",
            "theme": "Question prioritization",
            "source_ref": "Patients index 41 / sheet row 43",
            "excerpt": "Sometimes I can't think of the questions at the time.",
            "supports": "Questions often emerge after the appointment.",
        },
        {
            "audience": "Patient interview",
            "theme": "Prep",
            "source_ref": "Patients index 155 / sheet row 157",
            "excerpt": "What to expect beforehand, what to ask.",
            "supports": "Patients already seek preparation and question prompts.",
        },
        {
            "audience": "Patient interview",
            "theme": "Medical literacy",
            "source_ref": "Patients index 148 / sheet row 150",
            "excerpt": "Understanding results, what they mean.",
            "supports": "Test results and borderline values create interpretation needs.",
        },
        {
            "audience": "Patient interview",
            "theme": "Evidence provenance",
            "source_ref": "Patients index 61 / sheet row 63",
            "excerpt": "Show me the citations from research.",
            "supports": "Some users need transparent sources, not unsupported AI answers.",
        },
        {
            "audience": "Patient interview",
            "theme": "Longitudinal continuity",
            "source_ref": "Patients index 159 / sheet row 161",
            "excerpt": "Documentation between visits.",
            "supports": "Users want continuity across appointments, not isolated summaries.",
        },
        {
            "audience": "Patient interview",
            "theme": "Care circle",
            "source_ref": "Patients index 148 / sheet row 150",
            "excerpt": "My family will have follow-up questions.",
            "supports": "Visit information must often be relayed to absent family.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Question prioritization",
            "source_ref": "Clinicians sheet row 5",
            "excerpt": "What are your top three questions?",
            "supports": "Question support should prioritize a short agenda.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Prep",
            "source_ref": "Clinicians sheet row 2",
            "excerpt": "Written medication list, questions and concerns, recent vital signs.",
            "supports": "Preparation needs concrete documents and data.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Medical literacy",
            "source_ref": "Clinicians sheet row 2",
            "excerpt": "Depends on education level, medical literacy, anxiety, cognitive status.",
            "supports": "Communication needs are multi-dimensional and encounter-specific.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Clinician control",
            "source_ref": "Clinicians sheet row 5",
            "excerpt": "It would have to be a must that we see the summary.",
            "supports": "Some settings require review before patient release.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Accuracy and workload",
            "source_ref": "Clinicians sheet row 4",
            "excerpt": "For me to write three lines is faster than reviewing four lines for errors.",
            "supports": "Review burden can erase the product's workflow value.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Care circle",
            "source_ref": "Clinicians sheet row 6",
            "excerpt": "Presence or engagement of a care partner is instrumental.",
            "supports": "Care partners are a core communication support for high-need patients.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Interoperability",
            "source_ref": "Clinicians sheet row 4",
            "excerpt": "A thousand pages, but only two usable ones.",
            "supports": "The problem is relevant-record selection, not merely record collection.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Action and adherence",
            "source_ref": "Clinicians sheet rows 15–16",
            "excerpt": "Maybe they remember but do not execute the plan.",
            "supports": "Understanding alone does not ensure follow-through.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Prep",
            "source_ref": "Patients sheet row 54",
            "excerpt": "I write everything down ahead of time to remember it.",
            "supports": "Patients already create their own preparation scaffolding.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Medical literacy",
            "source_ref": "Patients sheet row 91",
            "excerpt": "I forgot all the technical terms.",
            "supports": "Terminology is a comprehension and recall barrier.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Question prioritization",
            "source_ref": "Patients sheet row 150",
            "excerpt": "I go in with a list of questions, but often forget while listening.",
            "supports": "A prepared list still needs in-visit prioritization support.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Cognitive load",
            "source_ref": "Patients sheet row 166",
            "excerpt": "I often feel overwhelmed with the amount of information shared.",
            "supports": "Explanation needs change with encounter load.",
        },
        {
            "audience": "Long-form patient/caregiver interview",
            "theme": "Care circle",
            "source_ref": "Long-form interview sheet row 2",
            "excerpt": "I feel better knowing someone else is there to absorb information.",
            "supports": "A care partner provides both recall support and reassurance.",
        },
        {
            "audience": "Long-form patient/caregiver interview",
            "theme": "Record fragmentation",
            "source_ref": "Long-form interview sheet row 3",
            "excerpt": "Multiple apps and portals have my medical data.",
            "supports": "Records are fragmented across systems and formats.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Symptom tracking",
            "source_ref": "Patients sheet row 162",
            "excerpt": "It would be better to keep a more detailed list of symptoms.",
            "supports": "Users want dated, event-level symptom history.",
        },
        {
            "audience": "Patient survey/interview",
            "theme": "Accessibility",
            "source_ref": "Patients sheet row 163",
            "excerpt": "Cannot keep track of it due to executive dysfunction.",
            "supports": "Tracking must reduce executive-function demands.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Medication reconciliation",
            "source_ref": "Clinicians sheet rows 19 and 21 duplicate pair",
            "excerpt": "What are you taking, and why are you taking it?",
            "supports": "Medication lists need purpose and reconciliation, not names alone.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Interoperability",
            "source_ref": "Clinicians sheet row 6",
            "excerpt": "The report is only a statement; we need to see the image.",
            "supports": "Some decisions require original clinical artifacts.",
        },
        {
            "audience": "Clinician interview",
            "theme": "Grounded research",
            "source_ref": "Clinicians sheet rows 2 and 10",
            "excerpt": "AI can be over-inclusive and has to be succinct.",
            "supports": "Research support must filter for relevance and currency.",
        },
    ]

    source_inventory = [
        {
            "source": "Patients",
            "role": "Controlling patient survey/interview dataset",
            "raw_rows": len(patients_raw),
            "analysis_population": len(patients),
            "notes": (
                "Contains 22 Interview-tagged rows; one duplicate response after "
                "excluding timestamp/contact fields, yielding 21 coded interview units."
            ),
            "url": PATIENTS_URL,
        },
        {
            "source": "Medical Information Recording - User Interview (Responses)",
            "role": "Separate long-form patient interview form",
            "raw_rows": len(patient_interviews),
            "analysis_population": len(patient_interviews),
            "notes": (
                "Four additional interview records with no timestamp overlap with Patients. "
                "Cross-form participant deduplication was not attempted to avoid using PII."
            ),
            "url": PATIENT_INTERVIEWS_URL,
        },
        {
            "source": "Clinicians and Doctors",
            "role": "Controlling clinician survey/interview dataset",
            "raw_rows": len(clinicians),
            "analysis_population": qualitative_clinician_n,
            "notes": (
                "Twenty-one raw rows; human review combined one continuation and one duplicate "
                "pair, yielding 19 qualitative clinician units. Structured denominators remain "
                "question-specific and sparse."
            ),
            "url": CLINICIANS_URL,
        },
    ]

    data_quality = [
        {
            "issue": "Accessible sample differs from recalled fieldwork totals",
            "evidence": (
                f"{len(patients_raw)} patient rows ({len(patients)} unique submissions), "
                f"{len(patient_interviews)} separate patient interview rows, and "
                f"{len(clinicians)} clinician rows were accessible."
            ),
            "impact": (
                "The report describes the connected corpus, not the larger recalled total of "
                "200–300 surveys, 50 user interviews, and 30–50 clinicians."
            ),
        },
        {
            "issue": "Survey instrument changed over time",
            "evidence": "Several later columns have only 53–59 responses; early fields have 119–165.",
            "impact": "Every percentage uses its own non-null denominator.",
        },
        {
            "issue": "Clinician structured fields are sparse",
            "evidence": "Most structured clinician questions have only 1–8 answers.",
            "impact": "Clinician percentages are descriptive of field respondents only.",
        },
        {
            "issue": "Qualitative sampling is purposive",
            "evidence": "Most patient records came through Reddit; interviewees have high chronic-care exposure.",
            "impact": "Theme counts show frequency in this corpus, not population prevalence.",
        },
        {
            "issue": "Bundled concept question",
            "evidence": "The interest question combines recording, transcript, and tailored questions.",
            "impact": "It cannot isolate demand for one feature.",
        },
        {
            "issue": "PII and credentials present in source files",
            "evidence": "Contact fields and a separate operational tracker contain sensitive information.",
            "impact": "Raw exports are excluded; only de-identified aggregates and excerpts are written.",
        },
    ]

    write_csv(data_dir / "metrics.csv", metrics)
    write_csv(data_dir / "current_skill_support.csv", current_skill_counts)
    write_csv(data_dir / "unmet_needs.csv", unmet_needs)
    write_csv(data_dir / "evidence_ledger.csv", evidence_ledger)
    write_csv(data_dir / "source_inventory.csv", source_inventory)
    write_csv(data_dir / "data_quality.csv", data_quality)

    metrics_by_id = {row["metric_id"]: row for row in metrics}
    snapshot = {
        "generated_from": {
            "patients": PATIENTS_URL,
            "clinicians": CLINICIANS_URL,
            "patient_interviews": PATIENT_INTERVIEWS_URL,
        },
        "source_checks": {
            "patient_duplicate_export_content_equal": bool(
                patients_raw.equals(patients_original)
            ),
            "clinician_duplicate_export_content_equal": bool(
                clinicians.equals(clinicians_original)
            ),
            "patient_raw_rows": len(patients_raw),
            "patient_duplicate_rows": duplicate_patient_rows,
            "patient_unique_submissions": len(patients),
            "patient_interview_tagged_rows": len(patient_interview_rows_raw),
            "patient_interview_duplicate_rows": duplicate_interview_rows,
            "patient_interview_unique_units": patient_interview_unique_n,
            "separate_patient_interview_rows": len(patient_interviews),
            "clinician_raw_rows": len(clinicians),
            "clinician_qualitative_units": qualitative_clinician_n,
        },
        "score_details": score_details,
        "metrics": metrics,
        "current_skill_support": current_skill_counts,
        "unmet_needs": unmet_needs,
        "evidence_ledger": evidence_ledger,
        "data_quality": data_quality,
    }
    (data_dir / "analysis_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    skill_rows = []
    for row in current_skill_counts:
        skill_rows.append(
            {
                "label": row["skill"],
                "patient": {
                    "count": row["patient_count"],
                    "denominator": row["patient_denominator"],
                    "percent": row["patient_percent"],
                },
                "clinician": {
                    "count": row["clinician_count"],
                    "denominator": row["clinician_denominator"],
                    "percent": row["clinician_percent"],
                },
            }
        )
    save_grouped_bar_chart(
        figures_dir / "01_current_skill_support.png",
        "Interview evidence supports all four planned skills",
        "Unique coded interview units; each participant can support multiple themes",
        skill_rows,
        [
            ("Patient interviews", "patient", COLORS["blue"]),
            ("Clinician interviews", "clinician", COLORS["orange"]),
        ],
        "Counts are thematic frequencies in purposive interviews, not population estimates. "
        "Question generation has broad patient support but narrower explicit clinician support; "
        "clinicians consistently asked for prioritization rather than more questions.",
    )

    patient_signal_ids = [
        "patient_question_gap",
        "patient_not_full_understanding",
        "patient_forget_3_to_5",
        "patient_worry_4_to_5",
        "patient_symptom_tracking_not_full",
        "patient_family_verbal_relay",
        "patient_app_interest_4_to_5",
    ]
    patient_signal_rows = []
    for idx, metric_id in enumerate(patient_signal_ids):
        row = metrics_by_id[metric_id]
        patient_signal_rows.append(
            {
                "label": row["label"],
                "count": row["count"],
                "denominator": row["denominator"],
                "percent": row["percent"],
                "color": [COLORS["blue"], COLORS["teal"], COLORS["orange"]][idx % 3],
            }
        )
    save_bar_chart(
        figures_dir / "02_patient_problem_signals.png",
        "Patients report gaps in questions, understanding, recall, and follow-through",
        "Question-specific denominators are shown because the survey changed during collection",
        patient_signal_rows,
        "The app-interest item bundles recording, transcript, and tailored questions, so it "
        "validates the combined concept but cannot attribute demand to one feature.",
    )

    barrier_rows = [
        {
            "label": label,
            "count": count,
            "denominator": denominator,
            "percent": round(100 * count / denominator, 1),
            "color": COLORS["orange"],
        }
        for label, count, denominator in clinician_barriers
    ]
    save_bar_chart(
        figures_dir / "03_clinician_appointment_barriers.png",
        "Clinician barriers: missing records, limited time, overload, and language",
        "Eight clinicians populated the multi-select barrier field",
        barrier_rows,
        "Percentages do not sum to 100%. The structured clinician sample is sparse; use these "
        "values as directional corroboration of the interview themes.",
    )

    unmet_rows = []
    for row in unmet_needs:
        unmet_rows.append(
            {
                "label": row["opportunity"],
                "patient": {
                    "count": row["patient_count"],
                    "denominator": row["patient_denominator"],
                    "percent": row["patient_percent"],
                },
                "clinician": {
                    "count": row["clinician_count"],
                    "denominator": row["clinician_denominator"],
                    "percent": row["clinician_percent"],
                },
            }
        )
    save_grouped_bar_chart(
        figures_dir / "04_unmet_needs.png",
        "The largest uncovered opportunities concern continuity, trust, and shared care",
        "Unique coded interview units mentioning each need",
        unmet_rows,
        [
            ("Patient interviews", "patient", COLORS["teal"]),
            ("Clinician interviews", "clinician", COLORS["orange"]),
        ],
        "These themes sit outside the core output of simplify, prep, question prioritization, "
        "and medical-literacy identification, although several should become shared platform "
        "requirements across those skills.",
    )
    save_journey_figure(figures_dir / "05_connected_care_journey.png")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "metrics": len(metrics),
                "figures": 5,
                "patient_raw_rows": len(patients_raw),
                "patient_unique_submissions": len(patients),
                "patient_interview_units": patient_interview_unique_n,
                "clinician_rows": len(clinicians),
                "clinician_qualitative_units": qualitative_clinician_n,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
