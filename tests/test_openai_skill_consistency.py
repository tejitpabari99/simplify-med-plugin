"""Drift guard between the canonical `SKILL.md` and the OpenAI-specific,
self-contained orchestrator `SKILL.md` used only for the `--no-mcp` build
(see docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md, D3).

This test parses text, not behaviour: it does not run any script or
dispatch any agent, so it is fast and needs no fixtures. It reuses the
same extraction regexes as `test_skill_consistency.py` so both files stay
provably in the same stage/script order without hand-copying paths.
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
CANONICAL_SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
OPENAI_SKILL_MD = os.path.join(
    REPO_ROOT, "packaging", "openai", "skills", "simplify-med", "SKILL.md"
)
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
STAGES_DIR = os.path.join(SKILL_DIR, "stages")

SCRIPT_RE = r"scripts/([A-Za-z_]+\.py)"
STAGE_RE = r"stages/([A-Za-z_]+\.md)"

FORBIDDEN_SUBSTRINGS = (
    "agents/",
    "custom_start",
    "custom_end",
    "render_simplify_med_report",
)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _dedup_in_order(items) -> list:
    """Return `items` deduplicated, keeping each item's first-occurrence
    position (plain `set()` would lose order, which is exactly what this
    drift guard needs to catch)."""
    seen: list = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _extract_matches(text: str, pattern: str) -> list:
    return _dedup_in_order(re.findall(pattern, text))


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


class TestScriptAndStageOrderMatchesCanonical(unittest.TestCase):
    """The OpenAI orchestrator SKILL.md must reference the same scripts,
    and the same stage files, in the same order, as the canonical
    SKILL.md -- this is the one drift check D3 requires."""

    def setUp(self):
        self.canonical_text = _read(CANONICAL_SKILL_MD)
        self.openai_text = _read(OPENAI_SKILL_MD)

    def test_script_order_matches_canonical(self):
        canonical = _extract_matches(self.canonical_text, SCRIPT_RE)
        openai = _extract_matches(self.openai_text, SCRIPT_RE)
        self.assertTrue(canonical, "canonical SKILL.md should mention at least one script")
        self.assertEqual(
            openai,
            canonical,
            "packaging/openai/skills/simplify-med/SKILL.md's scripts/*.py "
            f"references {openai!r} do not match canonical skills/simplify-med/"
            f"SKILL.md's {canonical!r} (same set, same order expected)",
        )

    def test_stage_order_matches_canonical(self):
        canonical = _extract_matches(self.canonical_text, STAGE_RE)
        openai = _extract_matches(self.openai_text, STAGE_RE)
        self.assertTrue(canonical, "canonical SKILL.md should mention at least one stage file")
        self.assertEqual(
            openai,
            canonical,
            "packaging/openai/skills/simplify-med/SKILL.md's stages/*.md "
            f"references {openai!r} do not match canonical skills/simplify-med/"
            f"SKILL.md's {canonical!r} (same set, same order expected)",
        )


class TestOpenAiSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.text = _read(OPENAI_SKILL_MD)
        self.frontmatter = _parse_frontmatter(self.text)

    def test_frontmatter_has_exactly_name_and_description(self):
        keys = set(self.frontmatter["__order__"])
        self.assertEqual(keys, {"name", "description"})

    def test_frontmatter_name_is_simplify_med(self):
        self.assertEqual(self.frontmatter["name"], "simplify-med")


class TestOpenAiSkillIsSelfContained(unittest.TestCase):
    """No hook/dispatch indirection: no custom_start.md/custom_end.md, no
    agents/ dispatch, no render-tool call (D3)."""

    def setUp(self):
        self.text = _read(OPENAI_SKILL_MD)

    def test_contains_none_of_the_forbidden_substrings(self):
        for needle in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(
                needle, self.text, f"OpenAI SKILL.md unexpectedly contains {needle!r}"
            )

    def test_contains_no_mcp_reference(self):
        # Case-sensitive: lowercase "mcp" can appear incidentally (e.g. inside
        # another word); the forbidden token is the literal "MCP" acronym.
        self.assertNotIn("MCP", self.text, "OpenAI SKILL.md unexpectedly contains 'MCP'")


class TestOpenAiSkillReferencesExist(unittest.TestCase):
    """Every script and stage file the OpenAI orchestrator names must
    actually exist under the canonical skills/simplify-med/ tree (it has
    no scripts/stages of its own -- it only reads the shared ones)."""

    def setUp(self):
        self.text = _read(OPENAI_SKILL_MD)

    def test_every_mentioned_script_exists(self):
        mentioned = _extract_matches(self.text, SCRIPT_RE)
        self.assertTrue(mentioned, "OpenAI SKILL.md should mention at least one script")
        for name in mentioned:
            path = os.path.join(SCRIPTS_DIR, name)
            self.assertTrue(
                os.path.isfile(path),
                f"OpenAI SKILL.md mentions scripts/{name}, which does not exist under "
                "skills/simplify-med/scripts/",
            )

    def test_every_mentioned_stage_file_exists(self):
        mentioned = _extract_matches(self.text, STAGE_RE)
        self.assertTrue(mentioned, "OpenAI SKILL.md should mention at least one stage file")
        for name in mentioned:
            path = os.path.join(STAGES_DIR, name)
            self.assertTrue(
                os.path.isfile(path),
                f"OpenAI SKILL.md mentions stages/{name}, which does not exist under "
                "skills/simplify-med/stages/",
            )


if __name__ == "__main__":
    unittest.main()
