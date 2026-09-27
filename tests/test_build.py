from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

ROOT = _paths.REPO_ROOT
BUILD = os.path.join(ROOT, "build.py")

EXPECTED_STAGE_FILES = {"verify.md", "write.md"}
EXPECTED_SCHEMA_FILES = {"plan.schema.json"}
EXPECTED_REFERENCE_FILES = {"abbreviations.json", "style_rules.md"}
OBSOLETE_PIPELINE_FILES = {
    "skills/simplify/stages/assemble.md",
    "skills/simplify/stages/ground.md",
    "skills/simplify/stages/review.md",
    "skills/simplify/reference/categories.md",
    "skills/simplify/scripts/anchor_check.py",
    "skills/simplify/scripts/cite_check.py",
    "skills/simplify/scripts/merge_facts.py",
    "skills/simplify/scripts/numeric_parity.py",
    "skills/simplify/scripts/settle_review.py",
    "skills/simplify/schema/care_plan.schema.json",
    "skills/simplify/schema/care_plan_agent.schema.json",
    "skills/simplify/schema/facts.schema.json",
    "skills/simplify/schema/facts_raw.schema.json",
    "skills/simplify/schema/flags.schema.json",
    "skills/simplify/schema/review.schema.json",
    "skills/simplify/schema/review_raw.schema.json",
    "skills/simplify/stages/assemble_missing.md",
    "skills/simplify/stages/correct.md",
    "skills/simplify/stages/review_coverage.md",
    "skills/simplify/stages/review_fidelity.md",
    "skills/simplify/scripts/diff_guard.py",
    "skills/simplify/scripts/sanitize_review.py",
    "skills/simplify/schema/additions.schema.json",
    "skills/simplify/schema/additions_raw.schema.json",
    "skills/simplify/schema/coverage.schema.json",
    "skills/simplify/schema/coverage_raw.schema.json",
    "skills/simplify/schema/manifest.schema.json",
    "skills/simplify/stages/glossary.md",
    "skills/simplify/reference/ahrq_plain_language.json",
    "skills/simplify/templates/report.html",
    "skills/simplify/scripts/_version.py",
    "skills/simplify/scripts/check_draft.py",
    "skills/simplify/scripts/finalize.py",
    "skills/simplify/scripts/glossary_check.py",
    "skills/simplify/scripts/numtokens.py",
    "skills/simplify/scripts/plan_paths.py",
    "skills/simplify/scripts/plan_view.py",
    "skills/simplify/scripts/protected.py",
    "skills/simplify/scripts/readability.py",
    "skills/simplify/scripts/render_audit.py",
    "skills/simplify/scripts/render_html.py",
    "skills/simplify/scripts/render_md.py",
    "skills/simplify/scripts/runlog.py",
    "skills/simplify/scripts/settle.py",
    "skills/simplify/scripts/textnorm.py",
    "skills/simplify/scripts/unitize.py",
    "skills/simplify/scripts/validate.py",
    "skills/simplify/schema/check.schema.json",
    "skills/simplify/schema/draft.schema.json",
    "skills/simplify/schema/draft_checked.schema.json",
    "skills/simplify/schema/glossary.schema.json",
    "skills/simplify/schema/glossary_raw.schema.json",
    "skills/simplify/schema/protected.schema.json",
    "skills/simplify/schema/run.schema.json",
    "skills/simplify/schema/units.schema.json",
    "skills/simplify/schema/verify.schema.json",
    "skills/simplify/schema/verify_raw.schema.json",
}


def _run_build(out_dir: str, repo_root: str, dev: bool = False) -> subprocess.CompletedProcess:
    command = [sys.executable, os.path.join(repo_root, "build.py"), "--out", out_dir]
    if dev:
        command.append("--dev")
    return subprocess.run(command, capture_output=True, text=True)


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)



def _copy_build_inputs(destination: str) -> None:
    shutil.copy2(BUILD, os.path.join(destination, "build.py"))
    shutil.copy2(os.path.join(ROOT, "build-versions.json"), os.path.join(destination, "build-versions.json"))
    shutil.copy2(os.path.join(ROOT, "plugin.json"), os.path.join(destination, "plugin.json"))
    shutil.copytree(os.path.join(ROOT, ".codex-plugin"), os.path.join(destination, ".codex-plugin"))
    shutil.copytree(
        os.path.join(ROOT, "skills"),
        os.path.join(destination, "skills"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


class TestOpenAiPluginBuild(unittest.TestCase):
    def test_package_contains_only_manifests_and_current_skills(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            result = _run_build(out_dir, repo_copy)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            zips = [name for name in os.listdir(out_dir) if name.endswith("-openai.zip")]
            self.assertEqual(len(zips), 1)

            with zipfile.ZipFile(os.path.join(out_dir, zips[0])) as archive:
                names = set(archive.namelist())
                blobs = {
                    name: archive.read(name)
                    for name in names
                    if not name.endswith((".png", ".jpg", ".jpeg", ".gif"))
                }

        relative_names = {
            name.removeprefix("simplify-med/")
            for name in names
            if not name.endswith("/")
        }
        self.assertIn("simplify-med/plugin.json", names)
        self.assertIn("simplify-med/.codex-plugin/plugin.json", names)
        self.assertIn("simplify-med/skills/simplify/SKILL.md", names)
        self.assertIn("simplify-med/skills/prep/SKILL.md", names)
        self.assertIn("simplify-med/skills/med-lit/SKILL.md", names)
        self.assertNotIn("simplify-med/build-versions.json", names)
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
        for excluded in ("mcp/", "packaging/", "tests/", "docs/", "agent_files/", "agents/"):
            self.assertFalse(any(name.startswith(f"simplify-med/{excluded}") for name in names))
        for content in blobs.values():
            text = content.decode("utf-8")
            self.assertNotIn("mcpServers", text)
            self.assertNotIn("type: mcp", text)
            self.assertNotIn("streamable_http", text)
        self.assertEqual(
            {
                os.path.basename(name) for name in relative_names
                if name.startswith("skills/simplify/stages/")
            },
            EXPECTED_STAGE_FILES,
        )
        self.assertEqual(
            {
                os.path.basename(name) for name in relative_names
                if name.startswith("skills/simplify/schema/")
            },
            EXPECTED_SCHEMA_FILES,
        )
        self.assertEqual(
            {
                os.path.basename(name) for name in relative_names
                if name.startswith("skills/simplify/reference/")
            },
            EXPECTED_REFERENCE_FILES,
        )
        self.assertFalse(any(name.startswith("skills/simplify/scripts/") for name in relative_names))
        self.assertFalse(any(name.startswith("skills/simplify/templates/") for name in relative_names))
        self.assertFalse(any(name.endswith(".py") for name in names))
        self.assertTrue(OBSOLETE_PIPELINE_FILES.isdisjoint(relative_names))
        for required in (
            "skills/simplify/stages/write.md",
            "skills/simplify/stages/verify.md",
            "skills/simplify/reference/style_rules.md",
            "skills/simplify/schema/plan.schema.json",
            "skills/simplify/agents/openai.yaml",
        ):
            self.assertIn(required, relative_names)

    def test_simplify_source_tree_has_no_scripts_or_templates(self):
        simplify = os.path.join(ROOT, "skills", "simplify")
        self.assertFalse(os.path.exists(os.path.join(simplify, "scripts")))
        self.assertFalse(os.path.exists(os.path.join(simplify, "templates")))
        for relative in OBSOLETE_PIPELINE_FILES:
            self.assertFalse(os.path.exists(os.path.join(ROOT, relative)), msg=relative)
        with open(BUILD, encoding="utf-8") as file:
            build_source = file.read()
        self.assertNotIn("scripts", build_source)

    def test_mcp_source_is_retained_but_not_declared_by_plugin_configs(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "mcp", "openai", "mcp.json")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "app.json")))
        for relative in ("plugin.json", os.path.join(".codex-plugin", "plugin.json")):
            manifest = _read_json(os.path.join(ROOT, relative))
            serialized = json.dumps(manifest).lower()
            self.assertNotIn("mcp", serialized)
            self.assertNotIn("streamable_http", serialized)


if __name__ == "__main__":
    unittest.main()
