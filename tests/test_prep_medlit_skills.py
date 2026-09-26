"""Structural and safety-invariant checks for the instruction-only prep and med-lit skills."""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

SKILLS_DIR = os.path.join(_paths.REPO_ROOT, "skills")
NEW_SKILLS = ("prep", "med-lit")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "missing frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    assert match, f"missing YAML key: {key}"
    return match.group(1).strip("'\"")


class TestNewSkillLayout(unittest.TestCase):
    def test_frontmatter_is_name_and_description_only(self):
        for skill in NEW_SKILLS:
            with self.subTest(skill=skill):
                fields = _frontmatter(_read(os.path.join(SKILLS_DIR, skill, "SKILL.md")))
                self.assertEqual(set(fields), {"name", "description"})
                self.assertEqual(fields["name"], skill)
                self.assertIn("Do not use", fields["description"])

    def test_skills_are_instruction_only(self):
        for skill in NEW_SKILLS:
            with self.subTest(skill=skill):
                root = os.path.join(SKILLS_DIR, skill)
                self.assertFalse(os.path.exists(os.path.join(root, "scripts")))
                for _dirpath, _dirs, files in os.walk(root):
                    self.assertFalse([f for f in files if f.endswith(".py")])

    def test_every_referenced_file_exists(self):
        for skill in NEW_SKILLS:
            root = os.path.join(SKILLS_DIR, skill)
            text = _read(os.path.join(root, "SKILL.md"))
            refs = set(re.findall(r"references/[A-Za-z0-9_.-]+\.md", text))
            self.assertTrue(refs, skill)
            for ref in refs:
                with self.subTest(skill=skill, ref=ref):
                    self.assertTrue(os.path.isfile(os.path.join(root, ref)))

    def test_every_reference_file_is_used(self):
        for skill in NEW_SKILLS:
            root = os.path.join(SKILLS_DIR, skill)
            text = _read(os.path.join(root, "SKILL.md"))
            for name in os.listdir(os.path.join(root, "references")):
                with self.subTest(skill=skill, ref=name):
                    self.assertIn(f"references/{name}", text)

    def test_openai_metadata_icons_and_prompt(self):
        for skill in NEW_SKILLS:
            with self.subTest(skill=skill):
                root = os.path.join(SKILLS_DIR, skill)
                yaml = _read(os.path.join(root, "agents", "openai.yaml"))
                for key in ("icon_small", "icon_large"):
                    self.assertTrue(os.path.isfile(os.path.join(root, _yaml_scalar(yaml, key))))
                self.assertIn(f"${skill}", _yaml_scalar(yaml, "default_prompt"))
                self.assertNotIn("dependencies:", yaml)

    def test_med_lit_requires_explicit_invocation(self):
        yaml = _read(os.path.join(SKILLS_DIR, "med-lit", "agents", "openai.yaml"))
        self.assertEqual(_yaml_scalar(yaml, "allow_implicit_invocation"), "false")


class TestBhlsScoring(unittest.TestCase):
    """The profile example must agree with the scoring table it documents."""

    def setUp(self):
        root = os.path.join(SKILLS_DIR, "med-lit", "references")
        self.bhls = _read(os.path.join(root, "bhls.md"))
        template = _read(os.path.join(root, "profile-template.md"))
        block = re.search(r"```json\n(.*?)\n```", template, re.DOTALL)
        self.profile = json.loads(block.group(1))

    def _points(self) -> dict:
        table = {}
        for row in re.findall(r"^\| ([^|]+?) \| (\d) \| ([^|]+?) \| (\d) \|$", self.bhls, re.MULTILINE):
            table[("bhls_confidence_forms", row[0])] = int(row[1])
            for item in ("bhls_help_reading", "bhls_problems_learning"):
                table[(item, row[2])] = int(row[3])
        return table

    def test_each_item_has_five_distinct_points(self):
        table = self._points()
        for item in ("bhls_confidence_forms", "bhls_help_reading", "bhls_problems_learning"):
            values = sorted(v for (i, _), v in table.items() if i == item)
            self.assertEqual(values, [1, 2, 3, 4, 5])

    def test_example_profile_is_scored_by_the_table(self):
        table = self._points()
        responses = self.profile["responses"]
        self.assertEqual(len(responses), 3)
        for response in responses:
            self.assertEqual(table[(response["item_id"], response["option"])], response["points"])
        self.assertEqual(self.profile["score"], sum(r["points"] for r in responses))
        self.assertTrue(self.profile["score_eligible"])
        self.assertEqual(self.profile["score_range"], [3, 15])

    def test_profile_never_labels_a_level(self):
        self.assertIsNone(self.profile["interpretation"]["label"])
        self.assertFalse(self.profile["administration"]["validated_mode"])
        self.assertNotIn("level", self.profile)


if __name__ == "__main__":
    unittest.main()
