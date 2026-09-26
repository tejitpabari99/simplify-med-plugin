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

EXPECTED_STAGE_FILES = {
    "assemble.md", "glossary.md", "ground.md", "review.md",
}
EXPECTED_SCRIPT_FILES = {
    "_version.py", "anchor_check.py", "cite_check.py", "finalize.py",
    "glossary_check.py", "merge_facts.py", "numeric_parity.py",
    "plan_view.py", "readability.py", "render_audit.py", "render_html.py",
    "render_md.py", "runlog.py", "settle_review.py", "textnorm.py",
    "unitize.py", "validate.py",
}
EXPECTED_SCHEMA_FILES = {
    "care_plan.schema.json", "care_plan_agent.schema.json",
    "facts.schema.json", "facts_raw.schema.json", "flags.schema.json",
    "glossary.schema.json", "glossary_raw.schema.json",
    "review.schema.json", "review_raw.schema.json", "run.schema.json",
    "units.schema.json",
}
OBSOLETE_PIPELINE_FILES = {
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
}


def _run_build(out_dir: str, repo_root: str, dev: bool = False) -> subprocess.CompletedProcess:
    command = [sys.executable, os.path.join(repo_root, "build.py"), "--out", out_dir]
    if dev:
        command.append("--dev")
    return subprocess.run(command, capture_output=True, text=True)


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as file:
        return file.read()


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


def _read_archive_json(archive: zipfile.ZipFile, root: str, relative: str) -> dict:
    return json.loads(archive.read(f"{root}/{relative}"))


class TestOpenAiPluginBuild(unittest.TestCase):
    def test_prod_build_increments_and_synchronizes_versions(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            skill_path = os.path.join(repo_copy, "skills", "simplify", "SKILL.md")
            with open(skill_path, "rb") as file:
                skill_before = file.read()

            result = _run_build(out_dir, repo_copy)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            zip_path = os.path.join(out_dir, "simplify-med-0.1.1-openai.zip")
            self.assertTrue(os.path.isfile(zip_path))

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                relative_names = {
                    name.removeprefix("simplify-med/")
                    for name in names
                    if not name.endswith("/")
                }
                portable = _read_archive_json(archive, "simplify-med", "plugin.json")
                compatibility = _read_archive_json(
                    archive, "simplify-med", ".codex-plugin/plugin.json"
                )
                pipeline_version = archive.read(
                    "simplify-med/skills/simplify/scripts/_version.py"
                ).decode("utf-8")
                blobs = {
                    name: archive.read(name)
                    for name in names
                    if not name.endswith((".png", ".jpg", ".jpeg", ".gif"))
                }

            self.assertEqual(portable["name"], "simplify-med")
            self.assertEqual(portable["version"], "0.1.1")
            self.assertEqual(compatibility["name"], "simplify-med")
            self.assertEqual(compatibility["version"], "0.1.1")
            self.assertIn('PLUGIN_VERSION = "0.1.1"', pipeline_version)
            self.assertEqual(_read_json(os.path.join(repo_copy, "build-versions.json")), {
                "prod": "0.1.1",
                "dev": "0.1.3",
            })
            self.assertEqual(_read_json(os.path.join(repo_copy, "plugin.json"))["version"], "0.1.1")
            self.assertEqual(
                _read_json(os.path.join(repo_copy, ".codex-plugin", "plugin.json"))["version"],
                "0.1.1",
            )
            with open(os.path.join(repo_copy, "skills", "simplify", "scripts", "_version.py"), encoding="utf-8") as file:
                self.assertIn('PLUGIN_VERSION = "0.1.1"', file.read())
            with open(skill_path, "rb") as file:
                self.assertEqual(file.read(), skill_before)

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
                if name.startswith("skills/simplify/scripts/")
            },
            EXPECTED_SCRIPT_FILES,
        )
        self.assertEqual(
            {
                os.path.basename(name) for name in relative_names
                if name.startswith("skills/simplify/schema/")
            },
            EXPECTED_SCHEMA_FILES,
        )
        self.assertTrue(OBSOLETE_PIPELINE_FILES.isdisjoint(relative_names))
        for required in (
            "skills/simplify/stages/review.md",
            "skills/simplify/scripts/settle_review.py",
            "skills/simplify/schema/review.schema.json",
            "skills/simplify/schema/review_raw.schema.json",
        ):
            self.assertIn(required, relative_names)

    def test_dev_build_increments_and_stamps_both_packaged_manifests(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            source_paths = (
                "plugin.json",
                os.path.join(".codex-plugin", "plugin.json"),
                os.path.join("skills", "simplify", "scripts", "_version.py"),
            )
            source_before = {
                relative: _read_bytes(os.path.join(repo_copy, relative))
                for relative in source_paths
            }

            result = _run_build(out_dir, repo_copy, dev=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            zip_path = os.path.join(out_dir, "simplify-med-dev-0.1.4-openai.zip")
            self.assertTrue(os.path.isfile(zip_path))

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                portable = _read_archive_json(archive, "simplify-med-dev", "plugin.json")
                compatibility = _read_archive_json(
                    archive, "simplify-med-dev", ".codex-plugin/plugin.json"
                )
                pipeline_version = archive.read(
                    "simplify-med-dev/skills/simplify/scripts/_version.py"
                ).decode("utf-8")

            self.assertEqual(portable["name"], "simplify-med-dev")
            self.assertEqual(portable["version"], "0.1.4")
            self.assertEqual(
                portable["extensions"]["com.openai"]["interface"]["displayName"],
                "Simplify Med Dev",
            )
            self.assertEqual(compatibility["name"], "simplify-med-dev")
            self.assertEqual(compatibility["version"], "0.1.4")
            self.assertEqual(compatibility["interface"]["displayName"], "Simplify Med Dev")
            self.assertIn('PLUGIN_VERSION = "0.1.4"', pipeline_version)
            self.assertNotIn("simplify-med-dev/build-versions.json", names)
            self.assertFalse(any("/mcp/" in f"/{name}" for name in names))
            self.assertEqual(_read_json(os.path.join(repo_copy, "build-versions.json")), {
                "prod": "0.1.0",
                "dev": "0.1.4",
            })
            for relative, content in source_before.items():
                with open(os.path.join(repo_copy, relative), "rb") as file:
                    self.assertEqual(file.read(), content)

    def test_prod_and_dev_counters_increment_independently(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            self.assertEqual(_run_build(out_dir, repo_copy, dev=True).returncode, 0)
            self.assertEqual(_run_build(out_dir, repo_copy, dev=True).returncode, 0)
            self.assertEqual(_run_build(out_dir, repo_copy).returncode, 0)
            self.assertEqual(_run_build(out_dir, repo_copy).returncode, 0)

            self.assertTrue(os.path.isfile(os.path.join(out_dir, "simplify-med-dev-0.1.4-openai.zip")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "simplify-med-dev-0.1.5-openai.zip")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "simplify-med-0.1.1-openai.zip")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "simplify-med-0.1.2-openai.zip")))
            self.assertEqual(_read_json(os.path.join(repo_copy, "build-versions.json")), {
                "prod": "0.1.2",
                "dev": "0.1.5",
            })

    def test_mcp_source_is_retained_but_not_declared_by_plugin_configs(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "mcp", "openai", "mcp.json")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "app.json")))
        for relative in ("plugin.json", os.path.join(".codex-plugin", "plugin.json")):
            manifest = _read_json(os.path.join(ROOT, relative))
            serialized = json.dumps(manifest).lower()
            self.assertNotIn("mcp", serialized)
            self.assertNotIn("streamable_http", serialized)

    def test_rejects_compatibility_version_mismatch_without_incrementing(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            path = os.path.join(repo_copy, ".codex-plugin", "plugin.json")
            manifest = _read_json(path)
            manifest["version"] = "9.9.9"
            with open(path, "w", encoding="utf-8") as file:
                json.dump(manifest, file)
            versions_before = _read_json(os.path.join(repo_copy, "build-versions.json"))
            result = _run_build(out_dir, repo_copy)
            versions_after = _read_json(os.path.join(repo_copy, "build-versions.json"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version mismatch", result.stderr)
        self.assertEqual(versions_after, versions_before)

    def test_rejects_pipeline_version_mismatch(self):
        with tempfile.TemporaryDirectory() as repo_copy, tempfile.TemporaryDirectory() as out_dir:
            _copy_build_inputs(repo_copy)
            path = os.path.join(repo_copy, "skills", "simplify", "scripts", "_version.py")
            with open(path, "w", encoding="utf-8") as file:
                file.write('PLUGIN_VERSION = "9.9.9"\nSCHEMA_VERSION = "1.0"\n')
            result = _run_build(out_dir, repo_copy, dev=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
