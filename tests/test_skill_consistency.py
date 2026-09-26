"""Cross-check SKILL.md and stage prompts against bundled resources.

This test parses text, not behaviour: it does not run any script or
dispatch any agent, so it is fast and needs no fixtures.
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

# Names from retired pipelines that must not reappear in the skill or its prompts.
OBSOLETE_NAMES = (
    "ground.md",
    "assemble.md",
    "stages/review.md",
    "review_fidelity",
    "review_coverage",
    "assemble_missing",
    "correct.md",
    "categories.md",
    "cite_check.py",
    "anchor_check.py",
    "merge_facts.py",
    "numeric_parity.py",
    "settle_review.py",
    "facts_raw",
    "care_plan_agent",
    "review_raw",
    "flags.schema",
    "02_facts",
    "03_plan",
    "03_flags",
    "04_review",
    "05_plan.settled",
    "06_plan.final",
    "01_units.<k>",
    "omitted_facts",
    "fact_id",
    "reassemble",
    "CRITICAL VS SUPPORTING",
)

# The PRD section 4 graph, in execution order.
CORE_SEQUENCE = (
    "scripts/unitize.py",
    "stages/write.md",
    "scripts/check_draft.py",
    "stages/verify.md",
    "scripts/settle.py",
    "scripts/finalize.py",
)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _stage_texts() -> dict:
    return {
        name: _read(os.path.join(STAGES_DIR, name))
        for name in sorted(os.listdir(STAGES_DIR))
        if name.endswith(".md")
    }


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
        self.assertEqual(set(self.frontmatter["__order__"]), {"name", "description"})

    def test_frontmatter_name_is_simplify(self):
        self.assertEqual(self.frontmatter["name"], "simplify")

    def test_description_states_trigger_and_boundary(self):
        description = self.frontmatter["description"]
        self.assertIn("Use when", description)
        self.assertIn("Do not use", description)


class TestMentionedPathsExist(unittest.TestCase):
    """Every script, stage, reference, and schema named by SKILL.md or a stage exists."""

    def setUp(self):
        self.text = _read(SKILL_MD_PATH) + "\n" + "\n".join(_stage_texts().values())

    def _assert_all_exist(self, pattern: str, directory: str, label: str):
        mentioned = sorted(set(re.findall(pattern, self.text)))
        self.assertTrue(mentioned, f"expected at least one {label} mention")
        missing = [name for name in mentioned if not os.path.isfile(os.path.join(directory, name))]
        self.assertEqual(missing, [], f"mentioned {label} files do not exist: {missing}")

    def test_every_mentioned_script_exists(self):
        self._assert_all_exist(r"scripts/([A-Za-z_]+\.py)", SCRIPTS_DIR, "scripts/")

    def test_every_mentioned_stage_exists(self):
        self._assert_all_exist(r"stages/([A-Za-z_]+\.md)", STAGES_DIR, "stages/")

    def test_every_mentioned_reference_exists(self):
        self._assert_all_exist(r"reference/([A-Za-z0-9_.]+\.(?:md|json))", REFERENCE_DIR, "reference/")

    def test_every_mentioned_schema_exists(self):
        self._assert_all_exist(r"schema/([A-Za-z0-9_.]+\.json)", SCHEMA_DIR, "schema/")


class TestObsoleteNamesAbsent(unittest.TestCase):
    def test_retired_files_are_deleted(self):
        for relative in (
            "stages/ground.md",
            "stages/assemble.md",
            "stages/review.md",
            "reference/categories.md",
        ):
            self.assertFalse(os.path.exists(os.path.join(SKILL_DIR, relative)), relative)

    def test_skill_and_stages_do_not_name_retired_pipeline_parts(self):
        documents = {"SKILL.md": _read(SKILL_MD_PATH)}
        documents.update({f"stages/{k}": v for k, v in _stage_texts().items()})
        documents["reference/style_rules.md"] = _read(os.path.join(REFERENCE_DIR, "style_rules.md"))
        for name, text in documents.items():
            for obsolete in OBSOLETE_NAMES:
                self.assertNotIn(obsolete, text, f"{name} still mentions {obsolete!r}")


class TestExecutionContract(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)

    def test_core_graph_runs_in_prd_order(self):
        workflow = self.text[self.text.index("## Workflow"):]
        positions = []
        for step in CORE_SEQUENCE:
            self.assertIn(step, workflow)
            positions.append(workflow.index(step))
        self.assertEqual(positions, sorted(positions), "SKILL.md lists the core steps out of order")

    def test_model_stages_name_their_inputs_and_outputs(self):
        for artifact in (
            "01_source.txt",
            "01_protected.json",
            "schema/draft.schema.json",
            "02_draft.raw.json",
            "02_draft.json",
            "02_check.json",
            "schema/verify_raw.schema.json",
            "03_verify.raw.json",
            "reference/style_rules.md",
        ):
            self.assertIn(artifact, self.text)

    def test_repair_round_is_bounded_and_uses_round_two(self):
        self.assertIn("scripts/check_draft.py --run-dir <run> --round 2", self.text)
        self.assertIn("scripts/settle.py --run-dir <run> --round 2", self.text)
        for artifact in ("04_repair.json", "02_draft.r2.raw.json", "02_draft.r2.json",
                         "02_check.r2.json", "03_verify.r2.raw.json"):
            self.assertIn(artifact, self.text)
        self.assertRegex(self.text, r"(?i)at most once|one repair round")

    def test_settle_exit_codes_are_handled(self):
        for code in ("Exit 0", "Exit 1", "Exit 3"):
            self.assertIn(code, self.text)
        self.assertIn("Any other exit stops the run", self.text)

    def test_verify_is_independent(self):
        self.assertIn("fresh sub-agent", self.text)

    def test_host_never_reads_units_json(self):
        for line in self.text.splitlines():
            if "01_units.json" in line:
                self.assertRegex(line, r"(?i)\bnever\b", f"line may instruct reading 01_units.json: {line}")

    def test_fail_closed_and_report_only(self):
        self.assertIn("Never simplify, summarize, or answer directly", self.text)
        self.assertIn("05_plan.final.json", self.text)
        self.assertIn("Present only `<run>/report.md`", self.text)
        self.assertIn("Do not create a second summary", self.text)
        self.assertIn("never write your own summary", self.text)
        self.assertIn("show no clinical content", self.text)

    def test_optional_outputs_only_on_request(self):
        for command in ("scripts/glossary_check.py", "scripts/render_html.py", "scripts/render_audit.py",
                        "stages/glossary.md"):
            self.assertIn(command, self.text)
        self.assertIn("Only when the user asks", self.text)

    def test_skill_md_stays_short(self):
        self.assertLess(len(self.text.splitlines()), 130)


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
