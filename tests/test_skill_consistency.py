"""Cross-check SKILL.md and stage prompts against bundled resources.

This test parses text, not behaviour: it does not run any script or
dispatch any agent, so it is fast and needs no fixtures.
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "simplify")
SKILL_MD_PATH = os.path.join(SKILL_DIR, "SKILL.md")
STAGES_DIR = os.path.join(SKILL_DIR, "stages")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
REFERENCE_DIR = os.path.join(SKILL_DIR, "reference")
SCHEMA_DIR = os.path.join(SKILL_DIR, "schema")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_frontmatter(text: str) -> dict:
    """Parse a simple `---\\nkey: value\\n...---` block at the top of
    `text` into {key: value}. Each field must be a single line (true of
    every frontmatter field in this plugin)."""
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file does not start with a frontmatter block"
    fields: dict = {}
    order: list = []
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            fields[key] = value.strip()
            order.append(key)
        i += 1
    assert i < len(lines), "frontmatter block never closes with ---"
    fields["__order__"] = order
    return fields


class TestSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)
        self.frontmatter = _parse_frontmatter(self.text)

    def test_frontmatter_has_exactly_name_and_description(self):
        keys = set(self.frontmatter["__order__"])
        self.assertEqual(keys, {"name", "description"})

    def test_frontmatter_name_is_simplify(self):
        self.assertEqual(self.frontmatter["name"], "simplify")

    def test_frontmatter_description_nonempty(self):
        self.assertTrue(self.frontmatter["description"])


class TestScriptAndStageMentionsExist(unittest.TestCase):
    def setUp(self):
        stage_text = "\n".join(
            _read(os.path.join(STAGES_DIR, name))
            for name in sorted(os.listdir(STAGES_DIR))
            if name.endswith(".md")
        )
        self.text = _read(SKILL_MD_PATH) + "\n" + stage_text

    def test_every_mentioned_script_exists(self):
        mentioned = sorted(set(re.findall(r"scripts/([A-Za-z_]+\.py)", self.text)))
        self.assertTrue(mentioned, "SKILL.md should mention at least one script")
        for name in mentioned:
            path = os.path.join(SCRIPTS_DIR, name)
            self.assertTrue(os.path.isfile(path), f"SKILL.md mentions scripts/{name}, which does not exist")

    def test_every_mentioned_stage_file_exists(self):
        mentioned = sorted(set(re.findall(r"stages/([A-Za-z_]+\.md)", self.text)))
        self.assertTrue(mentioned, "SKILL.md should mention at least one stage file")
        for name in mentioned:
            path = os.path.join(STAGES_DIR, name)
            self.assertTrue(os.path.isfile(path), f"SKILL.md mentions stages/{name}, which does not exist")

    def test_every_mentioned_reference_file_exists(self):
        mentioned = sorted(set(re.findall(r"reference/([A-Za-z0-9_.]+\.(?:md|json))", self.text)))
        self.assertTrue(mentioned, "SKILL.md should mention at least one reference file")
        for name in mentioned:
            path = os.path.join(REFERENCE_DIR, name)
            self.assertTrue(os.path.isfile(path), f"SKILL.md mentions reference/{name}, which does not exist")

    def test_every_mentioned_schema_file_exists(self):
        mentioned = sorted(set(re.findall(r"schema/([A-Za-z0-9_.]+\.json)", self.text)))
        self.assertTrue(mentioned, "SKILL.md should mention at least one schema file")
        for name in mentioned:
            path = os.path.join(SCHEMA_DIR, name)
            self.assertTrue(os.path.isfile(path), f"SKILL.md mentions schema/{name}, which does not exist")


if __name__ == "__main__":
    unittest.main()
