"""Kill test 1, fixes #3, #4, #5: text-content regression guards for the
LLM-facing instruction documents that changed. These stages have no
deterministic code to exercise, so (mirroring test_skill_consistency.py's
approach of parsing text rather than running it) these tests assert the
required language actually landed in the file and stays there.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
SKILL_MD_PATH = os.path.join(REPO_ROOT, "skills", "simplify", "SKILL.md")
STAGES_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "stages")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestReviewFidelityNumeracyCarveout(unittest.TestCase):
    """Fix #3: a dropped unit / mismatched number is a FIDELITY error, not
    style, and a numeric_parity hint must be resolved, not waved off."""

    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "review_fidelity.md"))

    def test_scope_paragraph_carves_out_numeracy(self):
        self.assertIn("FIDELITY error", self.text)
        self.assertIn("NUMERACY rule", self.text)
        # The concrete dropped-unit example from the kill test.
        self.assertIn("148/92", self.text)

    def test_correction_value_is_the_facts_own_wording(self):
        self.assertIn("value is the fact's own wording", self.text)

    def test_numeric_parity_hint_guidance_requires_resolution(self):
        hints_section = self.text.split("## Hints from deterministic checks", 1)[1]
        self.assertIn("usually", hints_section)
        self.assertIn("NUMERACY", hints_section)
        self.assertIn("25mg", hints_section)
        self.assertIn("25 mg", hints_section)


class TestAssembleNoNestedPhrasing(unittest.TestCase):
    """Fix #4: title/plain_name must never nest or duplicate the same
    phrase; say a thing once per item."""

    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "assemble.md"))

    def test_title_plain_name_rule_present(self):
        self.assertIn("plain_name", self.text)
        self.assertIn(
            "the everyday name ONLY when it differs from `title`",
            self.text,
        )

    def test_bad_and_good_examples_present(self):
        self.assertIn("high blood pressure (high blood pressure (hypertension))", self.text)
        self.assertIn("hypertension", self.text)

    def test_say_once_rule_present(self):
        self.assertIn("Say a thing once per item", self.text)


class TestNotStatedIsAStatedReason(unittest.TestCase):
    """Kill test 2 fix: `why` must be the clinician's stated reason for this
    patient, never the item's usual purpose/class or a timing instruction,
    and never mined from a fact that says the reason isn't documented."""

    def test_assemble_md_has_stated_reason_and_ondansetron(self):
        text = _read(os.path.join(STAGES_DIR, "assemble.md"))
        self.assertIn("stated reason", text)
        self.assertIn("ondansetron", text.lower())

    def test_assemble_missing_md_has_stated_reason_and_ondansetron(self):
        text = _read(os.path.join(STAGES_DIR, "assemble_missing.md"))
        self.assertIn("stated reason", text)
        self.assertIn("ondansetron", text.lower())

    def test_review_fidelity_md_has_general_indication(self):
        text = _read(os.path.join(STAGES_DIR, "review_fidelity.md"))
        self.assertIn("general indication", text)


if __name__ == "__main__":
    unittest.main()
