import json
import hashlib
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


def _skill_digest():
    digest = hashlib.sha256()
    root = os.path.join(_paths.REPO_ROOT, "skills", "simplify-med")
    for dirpath, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            digest.update(os.path.relpath(path, root).encode())
            with open(path, "rb") as f:
                digest.update(f.read())
    return digest.hexdigest()


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
            self.assertIn("simplify-med/skills/simplify-med/custom_start.md", names)
            self.assertIn("simplify-med/skills/simplify-med/custom_end.md", names)

            for n in names:
                self.assertFalse(n.startswith("simplify-med/docs/"), n)
                self.assertFalse(n.startswith("simplify-med/tests/"), n)
                self.assertFalse(n.startswith("simplify-med/dist/"), n)
                self.assertFalse(n.startswith("simplify-med/packaging/"), n)
                self.assertFalse(n.startswith("simplify-med/mcp/"), n)
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
            self.assertIn("simplify-med/custom_start.md", names)
            self.assertIn("simplify-med/custom_end.md", names)

            for n in names:
                self.assertFalse(n.startswith("simplify-med/docs/"), n)
                self.assertFalse(n.startswith("simplify-med/tests/"), n)
                self.assertFalse(n.startswith("simplify-med/agents/"), n)
                self.assertFalse(n.startswith("simplify-med/.claude-plugin/"), n)
                self.assertNotEqual(n, "simplify-med/plugin.meta.json")
                self.assertNotEqual(n, "simplify-med/README.md")
                self.assertNotIn("__pycache__", n)


class TestBuildOpenAi(unittest.TestCase):
    def test_archive_layout_content_and_exclusions(self):
        before = _skill_digest()
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "openai", "--out", out_dir])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(before, _skill_digest(), "build mutated the source skill")

            zip_path = os.path.join(out_dir, "simplify-med-0.1.0-openai.zip")
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                plugin = json.loads(zf.read("simplify-med/plugin.json"))
                staged_mcp = zf.read("simplify-med/mcp.json")
                yaml = zf.read(
                    "simplify-med/skills/simplify-med/agents/openai.yaml"
                ).decode()
                custom_end = zf.read(
                    "simplify-med/skills/simplify-med/custom_end.md"
                ).decode()

            self.assertEqual(plugin["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
            self.assertEqual(plugin["name"], "simplify-med")
            self.assertEqual(plugin["version"], "0.1.0")
            interface = plugin["extensions"]["com.openai"]["interface"]
            self.assertEqual(interface["displayName"], "Simplify Med")
            self.assertIn("shortDescription", interface)
            self.assertNotIn("skills", plugin)
            with open(os.path.join(_paths.REPO_ROOT, "mcp", "openai", "mcp.json"), "rb") as f:
                self.assertEqual(staged_mcp, f.read())
            self.assertIn("url: https://PLUGIN_DOMAIN.example/mcp", yaml)
            self.assertIn("render_simplify_med_report", custom_end)
            self.assertIn("06_plan.final.json", custom_end)
            self.assertIn("simplify-med/skills/simplify-med/schema/care_plan.schema.json", names)
            self.assertNotIn("simplify-med/agents/ground.md", names)
            self.assertFalse(any(name.startswith("simplify-med/mcp/openai/") for name in names))
            self.assertFalse(any(name.startswith("simplify-med/docs/") for name in names))
            self.assertFalse(any(name.startswith("simplify-med/tests/") for name in names))

    def test_endpoint_override_updates_mcp_and_yaml_only_in_archive(self):
        source_path = os.path.join(_paths.REPO_ROOT, "mcp", "openai", "mcp.json")
        with open(source_path, "rb") as f:
            source_before = f.read()
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--mcp-url", "https://mcp.simplify-med.dev/mcp", "--release",
            ])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            with zipfile.ZipFile(os.path.join(out_dir, "simplify-med-0.1.0-openai.zip")) as zf:
                staged_mcp = json.loads(zf.read("simplify-med/mcp.json"))
                yaml = zf.read("simplify-med/skills/simplify-med/agents/openai.yaml").decode()
        self.assertEqual(
            staged_mcp["mcpServers"]["simplify-med-ui"]["url"],
            "https://mcp.simplify-med.dev/mcp",
        )
        self.assertIn("url: https://mcp.simplify-med.dev/mcp", yaml)
        with open(source_path, "rb") as f:
            self.assertEqual(source_before, f.read())

    def test_release_rejects_placeholder_endpoint(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "openai", "--out", out_dir, "--release"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-reserved host", result.stderr)

    def test_non_release_accepts_loopback_http_for_development(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--mcp-url", "http://127.0.0.1:3000/mcp",
            ])
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_non_release_rejects_insecure_non_loopback_http(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--mcp-url", "http://mcp.simplify-med.dev/mcp",
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP only with a loopback host", result.stderr)

    def test_release_rejects_non_public_or_malformed_endpoints(self):
        invalid_endpoints = [
            "http://localhost:3000/mcp",
            "https://localhost/mcp",
            "https://127.0.0.1/mcp",
            "https://[::1]/mcp",
            "https://10.0.0.1/mcp",
            "https://mcp.internal.local/mcp",
            "https://mcp.example.test/mcp",
            "https://mcp.plugin.example/mcp",
            "https://mcp.plugin.invalid/mcp",
            "https://viewer.example.com/mcp",
            "https://user:password@mcp.simplify-med.dev/mcp",
            "https://mcp.simplify-med.dev/not-mcp",
            "https://mcp.simplify-med.dev/mcp?token=secret",
            "https://mcp.simplify-med.dev/mcp#fragment",
            "https:///mcp",
            "not-a-url",
        ]
        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as out_dir:
                result = _run_build([
                    "--platform", "openai", "--out", out_dir,
                    "--mcp-url", endpoint, "--release",
                ])
                self.assertNotEqual(result.returncode, 0, msg=endpoint)
                self.assertIn("Release OpenAI MCP endpoint", result.stderr)


class TestBuildDispatcherAndOverlays(unittest.TestCase):
    def test_root_dispatcher_and_unknown_platform(self):
        root_build = os.path.join(_paths.REPO_ROOT, "build.py")
        with tempfile.TemporaryDirectory() as out_dir:
            good = subprocess.run(
                [sys.executable, root_build, "claude-ai", "--out", out_dir],
                capture_output=True,
                text=True,
            )
            bad = subprocess.run(
                [sys.executable, root_build, "unknown"], capture_output=True, text=True
            )
        self.assertEqual(good.returncode, 0, msg=good.stderr)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("invalid choice", bad.stderr)

    def test_defaults_are_blank_and_platform_override_wins(self):
        for filename in ("custom_start.md", "custom_end.md"):
            path = os.path.join(_paths.REPO_ROOT, "packaging", "default", filename)
            self.assertEqual(os.path.getsize(path), 0)

        with tempfile.TemporaryDirectory() as repo_copy:
            for name in ["plugin.meta.json", ".claude-plugin", "skills", "packaging"]:
                source = os.path.join(_paths.REPO_ROOT, name)
                target = os.path.join(repo_copy, name)
                if os.path.isdir(source):
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(source, target)
            override = os.path.join(repo_copy, "packaging", "claude-ai", "custom_end.md")
            with open(override, "w", encoding="utf-8") as f:
                f.write("platform override\n")
            build_py = os.path.join(repo_copy, "packaging", "build.py")
            with tempfile.TemporaryDirectory() as out_dir:
                result = subprocess.run(
                    [sys.executable, build_py, "--platform", "claude-ai", "--out", out_dir],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                with zipfile.ZipFile(os.path.join(out_dir, "simplify-med-0.1.0-claude-ai.zip")) as zf:
                    self.assertEqual(zf.read("simplify-med/custom_end.md"), b"platform override\n")


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
