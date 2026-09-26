"""Cross-check SKILL.md and stage prompts against bundled resources.

This test parses text, not behaviour: it does not run any script or
dispatch any agent, so it is fast and needs no fixtures.
"""

from __future__ import annotations

import os
import json
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
OPENAI_YAML_PATH = os.path.join(SKILL_DIR, "agents", "openai.yaml")
PLUGIN_JSON_PATH = os.path.join(REPO_ROOT, "plugin.json")
CODEX_PLUGIN_JSON_PATH = os.path.join(REPO_ROOT, ".codex-plugin", "plugin.json")

DEFAULT_PROMPT = (
    "Run the complete $simplify workflow on the supplied medical documents. "
    "Return only the validated final report and requested artifacts. "
    "Do not summarize the documents directly."
)

OBSOLETE_REFERENCES = {
    "stages/review_fidelity.md",
    "stages/review_coverage.md",
    "stages/correct.md",
    "stages/assemble_missing.md",
    "scripts/sanitize_review.py",
    "scripts/diff_guard.py",
    "schema/manifest.schema.json",
    "schema/coverage_raw.schema.json",
    "schema/coverage.schema.json",
    "schema/additions_raw.schema.json",
    "schema/additions.schema.json",
    "02_facts.txt",
    "04_coverage.json",
    "05_plan.corrected.raw.json",
    "05_plan.corrected.json",
    "05_additions.raw.json",
    "05_additions.json",
}


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    assert match, f"missing YAML key: {key}"
    return match.group(1).strip("'\"")


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


class TestMandatoryWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)

    def test_execution_contract_is_prominent_and_forbids_direct_answers(self):
        heading = "## Non-Negotiable Execution Contract"
        self.assertIn(heading, self.text)
        self.assertLess(self.text.index(heading), self.text.index("## Core Rules"))
        self.assertIn("Never simplify, summarize, or answer directly", self.text)
        self.assertIn("Do not present clinical content until finalization succeeds", self.text)

    def test_contract_requires_validated_final_artifacts_and_report_only(self):
        self.assertIn("validated `06_plan.final.json` and `report.md`", self.text)
        self.assertIn("Present only `<run>/report.md`", self.text)
        self.assertIn("Do not create a second summary", self.text)

    def test_contract_is_fail_closed_without_substitute_summary(self):
        self.assertIn("one retry", self.text.lower())
        self.assertIn("workflow failure", self.text.lower())
        self.assertIn("without providing a substitute medical summary", self.text)
        self.assertNotIn("Fall back to the draft plan", self.text)
        self.assertNotIn("Continue with a recorded notice if a review fails", self.text)

    def test_core_graph_and_bounded_reassembly_are_current(self):
        self.assertIn("ground[1..K]", self.text)
        self.assertIn("assemble", self.text)
        self.assertIn("combined independent review", self.text)
        self.assertIn("deterministic settlement", self.text)
        self.assertIn("approximately 13 core artifacts", self.text)
        self.assertIn("reassemble once", self.text.lower())
        self.assertIn("fresh independent review", self.text.lower())
        self.assertIn("A second reassembly request fails the run", self.text)

    def test_output_remains_concise_and_critical_first(self):
        self.assertIn("concise and action-first", self.text)
        self.assertIn("critical", self.text.lower())
        self.assertIn("generic", self.text.lower())
        self.assertIn("omitted", self.text.lower())

    def test_current_core_stage_script_and_schema_names_are_used(self):
        required = {
            "stages/ground.md",
            "stages/assemble.md",
            "stages/review.md",
            "scripts/unitize.py",
            "scripts/anchor_check.py",
            "scripts/merge_facts.py",
            "scripts/cite_check.py",
            "scripts/numeric_parity.py",
            "scripts/settle_review.py",
            "scripts/finalize.py",
            "schema/facts_raw.schema.json",
            "schema/care_plan_agent.schema.json",
            "schema/review_raw.schema.json",
        }
        for reference in sorted(required):
            self.assertIn(reference, self.text)

    def test_obsolete_workflow_references_are_absent(self):
        for reference in sorted(OBSOLETE_REFERENCES):
            self.assertNotIn(reference, self.text)


class TestEntryPointConsistency(unittest.TestCase):
    def setUp(self):
        self.openai_yaml = _read(OPENAI_YAML_PATH)
        self.plugin = _read_json(PLUGIN_JSON_PATH)
        self.codex_plugin = _read_json(CODEX_PLUGIN_JSON_PATH)

    def test_default_prompt_is_identical_across_all_entry_points(self):
        openai_prompt = _yaml_scalar(self.openai_yaml, "default_prompt")
        plugin_prompt = self.plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"]
        codex_prompt = self.codex_plugin["interface"]["defaultPrompt"]
        self.assertEqual(plugin_prompt, [DEFAULT_PROMPT])
        self.assertEqual(codex_prompt, [DEFAULT_PROMPT])
        self.assertEqual(openai_prompt, DEFAULT_PROMPT)

    def test_implicit_invocation_is_disabled(self):
        self.assertEqual(_yaml_scalar(self.openai_yaml, "allow_implicit_invocation"), "false")

    def test_plugin_manifest_interfaces_remain_in_parity(self):
        self.assertEqual(
            self.plugin["extensions"]["com.openai"]["interface"],
            self.codex_plugin["interface"],
        )


if __name__ == "__main__":
    unittest.main()
