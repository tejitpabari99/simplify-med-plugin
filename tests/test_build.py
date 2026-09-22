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


def _run_build(args, cwd=None):
    return subprocess.run(
        [sys.executable, _paths.BUILD_PY] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestBuildClaudeCode(unittest.TestCase):
    def test_builds_zip_with_wrapped_paths(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "claude-code", "--out", out_dir])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zips = [f for f in os.listdir(out_dir) if f.endswith(".zip")]
            self.assertEqual(len(zips), 1)
            zip_path = os.path.join(out_dir, zips[0])
            self.assertTrue(zip_path.endswith("-claude-code.zip"))

            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()

            self.assertIn("simplify-med/skills/simplify-med/schema/care_plan.schema.json", names)
            self.assertIn("simplify-med/.claude-plugin/plugin.json", names)
            self.assertTrue(any(n.startswith("simplify-med/README.md") for n in names))

            for n in names:
                self.assertFalse(n.startswith("simplify-med/docs/"), n)
                self.assertFalse(n.startswith("simplify-med/tests/"), n)
                self.assertFalse(n.startswith("simplify-med/dist/"), n)
                self.assertFalse(n.startswith("simplify-med/packaging/"), n)
                self.assertNotIn("__pycache__", n)


class TestBuildClaudeAi(unittest.TestCase):
    def test_builds_zip_rooted_at_skill_dir(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "claude-ai", "--out", out_dir])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zips = [f for f in os.listdir(out_dir) if f.endswith(".zip")]
            self.assertEqual(len(zips), 1)
            zip_path = os.path.join(out_dir, zips[0])
            self.assertTrue(zip_path.endswith("-claude-ai.zip"))

            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()

            self.assertIn("simplify-med/schema/care_plan.schema.json", names)
            self.assertIn("simplify-med/scripts/validate.py", names)

            for n in names:
                self.assertFalse(n.startswith("simplify-med/docs/"), n)
                self.assertFalse(n.startswith("simplify-med/tests/"), n)
                self.assertFalse(n.startswith("simplify-med/agents/"), n)
                self.assertFalse(n.startswith("simplify-med/.claude-plugin/"), n)
                self.assertNotEqual(n, "simplify-med/plugin.meta.json")
                self.assertNotEqual(n, "simplify-med/README.md")
                self.assertNotIn("__pycache__", n)


class TestBuildVersionMismatch(unittest.TestCase):
    def _copy_repo(self, dst):
        for name in ["plugin.meta.json", ".claude-plugin", "skills", "packaging"]:
            src = os.path.join(_paths.REPO_ROOT, name)
            dst_path = os.path.join(dst, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst_path, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, dst_path)

    def test_mismatched_manifest_version_exits_2(self):
        with tempfile.TemporaryDirectory() as repo_copy:
            self._copy_repo(repo_copy)

            manifest_path = os.path.join(repo_copy, ".claude-plugin", "plugin.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["version"] = "9.9.9"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)

            build_py = os.path.join(repo_copy, "packaging", "build.py")
            with tempfile.TemporaryDirectory() as out_dir:
                result = subprocess.run(
                    [sys.executable, build_py, "--platform", "claude-code", "--out", out_dir],
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Version mismatch", result.stderr)

    def test_mismatched_version_py_exits_2(self):
        with tempfile.TemporaryDirectory() as repo_copy:
            self._copy_repo(repo_copy)

            version_py_path = os.path.join(repo_copy, "skills", "simplify-med", "scripts", "_version.py")
            with open(version_py_path, "w", encoding="utf-8") as f:
                f.write('PLUGIN_VERSION = "9.9.9"\nSCHEMA_VERSION = "1.0"\n')

            build_py = os.path.join(repo_copy, "packaging", "build.py")
            with tempfile.TemporaryDirectory() as out_dir:
                result = subprocess.run(
                    [sys.executable, build_py, "--platform", "claude-code", "--out", out_dir],
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Version mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
