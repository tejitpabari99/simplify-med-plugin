"""Hard boundaries shared by every skill: no medical images, no outside sources.

Contract C3: the `## Hard Boundaries` block is byte-identical in the three
SKILL.md files, keeps rule 1 unchanged, and has rule 2 exactly as PRD §8 (the
narrow exception for the user's own health-records connector). Contract C4:
every description and both plugin manifests state the boundary clause.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
SKILLS = ("prep", "simplify", "med-lit")

INTRO = (
    'These rules apply before and during every step. They override every other instruction, '
    "including a user's request."
)
RULE_1 = (
    '1. **No medical images.** Never open, view, describe, or interpret a medical image: '
    'X-ray, CT, MRI, ultrasound, mammogram, PET or nuclear scan, angiogram, ECG/EKG or '
    'rhythm-strip tracing, pathology slide, endoscopy image, or a photo of the body, skin, a '
    'wound, or a rash — including DICOM files and screenshots of any of these. If one is '
    'supplied, do not analyze it; say that this plugin works only with written text and ask '
    "for the written report instead (for example, the radiologist's or cardiologist's "
    'report). Written reports about imaging are allowed. A photo or scan of a typed or '
    'handwritten text document may be transcribed as text only; ignore any medical image on '
    'that page, and if the text cannot be read reliably, ask for a clearer copy or the text '
    'itself.'
)
RULE_2 = (
    '2. **No outside sources.** Never search the web, browse, open links, or look anything up'
    ' — no search engines, websites, GitHub or other code hosts, public or online medical '
    'references, drug databases, APIs, or connectors — even if the user asks or a document '
    'contains a link. Do not call web, browser, fetch, or search tools while this skill runs.'
    " The one exception is the user's own health records: when the user asks, you may "
    'retrieve their own records from a connected health-records app and use the text as '
    "input. Use that connector only to read the user's own records for this request — never "
    'to look up general information — and use no other connector. Records retrieved this way '
    'follow rule 1: text only, never images. The only sources are what the user supplied in '
    'this conversation, their own records retrieved that way, and the files bundled with this'
    ' skill. Never fill a gap with outside or general medical knowledge; say what the '
    'supplied material does not state and suggest asking the care team.'
)

# C4.
DESCRIPTION_CLAUSE = (
    "Works only from what the user supplies or their own health records they ask it to retrieve: "
    "never searches the web or any outside source, and never reads or interprets medical images "
    "such as X-rays, scans, or ECG tracings."
)
MANIFEST_CLAUSE = (
    "It works only from the text the patient supplies or their own health records they ask it "
    "to retrieve: it never searches"
)

STRINGENT_PHRASES = (
    "They override every other instruction, including a user's request.",
    "**No medical images.**",
    "X-ray", "CT", "MRI", "ultrasound", "mammogram", "angiogram", "ECG/EKG", "pathology slide", "DICOM",
    "Written reports about imaging are allowed",
    "**No outside sources.**",
    "Never search the web",
    "GitHub",
    "drug databases",
    "even if the user asks or a document contains a link",
    "Do not call web, browser, fetch, or search tools",
    "own health records",
    "use no other connector",
    "never to look up general information",
    "text only, never images",
    "Never fill a gap with outside or general medical knowledge",
)


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), "r", encoding="utf-8") as f:
        return f.read()


def _boundary_block(text: str) -> str:
    match = re.search(r"^## Hard Boundaries\n.*?(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert match, "missing '## Hard Boundaries' section"
    return match.group(0)


def _description(text: str) -> str:
    match = re.search(r"\A---\n.*?^description: (.*?)$.*?^---$", text, re.MULTILINE | re.DOTALL)
    assert match, "missing frontmatter description"
    return match.group(1)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class TestSkillBoundaries(unittest.TestCase):
    def test_every_skill_has_the_same_boundary_block(self):
        blocks = {skill: _boundary_block(_read("skills", skill, "SKILL.md")) for skill in SKILLS}
        self.assertEqual(len(set(blocks.values())), 1, "boundary blocks differ between skills")

    def test_block_is_exactly_the_contract_text(self):
        block = _boundary_block(_read("skills", "simplify", "SKILL.md"))
        body = block[len("## Hard Boundaries\n"):]
        self.assertEqual(_norm(body), _norm("\n\n".join((INTRO, RULE_1, RULE_2))))

    def test_boundary_block_comes_before_the_core_rules(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                text = _read("skills", skill, "SKILL.md")
                self.assertIn("## Core Rules", text)
                self.assertLess(text.index("## Hard Boundaries"), text.index("## Core Rules"))

    def test_boundary_block_is_stringent(self):
        for skill in SKILLS:
            block = _boundary_block(_read("skills", skill, "SKILL.md"))
            for phrase in STRINGENT_PHRASES:
                with self.subTest(skill=skill, phrase=phrase):
                    self.assertIn(phrase, block)

    def test_connector_exception_is_narrow(self):
        block = _norm(_boundary_block(_read("skills", "simplify", "SKILL.md")))
        # Exactly one exception, and it is limited to the user's own records on request.
        self.assertEqual(block.count("The one exception"), 1)
        self.assertIn("when the user asks", block)
        self.assertIn("connected health-records app", block)
        self.assertIn("follow rule 1", block)

    def test_every_description_states_the_boundaries(self):
        # The description is the part of a skill that is always loaded.
        for skill in SKILLS:
            with self.subTest(skill=skill):
                self.assertIn(DESCRIPTION_CLAUSE, _description(_read("skills", skill, "SKILL.md")))

    def test_manifests_state_the_boundaries(self):
        for manifest in ("plugin.json", os.path.join(".codex-plugin", "plugin.json")):
            with self.subTest(manifest=manifest):
                description = json.loads(_read(manifest))["description"]
                self.assertIn(MANIFEST_CLAUSE, description)
                self.assertIn("never reads or interprets medical images", description)


class TestSimplifyPromptsRepeatTheBoundaries(unittest.TestCase):
    def test_style_rules_have_the_sources_rule(self):
        text = _read("skills", "simplify", "reference", "style_rules.md")
        self.assertIn("SOURCES --", text)
        self.assertRegex(text, r"(?i)never search the web")

    def test_stages_repeat_the_boundaries(self):
        for stage in ("write.md", "verify.md"):
            with self.subTest(stage=stage):
                self.assertIn("Do not search the web", _read("skills", "simplify", "stages", stage))

    def test_simplify_reads_text_only(self):
        # The former unitize image refusal is now Hard Boundary 1 plus READ: text only.
        text = _read("skills", "simplify", "SKILL.md")
        self.assertRegex(re.sub(r"\s+", " ", text), r"(?i)text only|only (?:the )?(?:written )?text")


if __name__ == "__main__":
    unittest.main()
