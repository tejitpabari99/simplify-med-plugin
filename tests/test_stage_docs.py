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
AGENTS_DIR = os.path.join(REPO_ROOT, "agents")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestSkillMdAgentLocation(unittest.TestCase):
    """Fix #1: agents/ lives at <plugin>/agents/, a sibling of skills/, not
    under <skill>. SKILL.md must say so and never imply <skill>/agents/."""

    def setUp(self):
        self.text = _read(SKILL_MD_PATH)

    def test_plugin_agents_path_documented(self):
        self.assertIn("<plugin>/agents/<stage>.md", self.text)
        self.assertIn("parent directory of `skills/`", self.text)

    def test_no_path_implies_skill_slash_agents(self):
        self.assertNotIn("<skill>/agents/", self.text)

    def test_unitize_status_line_exception_documented(self):
        self.assertIn("second-to-last stdout line", self.text)


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


class TestAgentsSingleLineReply(unittest.TestCase):
    """Fix #5: every agent file's reply instruction is strengthened to the
    exact one-line contract, and tools stay Read, Write."""

    EXPECTED_REPLY_LINE = (
        "Your entire reply is exactly one line: "
        "`<output path> — <N> items written`. No preamble, no summary."
    )

    def test_every_agent_has_the_strengthened_reply_instruction(self):
        agent_files = sorted(
            name for name in os.listdir(AGENTS_DIR) if name.endswith(".md")
        )
        self.assertTrue(agent_files, "no agent files found under agents/")
        for name in agent_files:
            path = os.path.join(AGENTS_DIR, name)
            text = _read(path)
            self.assertIn(self.EXPECTED_REPLY_LINE, text, f"{path} missing the strengthened reply line")
            self.assertIn("tools: Read, Write", text, path)


if __name__ == "__main__":
    unittest.main()
