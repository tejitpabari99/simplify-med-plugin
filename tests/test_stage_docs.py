"""Regression guards for the model-facing Simplify stage contracts."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
REFERENCE_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "reference")
STAGES_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "stages")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


class TestThreeStageContract(unittest.TestCase):
    def test_only_new_core_stage_documents_remain(self):
        for filename in ("ground.md", "assemble.md", "review.md"):
            self.assertTrue(os.path.isfile(os.path.join(STAGES_DIR, filename)))

        for filename in (
            "review_fidelity.md",
            "review_coverage.md",
            "correct.md",
            "assemble_missing.md",
        ):
            self.assertFalse(os.path.exists(os.path.join(STAGES_DIR, filename)))

    def test_active_documents_do_not_reference_deleted_stages(self):
        active_paths = [
            os.path.join(REFERENCE_DIR, "style_rules.md"),
            os.path.join(STAGES_DIR, "ground.md"),
            os.path.join(STAGES_DIR, "assemble.md"),
            os.path.join(STAGES_DIR, "review.md"),
            os.path.join(STAGES_DIR, "glossary.md"),
        ]
        deleted_names = (
            "review_fidelity",
            "review_coverage",
            "assemble_missing",
            "04_coverage",
            "05_additions",
            "05_plan.corrected",
        )
        combined = "\n".join(_read(path) for path in active_paths)
        for deleted_name in deleted_names:
            self.assertNotIn(deleted_name, combined)


class TestCanonicalPatientRelevance(unittest.TestCase):
    def setUp(self):
        self.style = _read(os.path.join(REFERENCE_DIR, "style_rules.md"))
        self.assemble = _read(os.path.join(STAGES_DIR, "assemble.md"))
        self.review = _read(os.path.join(STAGES_DIR, "review.md"))

    def test_style_rules_make_critical_vs_supporting_canonical(self):
        self.assertIn("CRITICAL VS SUPPORTING", self.style)
        self.assertIn("The goal is not to display every extracted fact", self.style)
        self.assertIn("generic education", self.style)
        self.assertIn("not patient-specific", self.style)
        self.assertIn("contrast names or doses", self.style)
        self.assertIn("medication starts, stops, changes", self.style)
        self.assertIn("explicit warning signs", self.style)

    def test_assemble_and_review_apply_the_same_relevance_policy(self):
        for text in (self.assemble, self.review):
            self.assertIn("CRITICAL VS SUPPORTING", text)
            self.assertIn("Concision is a requirement", text)
            self.assertIn("generic_not_patient_specific", text)
            self.assertIn("patient-specific", text)


class TestGroundCompleteClauses(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "ground.md"))

    def test_quotes_must_preserve_the_complete_clinical_clause(self):
        self.assertIn("complete clinical clause", self.text)
        for detail in (
            "negation",
            "uncertainty",
            "condition",
            "dose",
            "unit",
            "frequency",
            "timing",
            "body site",
            "status",
        ):
            self.assertIn(detail, self.text)
        self.assertIn("tiny matching fragment", self.text)

    def test_grounding_stays_exhaustive_and_source_anchored(self):
        self.assertIn("Extract every fact", self.text)
        self.assertIn("literal, contiguous span", self.text)
        self.assertIn("Do not summarize the document", self.text)


class TestAssembleContract(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "assemble.md"))

    def test_uses_structured_fact_ledger_and_forbids_direct_summary(self):
        self.assertIn("02_facts.json", self.text)
        self.assertNotIn("02_facts.txt", self.text)
        self.assertIn("Do not directly summarize", self.text)
        self.assertIn("03_plan.raw.json", self.text)

    def test_every_fact_is_visible_or_has_one_structured_disposition(self):
        self.assertIn("Every verified fact", self.text)
        self.assertIn("exactly one", self.text)
        self.assertIn("omitted_facts", self.text)
        for reason in (
            "duplicate_or_already_represented",
            "technical_detail",
            "routine_non_actionable",
            "rejected_non_actionable_differential",
            "generic_not_patient_specific",
            "stable_unchanged_background",
        ):
            self.assertIn(reason, self.text)
        self.assertIn("must not also appear in `omitted_facts`", self.text)

    def test_questions_are_optional_cited_objects(self):
        self.assertIn("source_fact_ids", self.text)
        self.assertIn('"question": "Do I need another heart tracing?"', self.text)
        self.assertIn("Write none when", self.text)

    def test_existing_plain_language_safeguards_remain(self):
        self.assertIn("the everyday name ONLY when it differs from `title`", self.text)
        self.assertIn("Say a thing once per item", self.text)
        self.assertIn("ondansetron", self.text.lower())
        self.assertIn("two or three short sentences", self.text)


class TestCombinedReviewContract(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "review.md"))

    def test_review_is_independent_and_exhaustive(self):
        self.assertIn("independent", self.text.lower())
        self.assertIn("02_facts.json", self.text)
        self.assertIn("03_plan.draft.json", self.text)
        self.assertIn("03_flags.json", self.text)
        self.assertIn("one `fact_reviews` entry for every verified fact", self.text)
        self.assertIn("reviewed_fact_ids", self.text)
        self.assertIn("reassemble_fact_ids", self.text)

    def test_review_combines_fidelity_coverage_and_numeric_resolution(self):
        for field in (
            "fact_reviews",
            "corrections",
            "numeric_resolutions",
            "reassemble_fact_ids",
        ):
            self.assertIn(field, self.text)
        self.assertIn("negation", self.text)
        self.assertIn("uncertainty", self.text)
        self.assertIn("urgency", self.text)
        self.assertIn("general indication", self.text)
        self.assertIn("148/92", self.text)
        self.assertIn("25mg", self.text)
        self.assertIn("25 mg", self.text)

    def test_review_emits_only_bounded_operations(self):
        self.assertIn("bounded operations", self.text)
        self.assertIn('`"replace"`', self.text)
        self.assertIn('`"clear"`', self.text)
        self.assertIn('`"remove"`', self.text)
        self.assertIn("value is the fact's own wording", self.text)
        self.assertIn("Do not apply the operations", self.text)
        self.assertIn("Do not produce a corrected plan", self.text)

    def test_reassembly_requires_a_fresh_review(self):
        self.assertIn("smallest patient-facing change", self.text)
        self.assertIn("fresh independent review", self.text)
        self.assertIn("New patient-facing prose must never bypass review", self.text)


class TestOptionalGlossary(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "glossary.md"))

    def test_glossary_is_optional_post_finalization_enrichment(self):
        self.assertIn("optional post-finalization", self.text)
        self.assertIn("06_plan.final.json", self.text)
        self.assertIn("report.md", self.text)
        self.assertIn("patient-visible finalized content", self.text)
        self.assertIn("07_glossary.raw.json", self.text)
        self.assertIn("07_glossary.json", self.text)
        self.assertIn("no more than five terms", self.text)
        self.assertIn("must not change", self.text)


if __name__ == "__main__":
    unittest.main()
