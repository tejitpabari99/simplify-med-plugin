#!/usr/bin/env python3
"""Build staged, platform-specific simplify-med archives.

The historical ``python3 packaging/build.py --platform ...`` CLI remains
supported. All overlays are applied to a temporary copy, never the source skill.
"""

from __future__ import annotations

import argparse
import fnmatch
import ipaddress
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from urllib.parse import urlsplit

_PACKAGING_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PACKAGING_DIR)
_URL_TOKEN = "__SIMPLIFY_MED_MCP_URL__"
_DEVELOPMENT_PLACEHOLDER = "https://PLUGIN_DOMAIN.example/mcp"
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_RESERVED_SUFFIXES = (".localhost", ".local", ".test", ".example", ".invalid", ".onion")
_EXAMPLE_DOMAINS = ("example.com", "example.net", "example.org")

PLATFORMS = {
    "claude-code": {
        "ignore_file": os.path.join("claude-code", "claude-code.ignore"),
        "walk_root": ".",
        "layout": "repository",
    },
    "claude-ai": {
        "ignore_file": os.path.join("claude-ai", "claude-ai.ignore"),
        "walk_root": os.path.join("skills", "simplify-med"),
        "layout": "skill",
    },
    "openai": {
        "ignore_file": os.path.join("openai", "openai.ignore"),
        "walk_root": os.path.join("skills", "simplify-med"),
        "layout": "openai",
    },
}


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_meta(repo_root: str = _REPO_ROOT) -> dict:
    return _read_json(os.path.join(repo_root, "plugin.meta.json"))


def load_manifest(repo_root: str = _REPO_ROOT) -> dict:
    return _read_json(os.path.join(repo_root, ".claude-plugin", "plugin.json"))


def load_version_constant(repo_root: str = _REPO_ROOT) -> str:
    path = os.path.join(repo_root, "skills", "simplify-med", "scripts", "_version.py")
    namespace: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, path, "exec"), namespace)
    return namespace["PLUGIN_VERSION"]


def check_versions(repo_root: str = _REPO_ROOT) -> str:
    meta = load_meta(repo_root)
    manifest = load_manifest(repo_root)
    version_py = load_version_constant(repo_root)
    meta_version = meta.get("version")
    manifest_version = manifest.get("version")
    if meta_version != manifest_version:
        print(
            "Version mismatch: plugin.meta.json version="
            f"{meta_version!r} vs .claude-plugin/plugin.json version={manifest_version!r}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if meta_version != version_py:
        print(
            "Version mismatch: plugin.meta.json version="
            f"{meta_version!r} vs skills/simplify-med/scripts/_version.py "
            f"PLUGIN_VERSION={version_py!r}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    openai_manifest = os.path.join(repo_root, "packaging", "openai", "plugin.json")
    if os.path.isfile(openai_manifest):
        openai_version = _read_json(openai_manifest).get("version")
        if openai_version != meta_version:
            print(
                "Version mismatch: plugin.meta.json version="
                f"{meta_version!r} vs packaging/openai/plugin.json version={openai_version!r}",
                file=sys.stderr,
            )
            raise SystemExit(2)

    openai_compat_manifest = os.path.join(
        repo_root, "packaging", "openai", ".codex-plugin", "plugin.json"
    )
    if os.path.isfile(openai_compat_manifest):
        compat_version = _read_json(openai_compat_manifest).get("version")
        if compat_version != meta_version:
            print(
                "Version mismatch: plugin.meta.json version="
                f"{meta_version!r} vs packaging/openai/.codex-plugin/plugin.json "
                f"version={compat_version!r}",
                file=sys.stderr,
            )
            raise SystemExit(2)
    return meta_version


def parse_ignore_file(path: str) -> list[tuple[str, bool, bool]]:
    patterns: list[tuple[str, bool, bool]] = []
    if not os.path.isfile(path):
        return patterns
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            anchored = line.startswith("/")
            if anchored:
                line = line[1:]
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            if line:
                patterns.append((line, anchored, dir_only))
    return patterns


def _matches_one(rel_path, basename, is_dir, pattern, anchored, dir_only):
    if dir_only and not is_dir:
        return False
    if anchored:
        return fnmatch.fnmatch(rel_path, pattern)
    return fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(rel_path, pattern)


def is_ignored(rel_path, is_dir, patterns):
    rel_path = rel_path.replace(os.sep, "/")
    basename = rel_path.rsplit("/", 1)[-1]
    return any(_matches_one(rel_path, basename, is_dir, *entry) for entry in patterns)


def iter_included_files(repo_root: str, walk_root: str, patterns):
    abs_walk_root = repo_root if walk_root == "." else os.path.join(repo_root, walk_root)
    for dirpath, dirnames, filenames in os.walk(abs_walk_root):
        rel_dir = os.path.relpath(dirpath, repo_root)
        dirnames[:] = [
            name
            for name in dirnames
            if not is_ignored(name if rel_dir == "." else f"{rel_dir}/{name}", True, patterns)
        ]
        for filename in filenames:
            rel_path = filename if rel_dir == "." else f"{rel_dir}/{filename}"
            if not is_ignored(rel_path, False, patterns):
                yield os.path.join(dirpath, filename)


def _copy_files(files, source_root: str, destination: str) -> None:
    for source in files:
        target = os.path.join(destination, os.path.relpath(source, source_root))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def _copy_default_custom_files(repo_root: str, skill_destination: str) -> None:
    defaults = os.path.join(repo_root, "packaging", "default")
    for filename in ("custom_start.md", "custom_end.md"):
        source = os.path.join(defaults, filename)
        if not os.path.isfile(source):
            raise SystemExit(f"Missing default platform hook: {source}")
        os.makedirs(skill_destination, exist_ok=True)
        shutil.copy2(source, os.path.join(skill_destination, filename))


def _copy_if_present(source: str, destination: str) -> None:
    if not os.path.exists(source):
        return
    if os.path.isdir(source):
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)


def _source_endpoint(repo_root: str) -> tuple[dict, str]:
    path = os.path.join(repo_root, "mcp", "openai", "mcp.json")
    if not os.path.isfile(path):
        raise SystemExit("Missing OpenAI MCP declaration: mcp/openai/mcp.json")
    document = _read_json(path)
    try:
        endpoint = document["mcpServers"]["simplify-med-ui"]["url"]
    except (KeyError, TypeError):
        raise SystemExit("mcp/openai/mcp.json must declare mcpServers.simplify-med-ui.url")
    if not isinstance(endpoint, str):
        raise SystemExit("The Simplify Med MCP endpoint must be a string")
    return document, endpoint


def _endpoint_error(endpoint: str, release: bool) -> str | None:
    """Return a reason when an MCP endpoint is unsafe or malformed.

    Developer builds allow HTTP only on literal loopback hosts. Release builds
    additionally require HTTPS and a syntactically public, non-reserved host.
    DNS is deliberately not queried during a deterministic package build.
    """
    if endpoint == _DEVELOPMENT_PLACEHOLDER:
        return (
            "must use a public, non-local, non-reserved host for a release build"
            if release
            else None
        )
    if not isinstance(endpoint, str) or not endpoint or endpoint != endpoint.strip():
        return "must be a non-empty URL without surrounding whitespace"
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port  # Force validation of a malformed/out-of-range port.
    except ValueError:
        return "contains an invalid host or port"
    if parsed.scheme not in {"http", "https"}:
        return "must use HTTP or HTTPS"
    if not parsed.hostname:
        return "must include a host"
    if parsed.username is not None or parsed.password is not None:
        return "must not contain credentials"
    if parsed.query or parsed.fragment:
        return "must not contain a query string or fragment"
    if parsed.path != "/mcp":
        return "must use the exact /mcp route"
    if port is not None and not 1 <= port <= 65535:
        return "contains an invalid port"

    host = parsed.hostname.lower()
    if host.endswith(".") or "%" in host:
        return "contains an invalid host"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return "contains an invalid host"
        labels = ascii_host.split(".")
        if any(not _DNS_LABEL.fullmatch(label) for label in labels):
            return "contains an invalid host"
        is_loopback = ascii_host == "localhost" or ascii_host.endswith(".localhost")
        is_public_host = (
            len(labels) >= 2
            and not is_loopback
            and not any(ascii_host.endswith(suffix) for suffix in _RESERVED_SUFFIXES)
            and not any(
                ascii_host == domain or ascii_host.endswith(f".{domain}")
                for domain in _EXAMPLE_DOMAINS
            )
        )
    else:
        is_loopback = address.is_loopback
        is_public_host = address.is_global

    if parsed.scheme == "http" and not is_loopback:
        return "may use HTTP only with a loopback host for development"
    if release:
        if parsed.scheme != "https":
            return "must use HTTPS for a release build"
        if not is_public_host:
            return "must use a public, non-local, non-reserved host for a release build"
    return None


def _strip_yaml_top_level_key(text: str, key: str) -> str:
    """Remove a top-level ``key:`` block (the key line plus its indented body).

    Deliberately not a general YAML parser: the build is stdlib-only, so this
    walks lines and removes the matching top-level key together with every
    following line that is blank or indented, stopping at the next
    non-indented line or end of file.
    """
    lines = text.splitlines(keepends=True)
    key_prefix = f"{key}:"
    out = []
    i = 0
    removed = False
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")
        if not removed and (stripped == key_prefix or stripped.startswith(key_prefix + " ")):
            removed = True
            i += 1
            while i < len(lines):
                candidate = lines[i]
                candidate_stripped = candidate.rstrip("\n")
                if candidate_stripped == "" or candidate[0] in (" ", "\t"):
                    i += 1
                    continue
                break
            continue
        out.append(line)
        i += 1
    if not removed:
        raise SystemExit(f"Expected top-level key {key!r} not found while staging openai.yaml")
    return "".join(out)


_NO_MCP_FORBIDDEN_STRINGS = (
    _URL_TOKEN,
    "ngrok",
    "PLUGIN_DOMAIN.example",
    "mcpServers",
    "render_simplify_med_report",
)
_APP_ID_RE = re.compile(r"^plugin_asdk_app_[0-9a-f]{32}$")


def _assert_no_mcp_traces(plugin_stage: str) -> None:
    """Guard for --no-mcp (and --app-id, which implies --no-mcp) builds: no

    endpoint token, mcpServers key, or example/ngrok URL may survive anywhere
    in the staged tree. A staged ``.app.json`` (EXPERIMENTAL ``--app-id``
    reference to an existing ChatGPT dev-mode app) is explicitly allowed --
    it never contains a URL, token, or mcpServers key, so no separate
    exemption logic is required here; this function still walks every staged
    file, including ``.app.json``, and simply finds nothing forbidden in it.
    """
    for dirpath, _, filenames in os.walk(plugin_stage):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for needle in _NO_MCP_FORBIDDEN_STRINGS:
                if needle in content:
                    rel = os.path.relpath(path, plugin_stage)
                    raise SystemExit(
                        f"--no-mcp build must not contain {needle!r}; found in {rel}"
                    )


def _stage_openai(
    repo_root, plugin_stage, patterns, endpoint_override, release, include_mcp=True, app_id=None
):
    skill_source = os.path.join(repo_root, "skills", "simplify-med")
    skill_destination = os.path.join(plugin_stage, "skills", "simplify-med")
    files = sorted(iter_included_files(repo_root, os.path.join("skills", "simplify-med"), patterns))
    _copy_files(files, skill_source, skill_destination)
    if include_mcp:
        _copy_default_custom_files(repo_root, skill_destination)

    overlay = os.path.join(repo_root, "packaging", "openai")
    if include_mcp:
        for filename in ("custom_start.md", "custom_end.md"):
            _copy_if_present(
                os.path.join(overlay, filename), os.path.join(skill_destination, filename)
            )
    _copy_if_present(os.path.join(overlay, "agents"), os.path.join(skill_destination, "agents"))
    _copy_if_present(os.path.join(overlay, "assets"), os.path.join(plugin_stage, "assets"))
    _copy_if_present(
        os.path.join(overlay, "skill-assets"),
        os.path.join(skill_destination, "assets"),
    )
    _copy_if_present(
        os.path.join(overlay, ".codex-plugin"),
        os.path.join(plugin_stage, ".codex-plugin"),
    )
    if include_mcp:
        shutil.copy2(
            os.path.join(overlay, "plugin.json"), os.path.join(plugin_stage, "plugin.json")
        )

    yaml_path = os.path.join(skill_destination, "agents", "openai.yaml")

    if not include_mcp:
        # No MCP connection info is staged at all: the owner will add the
        # connector manually in ChatGPT. Strip the compatibility manifest's
        # mcpServers pointer (write a modified copy of the staged file, never
        # the packaging source) and drop the MCP tool dependency from the
        # staged skill's agent file, keeping interface/policy intact.
        compat_manifest_path = os.path.join(plugin_stage, ".codex-plugin", "plugin.json")
        compat_manifest = _read_json(compat_manifest_path)
        compat_manifest["interface"]["capabilities"] = ["Read", "Write"]
        compat_manifest.pop("mcpServers", None)
        if app_id:
            # EXPERIMENTAL: reference an existing ChatGPT dev-mode app by ID
            # instead of shipping an MCP endpoint. Documented mechanism per
            # developers.openai.com/plugins/build/plugins and the Codex
            # plugin-creator spec: a companion ``.app.json`` at the plugin
            # root, pointed to from the manifest's ``apps`` field.
            compat_manifest["apps"] = "./.app.json"
        with open(compat_manifest_path, "w", encoding="utf-8") as f:
            json.dump(compat_manifest, f, indent=2)
            f.write("\n")

        with open(yaml_path, "r", encoding="utf-8") as f:
            template = f.read()
        stripped = _strip_yaml_top_level_key(template, "dependencies")
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(stripped)

        if app_id:
            app_manifest_path = os.path.join(plugin_stage, ".app.json")
            app_document = {
                "apps": {
                    "simplify-med-ui": {
                        "id": app_id,
                    }
                }
            }
            with open(app_manifest_path, "w", encoding="utf-8") as f:
                json.dump(app_document, f, indent=2)
                f.write("\n")

        no_mcp_skill_md = os.path.join(overlay, "skills", "simplify-med", "SKILL.md")
        if not os.path.isfile(no_mcp_skill_md):
            raise SystemExit(
                "Missing OpenAI skills-only SKILL.md: "
                "packaging/openai/skills/simplify-med/SKILL.md"
            )
        shutil.copy2(no_mcp_skill_md, os.path.join(skill_destination, "SKILL.md"))

        _assert_no_mcp_traces(plugin_stage)
        return

    mcp_document, configured_endpoint = _source_endpoint(repo_root)
    endpoint = endpoint_override or configured_endpoint
    endpoint_error = _endpoint_error(endpoint, release)
    if endpoint_error:
        kind = "Release OpenAI MCP endpoint" if release else "OpenAI MCP endpoint"
        raise SystemExit(f"{kind} {endpoint_error}")
    mcp_target = os.path.join(plugin_stage, "mcp.json")
    if endpoint_override:
        mcp_document["mcpServers"]["simplify-med-ui"]["url"] = endpoint
        with open(mcp_target, "w", encoding="utf-8") as f:
            json.dump(mcp_document, f, indent=2)
            f.write("\n")
    else:
        shutil.copy2(os.path.join(repo_root, "mcp", "openai", "mcp.json"), mcp_target)
    compat_mcp_target = os.path.join(plugin_stage, ".mcp.json")
    with open(compat_mcp_target, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": mcp_document["mcpServers"]}, f, indent=2)
        f.write("\n")

    with open(yaml_path, "r", encoding="utf-8") as f:
        template = f.read()
    if template.count(_URL_TOKEN) != 1:
        raise SystemExit("packaging/openai/agents/openai.yaml must contain one endpoint token")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(template.replace(_URL_TOKEN, endpoint))


def _stage_platform(platform, repo_root, plugin_stage, mcp_url, release, include_mcp=True, app_id=None):
    config = PLATFORMS[platform]
    patterns = parse_ignore_file(os.path.join(repo_root, "packaging", config["ignore_file"]))
    if config["layout"] == "openai":
        _stage_openai(repo_root, plugin_stage, patterns, mcp_url, release, include_mcp, app_id)
        return
    if mcp_url or release:
        raise SystemExit("--mcp-url and --release apply only to the OpenAI build")
    if not include_mcp:
        raise SystemExit("--no-mcp applies only to the OpenAI build")

    walk_root = config["walk_root"]
    source_root = repo_root if walk_root == "." else os.path.join(repo_root, walk_root)
    _copy_files(sorted(iter_included_files(repo_root, walk_root, patterns)), source_root, plugin_stage)
    skill_destination = (
        os.path.join(plugin_stage, "skills", "simplify-med")
        if config["layout"] == "repository"
        else plugin_stage
    )
    _copy_default_custom_files(repo_root, skill_destination)
    overlay = os.path.join(repo_root, "packaging", platform)
    for filename in ("custom_start.md", "custom_end.md"):
        _copy_if_present(os.path.join(overlay, filename), os.path.join(skill_destination, filename))


def build(
    platform,
    out_dir="dist",
    repo_root=_REPO_ROOT,
    mcp_url=None,
    release=False,
    no_mcp: bool = False,
    app_id=None,
):
    if platform not in PLATFORMS:
        print(f"Unknown platform {platform!r}; choose from {sorted(PLATFORMS)}", file=sys.stderr)
        raise SystemExit(2)
    if app_id is not None:
        # EXPERIMENTAL: --app-id references an existing ChatGPT dev-mode app
        # by ID instead of shipping an MCP endpoint. OpenAI platform only; it
        # implies the --no-mcp staging path (reused below) and cannot be
        # combined with an MCP endpoint override.
        if platform != "openai":
            raise SystemExit("--app-id applies only to the OpenAI build")
        if mcp_url:
            raise SystemExit("--app-id cannot be combined with --mcp-url")
        if not _APP_ID_RE.fullmatch(app_id):
            raise SystemExit(
                "--app-id must match ^plugin_asdk_app_[0-9a-f]{32}$ "
                f"(32 lowercase hex characters after the prefix); got {app_id!r}"
            )
        if no_mcp:
            raise SystemExit("--app-id cannot be combined with --no-mcp")
        no_mcp = True  # --app-id implies no-mcp staging, same as today
    include_mcp = not no_mcp
    if not include_mcp and mcp_url:
        raise SystemExit("--no-mcp cannot be combined with --mcp-url")
    version = check_versions(repo_root)
    plugin_name = load_meta(repo_root)["name"]
    out_dir_abs = out_dir if os.path.isabs(out_dir) else os.path.join(repo_root, out_dir)
    os.makedirs(out_dir_abs, exist_ok=True)
    zip_path = os.path.join(out_dir_abs, f"{plugin_name}-{version}-{platform}.zip")

    with tempfile.TemporaryDirectory(prefix="simplify-med-build-") as temp_dir:
        plugin_stage = os.path.join(temp_dir, plugin_name)
        os.makedirs(plugin_stage)
        _stage_platform(platform, repo_root, plugin_stage, mcp_url, release, include_mcp, app_id)
        staged_files = sorted(
            os.path.join(dirpath, filename)
            for dirpath, _, filenames in os.walk(plugin_stage)
            for filename in filenames
        )
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for source in staged_files:
                relative = os.path.relpath(source, plugin_stage).replace(os.sep, "/")
                zf.write(source, f"{plugin_name}/{relative}")

    print(zip_path)
    print(f"{len(staged_files)} entries")
    return zip_path, len(staged_files)


def _build_arg_parser():
    parser = argparse.ArgumentParser(description="Build a simplify-med plugin package")
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--out", default="dist", help="Output directory (default: dist)")
    parser.add_argument("--mcp-url", default=None, help="Override the staged OpenAI MCP endpoint")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Require a public HTTPS /mcp endpoint for an OpenAI build",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help=(
            "Exclude all MCP connection info from the OpenAI package "
            "(the connector is added manually in ChatGPT); cannot be combined with --mcp-url"
        ),
    )
    parser.add_argument(
        "--app-id",
        default=None,
        help=(
            "EXPERIMENTAL: reference an existing ChatGPT dev-mode app by ID "
            "(plugin_asdk_app_<32 lowercase hex chars>) instead of shipping an MCP "
            "endpoint. OpenAI platform only; implies --no-mcp staging; cannot be "
            "combined with --mcp-url"
        ),
    )
    return parser


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    build(
        args.platform,
        args.out,
        mcp_url=args.mcp_url,
        release=args.release,
        no_mcp=args.no_mcp,
        app_id=args.app_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
