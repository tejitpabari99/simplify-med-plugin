"""Cross-check the prompt-only `simplify` skill against its file set and entry points.

`simplify` is instruction-only: the host reads `SKILL.md`, the two stage
files, and the style rules, and runs no code (contracts C2, C5, C7). These
tests parse text; they run no script and dispatch no agent.
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
SKILLS_ROOT = os.path.join(REPO_ROOT, "skills")
SKILL_DIR = _paths.SKILL_DIR
SKILL_MD_PATH = os.path.join(SKILL_DIR, "SKILL.md")
OPENAI_YAML_PATH = os.path.join(SKILL_DIR, "agents", "openai.yaml")
PLUGIN_JSON_PATH = os.path.join(REPO_ROOT, "plugin.json")
CODEX_PLUGIN_JSON_PATH = os.path.join(REPO_ROOT, ".codex-plugin", "plugin.json")

# C2: the complete skill file set.
SKILL_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "assets/icon-large.png",
    "assets/icon-small.svg",
    "stages/write.md",
    "stages/verify.md",
    "reference/style_rules.md",
    "reference/abbreviations.json",
    "schema/plan.schema.json",
}
PROMPT_FILES = ("SKILL.md", "stages/write.md", "stages/verify.md", "reference/style_rules.md")

# C5.
DEFAULT_PROMPT = (
    "Run the complete $simplify workflow on the supplied medical documents: "
    "write the short report, verify it against the source, and return only the verified report."
)

# C7.
TITLES = (
    "Your ER visit, simplified",
    "Your urgent care visit, simplified",
    "Your hospital stay, simplified",
    "Your visit, simplified",
    "Your test results, simplified",
    "Your procedure, simplified",
    "Your documents, simplified",
)
HEADINGS = (
    "What did they find?",
    "What should you do now?",
    "When should you go back to the ER?",
    "When to get help right away",
    "Questions you may want to ask",
)
LABELS = ("The ER diagnosed you with:", "Diagnosed with:")
VISIT_TYPES = ("er_visit", "urgent_care", "hospital_stay", "clinic_visit", "test_results", "procedure", "other")

# Retired pipeline artifacts SKILL.md must not name (W3.6).
SKILL_MD_RETIRED = (
    r"scripts/", r"\.py\b", r"(?i)python", r"01_source\.txt", r"01_units", r"run\.json",
    r"05_plan\.final", r"report\.md", r"unit_ids", r"(?i)glossary",
)
# Retired names none of the four prompt files may mention (W1 acceptance).
PROMPT_RETIRED = (
    r"scripts/", r"(?i)python", r"\.py\b", r"unit_ids", r"run\.json", r"01_source\.txt",
    r"05_plan\.final", r"(?i)glossary", r"(?i)\bsettle\b", r"(?i)\bfinalize\b",
)
# Files deleted from skills/simplify; nothing under skills/ may reference them.
DELETED_FILE_PATTERNS = (
    r"scripts/", r"templates/", r"report\.html", r"stages/glossary\.md", r"ahrq_plain_language",
    r"\bunitize\b", r"check_draft", r"glossary_check", r"plan_view", r"plan_paths", r"render_(?:html|md|audit)",
    r"numtokens", r"runlog", r"textnorm", r"_version\.py",
    r"\b(?:readability|validate|settle|finalize|protected)\.py\b",
    r"\b(?:check|draft|draft_checked|glossary|glossary_raw|protected|run|units|verify|verify_raw)\.schema\.json",
)
TEXT_SUFFIXES = (".md", ".json", ".yaml", ".yml", ".txt", ".svg")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _prompt_texts() -> dict:
    return {name: _read(os.path.join(SKILL_DIR, name)) for name in PROMPT_FILES}


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    assert match, f"missing YAML key: {key}"
    return match.group(1).strip("'\"")


def _parse_frontmatter(text: str) -> dict:
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file does not start with a frontmatter block"
    fields: dict = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        key, sep, value = lines[i].partition(":")
        if sep:
            fields[key.strip()] = value.strip()
        i += 1
    assert i < len(lines), "frontmatter block never closes with ---"
    return fields


def _skill_files_on_disk() -> set:
    found = set()
    for dirpath, _dirnames, filenames in os.walk(SKILL_DIR):
        for name in filenames:
            if name == ".DS_Store":
                continue
            found.add(os.path.relpath(os.path.join(dirpath, name), SKILL_DIR).replace(os.sep, "/"))
    return found


class TestSkillFileSet(unittest.TestCase):
    def test_skill_holds_exactly_the_contract_files(self):
        self.assertEqual(_skill_files_on_disk(), SKILL_FILES)

    def test_no_code_in_the_skill(self):
        for relative in _skill_files_on_disk():
            self.assertFalse(relative.endswith((".py", ".pyc", ".sh", ".js")), relative)
        for folder in ("scripts", "templates"):
            self.assertFalse(os.path.exists(os.path.join(SKILL_DIR, folder)), folder)


class TestSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.frontmatter = _parse_frontmatter(_read(SKILL_MD_PATH))

    def test_frontmatter_has_exactly_name_and_description(self):
        self.assertEqual(set(self.frontmatter), {"name", "description"})
        self.assertEqual(self.frontmatter["name"], "simplify")

    def test_description_states_trigger_and_boundary(self):
        description = self.frontmatter["description"]
        self.assertIn("Use when", description)
        self.assertIn("Do not use", description)


class TestMentionedPathsExist(unittest.TestCase):
    """Every stages/, reference/, schema/ path named by a prompt file exists and is in C2."""

    def test_every_mentioned_path_exists(self):
        mentioned = set()
        for name, text in _prompt_texts().items():
            for match in re.findall(r"\b((?:stages|reference|schema)/[A-Za-z0-9_.-]+\.(?:md|json))", text):
                mentioned.add((name, match))
        self.assertTrue(mentioned)
        for name, path in sorted(mentioned):
            with self.subTest(file=name, path=path):
                self.assertIn(path, SKILL_FILES)
                self.assertTrue(os.path.isfile(os.path.join(SKILL_DIR, path)))

    def test_skill_md_names_the_files_to_read(self):
        text = _read(SKILL_MD_PATH)
        for path in ("stages/write.md", "stages/verify.md", "reference/style_rules.md",
                     "reference/abbreviations.json", "schema/plan.schema.json"):
            self.assertIn(path, text)


class TestRetiredNamesAbsent(unittest.TestCase):
    def test_skill_md_names_no_script_or_retired_artifact(self):
        text = _read(SKILL_MD_PATH)
        for pattern in SKILL_MD_RETIRED:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text), pattern)

    def test_prompt_files_name_no_retired_pipeline_part(self):
        for name, text in _prompt_texts().items():
            for pattern in PROMPT_RETIRED:
                with self.subTest(file=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text), pattern)

    def test_nothing_under_skills_references_a_deleted_file(self):
        for dirpath, _dirs, filenames in os.walk(SKILLS_ROOT):
            for filename in filenames:
                if not filename.endswith(TEXT_SUFFIXES):
                    continue
                path = os.path.join(dirpath, filename)
                text = _read(path)
                for pattern in DELETED_FILE_PATTERNS:
                    with self.subTest(file=os.path.relpath(path, REPO_ROOT), pattern=pattern):
                        self.assertIsNone(re.search(pattern, text), pattern)


class TestSkillInstructions(unittest.TestCase):
    def setUp(self):
        self.text = _read(SKILL_MD_PATH)
        self.flat = re.sub(r"\s+", " ", self.text)

    def _assert_says(self, pattern: str) -> None:
        self.assertIsNotNone(re.search(pattern, self.flat), f"SKILL.md lacks {pattern!r}")

    def test_skill_md_stays_short(self):
        self.assertLess(len(self.text.splitlines()), 100)

    def test_reads_only_the_named_files(self):
        match = re.search(r"[^.]*\bother plugin files?\b[^.]*\.", self.flat)
        self.assertIsNotNone(match, "SKILL.md must forbid opening other plugin files")
        rule = match.group(0)
        self.assertRegex(rule, r"(?i)\bnever\b")
        for verb in ("open", "list", "download", "unpack"):
            self.assertIn(verb, rule)

    def test_runs_no_code(self):
        self._assert_says(r"(?i)\bno (?:scripts?|code)\b|never run (?:any )?(?:scripts?|code)")

    def test_flow_is_read_write_verify_output(self):
        positions = []
        for step in ("read", "write", "verify", "output"):
            match = (re.search(rf"(?im)^#+\s*(?:(?:step\s*)?\d+[.:]?\s*)?{step}\b", self.text)
                     or re.search(rf"\b{step.upper()}\b", self.text))
            self.assertIsNotNone(match, f"no {step} step")
            positions.append(match.start())
        self.assertEqual(positions, sorted(positions))

    def test_verification_by_sub_agent_or_second_pass(self):
        self._assert_says(r"(?i)sub-?agent")
        self._assert_says(r"(?i)second pass")
        self._assert_says(r"(?i)exactly once")

    def test_fail_closed(self):
        self._assert_says(r"(?i)never (?:show|present|return)[^.]*(?:unverified|not been verified)")
        self._assert_says(r"(?i)only the verified report|only (?:the )?(?:corrected|verified) draft")
        self._assert_says(r"(?i)never answer directly|never (?:simplify|summarize|answer)[^.]*directly")

    def test_markdown_by_default_json_on_request(self):
        self.assertIn("Markdown", self.text)
        self._assert_says(r"(?i)json[^.]*(?:only )?(?:when|if|on)[^.]*(?:ask|request)")

    def test_report_format(self):
        for phrase in TITLES + HEADINGS + LABELS + VISIT_TYPES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)
        self._assert_says(r"(?i)300 words")


class TestEntryPointConsistency(unittest.TestCase):
    def setUp(self):
        self.openai_yaml = _read(OPENAI_YAML_PATH)
        self.plugin = _read_json(PLUGIN_JSON_PATH)
        self.codex_plugin = _read_json(CODEX_PLUGIN_JSON_PATH)

    def test_default_prompt_is_identical_across_all_entry_points(self):
        self.assertEqual(_yaml_scalar(self.openai_yaml, "default_prompt"), DEFAULT_PROMPT)
        self.assertEqual(self.plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"][0], DEFAULT_PROMPT)
        self.assertEqual(self.codex_plugin["interface"]["defaultPrompt"][0], DEFAULT_PROMPT)

    def test_implicit_invocation_is_disabled(self):
        self.assertEqual(_yaml_scalar(self.openai_yaml, "allow_implicit_invocation"), "false")

    def test_plugin_manifest_interfaces_remain_in_parity(self):
        self.assertEqual(self.plugin["extensions"]["com.openai"]["interface"], self.codex_plugin["interface"])

    def test_manifests_describe_no_deterministic_pipeline(self):
        for data in (self.plugin, self.codex_plugin):
            blob = json.dumps(data)
            for phrase in ("deterministic validation", "audit trail", "scripts/"):
                self.assertNotIn(phrase, blob)


if __name__ == "__main__":
    unittest.main()
