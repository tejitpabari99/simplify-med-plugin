import json
import hashlib
import os
import re
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


def _frontmatter_name(text: str) -> str:
    """Extract the `name:` field from a `---`-delimited frontmatter block
    at the top of a SKILL.md file's contents."""
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file does not start with a frontmatter block"
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("frontmatter has no 'name' field")


def _skill_digest():
    digest = hashlib.sha256()
    root = os.path.join(_paths.REPO_ROOT, "skills", "simplify")
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
                skill_md = zf.read("simplify-med/skills/simplify/SKILL.md").decode()

            self.assertIn("simplify-med/skills/simplify/schema/care_plan.schema.json", names)
            self.assertIn("simplify-med/.claude-plugin/plugin.json", names)
            self.assertTrue(any(n.startswith("simplify-med/README.md") for n in names))
            self.assertIn("simplify-med/skills/simplify/custom_start.md", names)
            self.assertIn("simplify-med/skills/simplify/custom_end.md", names)
            # The skill's own declared name must match its containing
            # directory (skills/simplify/), per the Agent Skills spec.
            self.assertEqual(_frontmatter_name(skill_md), "simplify")

            for n in names:
                self.assertFalse(n.startswith("simplify-med/docs/"), n)
                self.assertFalse(n.startswith("simplify-med/tests/"), n)
                self.assertFalse(n.startswith("simplify-med/dist/"), n)
                self.assertFalse(n.startswith("simplify-med/packaging/"), n)
                self.assertFalse(n.startswith("simplify-med/mcp/"), n)
                self.assertNotIn("__pycache__", n)


class TestBuildClaudeAi(unittest.TestCase):
    def test_builds_zip_rooted_at_skill_name(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "claude-ai", "--out", out_dir])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zips = [f for f in os.listdir(out_dir) if f.endswith(".zip")]
            self.assertEqual(len(zips), 1)
            zip_path = os.path.join(out_dir, zips[0])
            # The zip FILENAME still uses the plugin name.
            self.assertTrue(os.path.basename(zip_path).startswith("simplify-med-"))
            self.assertTrue(zip_path.endswith("-claude-ai.zip"))

            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                skill_md = zf.read("simplify/SKILL.md").decode()

            # A claude.ai skill upload is a standalone skill, and the Agent
            # Skills spec requires the skill's declared `name` to match its
            # containing folder -- so the archive's top-level folder must be
            # "simplify" (the skill name), not "simplify-med" (the plugin
            # name).
            self.assertTrue(names, "zip is empty")
            for n in names:
                self.assertTrue(n.startswith("simplify/"), n)
            self.assertIn("simplify/SKILL.md", names)
            self.assertEqual(_frontmatter_name(skill_md), "simplify")

            self.assertIn("simplify/schema/care_plan.schema.json", names)
            self.assertIn("simplify/scripts/validate.py", names)
            self.assertIn("simplify/custom_start.md", names)
            self.assertIn("simplify/custom_end.md", names)

            for n in names:
                self.assertFalse(n.startswith("simplify/docs/"), n)
                self.assertFalse(n.startswith("simplify/tests/"), n)
                self.assertFalse(n.startswith("simplify/agents/"), n)
                self.assertFalse(n.startswith("simplify/.claude-plugin/"), n)
                self.assertNotEqual(n, "simplify/plugin.meta.json")
                self.assertNotEqual(n, "simplify/README.md")
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
                compat_plugin = json.loads(
                    zf.read("simplify-med/.codex-plugin/plugin.json")
                )
                staged_mcp = zf.read("simplify-med/mcp.json")
                staged_compat_mcp = zf.read("simplify-med/.mcp.json")
                yaml = zf.read(
                    "simplify-med/skills/simplify/agents/openai.yaml"
                ).decode()
                custom_end = zf.read(
                    "simplify-med/skills/simplify/custom_end.md"
                ).decode()
                skill_md = zf.read("simplify-med/skills/simplify/SKILL.md").decode()

            self.assertEqual(plugin["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
            self.assertEqual(plugin["name"], "simplify-med")
            self.assertEqual(plugin["version"], "0.1.0")
            interface = plugin["extensions"]["com.openai"]["interface"]
            self.assertEqual(interface["displayName"], "Simplify Med")
            self.assertIn("shortDescription", interface)
            self.assertEqual(interface["category"], "Productivity")
            self.assertEqual(interface["capabilities"], ["Interactive", "Write"])
            self.assertTrue(interface["defaultPrompt"])
            self.assertNotIn("skills", plugin)
            self.assertEqual(compat_plugin["name"], plugin["name"])
            self.assertEqual(compat_plugin["version"], plugin["version"])
            self.assertEqual(compat_plugin["interface"], interface)
            self.assertEqual(compat_plugin["skills"], "./skills/")
            self.assertEqual(compat_plugin["mcpServers"], "./.mcp.json")
            with open(os.path.join(_paths.REPO_ROOT, "mcp", "openai", "mcp.json"), "rb") as f:
                self.assertEqual(staged_mcp, f.read())
            compat_mcp = json.loads(staged_compat_mcp)
            self.assertNotIn("$schema", compat_mcp)
            self.assertEqual(compat_mcp["mcpServers"], json.loads(staged_mcp)["mcpServers"])
            self.assertIn("url: https://PLUGIN_DOMAIN.example/mcp", yaml)
            self.assertIn("render_simplify_med_report", custom_end)
            self.assertIn("06_plan.final.json", custom_end)
            self.assertIn("simplify-med/skills/simplify/schema/care_plan.schema.json", names)
            self.assertNotIn("simplify-med/agents/ground.md", names)
            # The skill's own declared name must match its containing
            # directory (skills/simplify/), per the Agent Skills spec.
            self.assertEqual(_frontmatter_name(skill_md), "simplify")
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
                staged_compat_mcp = json.loads(zf.read("simplify-med/.mcp.json"))
                yaml = zf.read("simplify-med/skills/simplify/agents/openai.yaml").decode()
        self.assertEqual(
            staged_mcp["mcpServers"]["simplify-med-ui"]["url"],
            "https://mcp.simplify-med.dev/mcp",
        )
        self.assertNotIn("$schema", staged_compat_mcp)
        self.assertEqual(staged_compat_mcp["mcpServers"], staged_mcp["mcpServers"])
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


    def test_no_mcp_build_omits_all_mcp_connection_info(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "openai", "--out", out_dir, "--no-mcp"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zip_path = os.path.join(out_dir, "simplify-med-noui-0.1.0-openai.zip")
            self.assertTrue(zip_path.endswith("-openai.zip"))
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                compat_plugin = json.loads(
                    zf.read("simplify-med-noui/.codex-plugin/plugin.json")
                )
                yaml_text = zf.read(
                    "simplify-med-noui/skills/simplify/agents/openai.yaml"
                ).decode()
                staged_skill_md = zf.read(
                    "simplify-med-noui/skills/simplify/SKILL.md"
                ).decode()
                all_text_blobs = []
                for name in names:
                    if name.endswith((".png", ".ico", ".gif", ".jpg", ".jpeg")):
                        continue
                    try:
                        all_text_blobs.append(zf.read(name).decode())
                    except UnicodeDecodeError:
                        continue

            # No root or compatibility MCP declaration is staged at all, and no
            # root (portable-format) plugin.json is shipped for the skills-only
            # build (D2).
            self.assertTrue(names)
            self.assertTrue(all(name.startswith("simplify-med-noui/") for name in names))
            self.assertNotIn("simplify-med-noui/mcp.json", names)
            self.assertNotIn("simplify-med-noui/.mcp.json", names)
            self.assertNotIn("simplify-med-noui/plugin.json", names)

            # No custom_start.md/custom_end.md hand-off files are staged either
            # (D1/D3): the overlay SKILL.md is fully self-contained.
            self.assertNotIn("simplify-med-noui/skills/simplify/custom_start.md", names)
            self.assertNotIn("simplify-med-noui/skills/simplify/custom_end.md", names)

            # The compatibility manifest keeps its other keys but drops mcpServers
            # and trims capabilities to the non-interactive set (D2).
            self.assertNotIn("mcpServers", compat_plugin)
            self.assertEqual(compat_plugin["skills"], "./skills/")
            self.assertEqual(compat_plugin["name"], "simplify-med-noui")
            self.assertEqual(
                compat_plugin["interface"]["displayName"], "simplify-med-noUI"
            )
            self.assertEqual(
                compat_plugin["interface"]["capabilities"], ["Read", "Write"]
            )

            # The skill's agent file keeps interface/policy but drops the MCP tool
            # dependency entirely.
            self.assertIn("interface:", yaml_text)
            self.assertIn("policy:", yaml_text)
            self.assertNotIn("dependencies:", yaml_text)
            self.assertNotIn("type: mcp", yaml_text)
            self.assertNotIn("transport: streamable_http", yaml_text)

            # The staged SKILL.md is the OpenAI-specific overlay, not the
            # canonical file staged verbatim, and contains none of the
            # hand-off/dispatch/render-tool references the canonical file uses.
            canonical_skill_md_path = os.path.join(
                _paths.REPO_ROOT, "skills", "simplify", "SKILL.md"
            )
            with open(canonical_skill_md_path, "r", encoding="utf-8") as f:
                canonical_skill_md = f.read()
            self.assertNotEqual(staged_skill_md, canonical_skill_md)

            # The skill's own declared name must still match its containing
            # directory (skills/simplify/), per the Agent Skills spec.
            self.assertEqual(_frontmatter_name(staged_skill_md), "simplify")
            for forbidden in (
                "agents/",
                "custom_start.md",
                "custom_end.md",
                "render_simplify_med_report",
            ):
                self.assertNotIn(forbidden, staged_skill_md)

            # No stray endpoint token, mcpServers key, or example/ngrok URL survives
            # anywhere in the archive.
            for blob in all_text_blobs:
                self.assertNotIn("__SIMPLIFY_MED_MCP_URL__", blob)
                self.assertNotIn("mcpServers", blob)
                self.assertNotIn("ngrok", blob)
                self.assertNotIn("PLUGIN_DOMAIN.example", blob)

    def test_no_mcp_rejects_mcp_url(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--no-mcp", "--mcp-url", "https://mcp.simplify-med.dev/mcp",
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--no-mcp", result.stderr)
        self.assertIn("--mcp-url", result.stderr)

    def test_no_mcp_with_release_still_builds(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir, "--no-mcp", "--release",
            ])
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_app_id_stages_app_manifest_and_no_mcp_traces(self):
        app_id = "plugin_asdk_app_6ab74031b9608191b6aa67d0ac5c1e55"
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir, "--app-id", app_id,
            ])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zip_path = os.path.join(out_dir, "simplify-med-0.1.0-openai-no-mcp.zip")
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                app_manifest = json.loads(zf.read("simplify-med/.app.json"))
                compat_plugin = json.loads(
                    zf.read("simplify-med/.codex-plugin/plugin.json")
                )
                yaml_text = zf.read(
                    "simplify-med/skills/simplify/agents/openai.yaml"
                ).decode()
                all_text_blobs = []
                for name in names:
                    if name.endswith((".png", ".ico", ".gif", ".jpg", ".jpeg")):
                        continue
                    try:
                        all_text_blobs.append(zf.read(name).decode())
                    except UnicodeDecodeError:
                        continue

            # No MCP connection info at all, same as --no-mcp.
            self.assertNotIn("simplify-med/mcp.json", names)
            self.assertNotIn("simplify-med/.mcp.json", names)
            self.assertNotIn("mcpServers", compat_plugin)
            self.assertNotIn("dependencies:", yaml_text)

            # `.app.json` content matches the documented mechanism.
            self.assertEqual(
                app_manifest,
                {"apps": {"simplify-med-ui": {"id": app_id}}},
            )

            # The staged compat manifest points at it.
            self.assertEqual(compat_plugin["apps"], "./.app.json")

            for blob in all_text_blobs:
                self.assertNotIn("__SIMPLIFY_MED_MCP_URL__", blob)
                self.assertNotIn("ngrok", blob)
                self.assertNotIn("PLUGIN_DOMAIN.example", blob)

    def test_app_id_rejects_invalid_format(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--app-id", "not-a-valid-id",
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--app-id must match", result.stderr)

    def test_app_id_rejects_mcp_url_combination(self):
        app_id = "plugin_asdk_app_6ab74031b9608191b6aa67d0ac5c1e55"
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--app-id", app_id, "--mcp-url", "https://mcp.simplify-med.dev/mcp",
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--app-id", result.stderr)
        self.assertIn("--mcp-url", result.stderr)

    def test_app_id_rejects_non_openai_platform(self):
        app_id = "plugin_asdk_app_6ab74031b9608191b6aa67d0ac5c1e55"
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "claude-code", "--out", out_dir, "--app-id", app_id,
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--app-id applies only to the OpenAI build", result.stderr)

    def test_app_id_rejects_no_mcp_combination(self):
        app_id = "plugin_asdk_app_6ab74031b9608191b6aa67d0ac5c1e55"
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build([
                "--platform", "openai", "--out", out_dir,
                "--app-id", app_id, "--no-mcp",
            ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--app-id", result.stderr)
        self.assertIn("--no-mcp", result.stderr)

    def test_icons_exist_at_referenced_paths_and_interfaces_match(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "openai", "--out", out_dir])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zip_path = os.path.join(out_dir, "simplify-med-0.1.0-openai.zip")
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                plugin = json.loads(zf.read("simplify-med/plugin.json"))
                compat_plugin = json.loads(zf.read("simplify-med/.codex-plugin/plugin.json"))
                yaml_text = zf.read(
                    "simplify-med/skills/simplify/agents/openai.yaml"
                ).decode()

            interface = plugin["extensions"]["com.openai"]["interface"]

            # Root plugin.json and the .codex-plugin compatibility manifest must expose
            # byte-for-byte identical `interface` objects, including the icon fields, so
            # the two ingestion paths never present different metadata/artwork.
            self.assertEqual(compat_plugin["interface"], interface)

            # `interface.logo` / `interface.composerIcon` are resolved relative to the
            # plugin root by the Codex ingestion validator; the referenced files must
            # exist at that exact staged path inside the zip.
            for field in ("logo", "composerIcon"):
                self.assertIn(field, interface, f"interface.{field} is not set")
                relative = interface[field].removeprefix("./")
                self.assertIn(
                    f"simplify-med/{relative}",
                    names,
                    f"interface.{field}={interface[field]!r} has no staged file",
                )

            # `agents/openai.yaml` icon_small/icon_large are resolved relative to the
            # *skill* directory (skills/simplify/), not the plugin root -- extract
            # the declared paths and confirm each resolves to a real staged entry there.
            skill_prefix = "simplify-med/skills/simplify/"
            for key in ("icon_small", "icon_large"):
                match = re.search(rf"^\s*{key}:\s*(\S+)\s*$", yaml_text, re.MULTILINE)
                self.assertIsNotNone(match, f"{key} missing from staged openai.yaml")
                relative = match.group(1).strip().removeprefix("./")
                self.assertIn(
                    f"{skill_prefix}{relative}",
                    names,
                    f"agents/openai.yaml {key}={match.group(1)!r} has no staged file",
                )

    def test_icons_exist_at_referenced_paths_no_mcp(self):
        # No root plugin.json exists in the skills-only build (D2), so icon
        # paths must resolve purely from `.codex-plugin/plugin.json` (plugin
        # root icons) and the skill's `agents/openai.yaml` (skill-relative
        # icons) -- there is no cross-manifest interface comparison to make.
        with tempfile.TemporaryDirectory() as out_dir:
            result = _run_build(["--platform", "openai", "--out", out_dir, "--no-mcp"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            zip_path = os.path.join(out_dir, "simplify-med-noui-0.1.0-openai.zip")
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                self.assertNotIn("simplify-med-noui/plugin.json", names)
                compat_plugin = json.loads(
                    zf.read("simplify-med-noui/.codex-plugin/plugin.json")
                )
                yaml_text = zf.read(
                    "simplify-med-noui/skills/simplify/agents/openai.yaml"
                ).decode()

            interface = compat_plugin["interface"]

            # `interface.logo` / `interface.composerIcon` are resolved relative to
            # the plugin root; the referenced files must exist at that exact
            # staged path inside the zip.
            for field in ("logo", "composerIcon"):
                self.assertIn(field, interface, f"interface.{field} is not set")
                relative = interface[field].removeprefix("./")
                self.assertIn(
                    f"simplify-med-noui/{relative}",
                    names,
                    f"interface.{field}={interface[field]!r} has no staged file",
                )

            # `agents/openai.yaml` icon_small/icon_large are resolved relative to
            # the *skill* directory (skills/simplify/).
            skill_prefix = "simplify-med-noui/skills/simplify/"
            for key in ("icon_small", "icon_large"):
                match = re.search(rf"^\s*{key}:\s*(\S+)\s*$", yaml_text, re.MULTILINE)
                self.assertIsNotNone(match, f"{key} missing from staged openai.yaml")
                relative = match.group(1).strip().removeprefix("./")
                self.assertIn(
                    f"{skill_prefix}{relative}",
                    names,
                    f"agents/openai.yaml {key}={match.group(1)!r} has no staged file",
                )


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
                    self.assertEqual(zf.read("simplify/custom_end.md"), b"platform override\n")


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

            version_py_path = os.path.join(repo_copy, "skills", "simplify", "scripts", "_version.py")
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
