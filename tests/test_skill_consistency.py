"""Cross-checks SKILL.md against the actual files it references: scripts,
stage files, agent files, and reference/schema files it names must all
exist, and the agent <-> stage-file <-> SKILL.md mapping must be
consistent in both directions.

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
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "simplify-med")
SKILL_MD_PATH = os.path.join(SKILL_DIR, "SKILL.md")
AGENTS_DIR = os.path.join(REPO_ROOT, "agents")
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


def _agent_files() -> list:
    return sorted(
        os.path.join(AGENTS_DIR, name)
        for name in os.listdir(AGENTS_DIR)
        if name.endswith(".md")
    )


class TestSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)
        self.frontmatter = _parse_frontmatter(self.text)

    def test_frontmatter_has_exactly_name_and_description(self):
        keys = set(self.frontmatter["__order__"])
        self.assertEqual(keys, {"name", "description"})

    def test_frontmatter_name_is_simplify_med(self):
        self.assertEqual(self.frontmatter["name"], "simplify-med")

    def test_frontmatter_description_nonempty(self):
        self.assertTrue(self.frontmatter["description"])


class TestScriptAndStageMentionsExist(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)

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


class TestAgentNamesRoundTrip(unittest.TestCase):
    """Every agent name mentioned in SKILL.md must resolve to a real agent
    file whose own frontmatter `name:` matches, and every real agent
    file's name must in turn be mentioned in SKILL.md."""

    def setUp(self):
        self.skill_text = _read(SKILL_MD_PATH)
        self.agent_names_on_disk = {}
        for path in _agent_files():
            fm = _parse_frontmatter(_read(path))
            self.agent_names_on_disk[fm["name"]] = path

    def test_agent_files_are_named_simplify_med_prefixed(self):
        self.assertTrue(self.agent_names_on_disk, "no agent files found under agents/")
        for name in self.agent_names_on_disk:
            self.assertTrue(name.startswith("simplify-med-"), name)

    def test_every_agent_name_mentioned_in_skill_exists_on_disk(self):
        mentioned = {name for name in self.agent_names_on_disk if name in self.skill_text}
        # Every agent on disk must actually be mentioned (this also proves
        # the reverse direction below is non-vacuous).
        self.assertEqual(mentioned, set(self.agent_names_on_disk))

    def test_every_agent_file_name_is_mentioned_in_skill(self):
        for name, path in self.agent_names_on_disk.items():
            self.assertIn(name, self.skill_text, f"{path} declares name {name!r}, not mentioned in SKILL.md")


class TestStageFileAgentBijection(unittest.TestCase):
    """Each stage file under stages/ corresponds, by this plugin's naming
    convention (agent `simplify-med-<x-y>` <-> stage file `<x_y>.md`), to
    exactly one agent. Confirms the correspondence is a total bijection:
    no orphaned stage file, no orphaned agent, no collision."""

    def _derived_stage_filename(self, agent_name: str) -> str:
        stem = agent_name[len("simplify-med-"):]
        return stem.replace("-", "_") + ".md"

    def test_stage_files_map_one_to_one_to_agents(self):
        agent_paths = _agent_files()
        agent_names = [_parse_frontmatter(_read(p))["name"] for p in agent_paths]

        stage_files_on_disk = sorted(
            name for name in os.listdir(STAGES_DIR) if name.endswith(".md")
        )

        derived = [self._derived_stage_filename(n) for n in agent_names]

        # No agent maps to a nonexistent stage file.
        for stage_name, agent_name in zip(derived, agent_names):
            self.assertIn(
                stage_name, stage_files_on_disk,
                f"agent {agent_name!r} implies stages/{stage_name}, which does not exist",
            )

        # No stage file is left unclaimed by any agent.
        self.assertEqual(
            sorted(derived), stage_files_on_disk,
            "stage files and agent-derived stage names differ -- some stage file has no "
            "agent, or some agent implies a stage file that isn't there",
        )

        # Bijection: no stage file claimed by more than one agent.
        self.assertEqual(len(derived), len(set(derived)), "two agents map to the same stage file")


class TestAgentToolsRestricted(unittest.TestCase):
    def test_every_agent_tools_is_read_write_only(self):
        for path in _agent_files():
            fm = _parse_frontmatter(_read(path))
            self.assertIn("tools", fm, path)
            tools = {t.strip() for t in fm["tools"].split(",") if t.strip()}
            self.assertEqual(tools, {"Read", "Write"}, f"{path} declares tools: {fm['tools']!r}")


if __name__ == "__main__":
    unittest.main()
