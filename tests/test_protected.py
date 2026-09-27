"""Tests for scripts/protected.py and the 01_protected.json it feeds."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import protected  # noqa: E402
import unitize  # noqa: E402
import validate  # noqa: E402

ER_VISIT = os.path.join(_paths.FIXTURE_DOCUMENTS_DIR, "synthetic-er-visit.txt")


def _units(*texts: str) -> list[dict]:
    return [{"id": index, "text": text} for index, text in enumerate(texts, start=1)]


class TestCategories(unittest.TestCase):
    def test_categories_match_schema_order(self):
        schema = validate.load_schema("protected")
        self.assertEqual(
            list(protected.CATEGORIES),
            schema["properties"]["categories"]["required"],
        )

    def assertCandidate(self, category: str, text: str) -> None:
        self.assertIn(category, protected.categories_for(text), text)

    def assertNotCandidate(self, category: str, text: str) -> None:
        self.assertNotIn(category, protected.categories_for(text), text)

    def test_medication_changes(self):
        for text in (
            "No new medications prescribed.",
            "Prescription sent for amoxicillin.",
            "Start metoprolol for rate control.",
            "Stopped spironolactone due to kidney injury.",
            "Discontinue aspirin.",
            "Hold lisinopril until seen.",
            "Resume home medications.",
            "Increase furosemide dose.",
            "New medication: apixaban.",
            "Ibuprofen 400 mg by mouth every 6 hours as needed.",
            "Metformin 500mg PO BID",
        ):
            self.assertCandidate("medication_changes", text)
        for text in (
            "Technique: Iopamidol 76% injection 80 mL IV.",  # dose without frequency/oral route
            "Patient reports taking no daily medications.",  # frequency without dose
            "Current Outpatient Medications: none on file.",
            "Household contacts are well.",
        ):
            self.assertNotCandidate("medication_changes", text)

    def test_follow_up(self):
        for text in (
            "Follow-up: see your primary care provider.",
            "Follow up with neurology.",
            "Followup in clinic.",
            "f/u with cardiology in 2 weeks",
            "Schedule an appointment as soon as possible.",
            "Referral placed to dermatology.",
            "See your doctor within 3 days.",
            "Return to clinic in four weeks.",
            "Recheck labs at the next visit.",
        ):
            self.assertCandidate("follow_up", text)
        for text in ("Patient follows commands.", "Headache for 3 days."):
            self.assertNotCandidate("follow_up", text)

    def test_return_precautions(self):
        for text in (
            "Return to the emergency department for any new or worsening symptoms.",
            "Return to the ER if pain worsens.",
            "Come back if you have a fever.",
            "Seek immediate medical attention for chest pain.",
            "Call 911 for trouble breathing.",
            "Go to the nearest emergency room.",
            "Return precautions discussed.",
            "Call the office if blood pressure exceeds 160/100.",
            "WARNING SIGNS",
        ):
            self.assertCandidate("return_precautions", text)
        for text in ("Worsening headache over three days.", "Returned from travel last week."):
            self.assertNotCandidate("return_precautions", text)

    def test_diagnoses(self):
        for text in (
            "Clinical Impression: Acute headache.",
            "IMPRESSION: Normal brain MRI.",
            "Assessment and Plan",
            "Discharge diagnosis: pneumonia",
            "Final Dx: migraine",
            "Dx: sprain",
        ):
            self.assertCandidate("diagnoses", text)
        self.assertNotCandidate("diagnoses", "Neuro: speech normal.")

    def test_disposition(self):
        for text in (
            "Disposition: Discharged home in stable condition.",
            "Admitted to medicine.",
            "Transfer to a tertiary center.",
            "Patient left in good condition.",
        ):
            self.assertCandidate("disposition", text)
        self.assertNotCandidate("disposition", "Lungs clear to auscultation.")

    def test_abnormal_or_pending_results(self):
        for text in (
            "Glucose 115 (H), BUN 12",
            "Potassium 3.1 (L)",
            "Troponin (HH) critical",
            "Blood cultures pending.",
            "Awaiting pathology.",
            "Abnormal ECG",
            "Creatinine mildly elevated.",
            "Strep test positive.",
            "Result flagged by lab.",
            "Culture not yet resulted.",
        ):
            self.assertCandidate("abnormal_or_pending_results", text)
        for text in ("Sodium 142, Potassium 3.7", "Hemoglobin 14.5 (ref 13-17)"):
            self.assertNotCandidate("abnormal_or_pending_results", text)


class TestScan(unittest.TestCase):
    def test_every_category_present_sorted_unique(self):
        result = protected.scan(_units(
            "Disposition: admitted.",
            "Plain text.",
            "Discharged home.",
        ))
        self.assertEqual(list(result), list(protected.CATEGORIES))
        self.assertEqual(result["disposition"], [1, 3])
        self.assertEqual(result["follow_up"], [])

    def test_skipped_units_are_ignored(self):
        units = _units("Follow-up with PCP.", "Follow-up with PCP.")
        units[1]["skip"] = "repeat"
        self.assertEqual(protected.scan(units)["follow_up"], [1])

    def test_unit_may_be_candidate_in_several_categories(self):
        result = protected.scan(_units("Follow-up: schedule a visit about the abnormal ECG."))
        self.assertEqual(result["follow_up"], [1])
        self.assertEqual(result["abnormal_or_pending_results"], [1])
        self.assertEqual(protected.candidate_ids(result), {1})


class TestErFixture(unittest.TestCase):
    """unitize + protected scan on the synthetic ER visit."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        run_dir = os.path.join(cls._tmp.name, "run")
        with redirect_stdout(StringIO()):
            rc = unitize.main(["--run-dir", run_dir, "--input", ER_VISIT])
        assert rc == 0, rc
        with open(os.path.join(run_dir, "01_units.json"), encoding="utf-8") as f:
            cls.units = json.load(f)["units"]
        with open(os.path.join(run_dir, "01_protected.json"), encoding="utf-8") as f:
            cls.protected_doc = json.load(f)
        cls.categories = cls.protected_doc["categories"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _id(self, text_start: str) -> int:
        matches = [u["id"] for u in self.units if u["text"].startswith(text_start) and not u.get("skip")]
        self.assertEqual(len(matches), 1, text_start)
        return matches[0]

    def test_protected_doc_validates(self):
        self.assertEqual(validate.validate(self.protected_doc, validate.load_schema("protected")), [])

    def test_portal_boilerplate_is_skipped(self):
        skips = {}
        for unit in self.units:
            skips.setdefault(unit["text"], []).append(unit.get("skip"))
        self.assertEqual(skips["Patient Portal - Visit Summary"], [None, "repeat", "repeat"])
        self.assertEqual(skips["https://portal.example-health.test/visits/000000"], ["url"] * 3)
        for page in (1, 2, 3):
            self.assertEqual(skips[f"Page {page} of 3"], ["page_counter"])
        self.assertEqual(
            skips["Please discuss imaging findings and recommendations with the ordering provider."],
            [None, "repeat"],
        )
        # The synthetic-document comment line is an ordinary unit.
        self.assertEqual(self.units[0]["id"], 1)
        self.assertNotIn("skip", self.units[0])

    def test_skipped_units_are_never_candidates(self):
        skipped = {u["id"] for u in self.units if u.get("skip")}
        self.assertTrue(skipped)
        self.assertFalse(skipped & protected.candidate_ids(self.categories))

    def test_expected_candidates(self):
        expected = {
            "follow_up": "Follow-up: Schedule an appointment",
            "return_precautions": "Return to the emergency department",
            "disposition": "Disposition: Discharged home in stable condition.",
            "diagnoses": "Clinical Impression: Acute headache.",
            # A "none prescribed" statement is a medication candidate so the
            # writer shows it (medicines.none_statement) or the verifier dismisses it.
            "medication_changes": "No new medications prescribed.",
            "abnormal_or_pending_results": "Sodium 142, Potassium 3.7, Chloride 101, Glucose 115 (H)",
        }
        for category, text_start in expected.items():
            with self.subTest(category=category):
                self.assertIn(self._id(text_start), self.categories[category])

    def test_noise_is_not_a_medication_candidate(self):
        self.assertNotIn(self._id("Technique: Iopamidol"), self.categories["medication_changes"])
        self.assertNotIn(self._id("Current Outpatient Medications:"), self.categories["medication_changes"])


if __name__ == "__main__":
    unittest.main()
