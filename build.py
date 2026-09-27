#!/usr/bin/env python3
"""Build versioned production or development OpenAI plugin archives."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSIONS_FILE = "build-versions.json"
PORTABLE_MANIFEST = "plugin.json"
COMPATIBILITY_MANIFEST = os.path.join(".codex-plugin", "plugin.json")
INCLUDED_FILES = (PORTABLE_MANIFEST, COMPATIBILITY_MANIFEST)
INCLUDED_DIRECTORIES = ("skills",)
IGNORED_DIRECTORIES = {"__pycache__"}
IGNORED_SUFFIXES = (".pyc",)
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _read_bytes(relative: str) -> bytes:
    with open(os.path.join(ROOT, relative), "rb") as file:
        return file.read()


def _validate_version(label: str, version: object) -> str:
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise SystemExit(f"{VERSIONS_FILE} {label} version must use X.Y.Z")
    return version


def _bump_patch(version: str) -> str:
    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise SystemExit(f"cannot increment invalid version: {version}")
    major, minor, patch = (int(part) for part in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def _display_name(manifest: dict, dev: bool) -> None:
    if not dev:
        return
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        interface = manifest.get("extensions", {}).get("com.openai", {}).get("interface")
    if isinstance(interface, dict):
        display_name = interface.get("displayName")
        if isinstance(display_name, str) and not display_name.endswith(" Dev"):
            interface["displayName"] = f"{display_name} Dev"


def _build_metadata(dev: bool) -> tuple[str, str, dict, dict, dict]:
    portable = _read_json(os.path.join(ROOT, PORTABLE_MANIFEST))
    compatibility = _read_json(os.path.join(ROOT, COMPATIBILITY_MANIFEST))
    versions = _read_json(os.path.join(ROOT, VERSIONS_FILE))

    base_name = portable.get("name")
    if not isinstance(base_name, str) or not base_name:
        raise SystemExit("plugin.json must contain a non-empty name")
    if compatibility.get("name") != base_name:
        raise SystemExit("plugin name mismatch between plugin.json and .codex-plugin/plugin.json")

    prod_version = _validate_version("prod", versions.get("prod"))
    dev_version = _validate_version("dev", versions.get("dev"))
    if portable.get("version") != prod_version:
        raise SystemExit("production version mismatch between build-versions.json and plugin.json")
    if compatibility.get("version") != prod_version:
        raise SystemExit(
            "production version mismatch between build-versions.json and .codex-plugin/plugin.json"
        )

    current_version = dev_version if dev else prod_version
    next_version = _bump_patch(current_version)
    package_name = f"{base_name}-dev" if dev else base_name

    packaged_portable = copy.deepcopy(portable)
    packaged_compatibility = copy.deepcopy(compatibility)
    for manifest in (packaged_portable, packaged_compatibility):
        manifest["name"] = package_name
        manifest["version"] = next_version
        _display_name(manifest, dev)

    next_versions = dict(versions)
    next_versions["dev" if dev else "prod"] = next_version
    return package_name, next_version, packaged_portable, packaged_compatibility, next_versions


def _included_paths() -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for relative in INCLUDED_FILES:
        source = os.path.join(ROOT, relative)
        if not os.path.isfile(source):
            raise SystemExit(f"missing required plugin file: {relative}")
        paths.append((source, relative.replace(os.sep, "/")))

    for directory in INCLUDED_DIRECTORIES:
        source_root = os.path.join(ROOT, directory)
        if not os.path.isdir(source_root):
            raise SystemExit(f"missing required plugin directory: {directory}")
        for dirpath, dirnames, filenames in os.walk(source_root):
            dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRECTORIES)
            for filename in sorted(filenames):
                if filename.endswith(IGNORED_SUFFIXES):
                    continue
                source = os.path.join(dirpath, filename)
                relative = os.path.relpath(source, ROOT).replace(os.sep, "/")
                paths.append((source, relative))
    return sorted(paths, key=lambda item: item[1])


def _atomic_write(relative: str, content: bytes) -> None:
    path = os.path.join(ROOT, relative)
    temporary = f"{path}.tmp"
    with open(temporary, "wb") as file:
        file.write(content)
    os.replace(temporary, path)


def build(out_dir: str = "dist", dev: bool = False) -> str:
    package_name, version, portable, compatibility, versions = _build_metadata(dev)
    generated = {
        PORTABLE_MANIFEST.replace(os.sep, "/"): _json_bytes(portable),
        COMPATIBILITY_MANIFEST.replace(os.sep, "/"): _json_bytes(compatibility),
    }

    output_root = out_dir if os.path.isabs(out_dir) else os.path.join(ROOT, out_dir)
    os.makedirs(output_root, exist_ok=True)
    zip_path = os.path.join(output_root, f"{package_name}-{version}-openai.zip")
    temporary_zip = f"{zip_path}.tmp"
    included = _included_paths()

    try:
        with zipfile.ZipFile(temporary_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, relative in included:
                archive_path = f"{package_name}/{relative}"
                if relative in generated:
                    archive.writestr(archive_path, generated[relative])
                else:
                    archive.write(source, archive_path)

        originals = {VERSIONS_FILE: _read_bytes(VERSIONS_FILE)}
        updates = {VERSIONS_FILE: _json_bytes(versions)}
        if not dev:
            originals.update(
                {
                    PORTABLE_MANIFEST: _read_bytes(PORTABLE_MANIFEST),
                    COMPATIBILITY_MANIFEST: _read_bytes(COMPATIBILITY_MANIFEST),
                }
            )
            updates.update(
                {
                    PORTABLE_MANIFEST: generated[PORTABLE_MANIFEST],
                    COMPATIBILITY_MANIFEST: generated[COMPATIBILITY_MANIFEST.replace(os.sep, "/")],
                }
            )

        try:
            for relative, content in updates.items():
                _atomic_write(relative, content)
            os.replace(temporary_zip, zip_path)
        except Exception:
            for relative, content in originals.items():
                _atomic_write(relative, content)
            raise
    finally:
        if os.path.exists(temporary_zip):
            os.unlink(temporary_zip)

    channel = "dev" if dev else "prod"
    print(zip_path)
    print(f"{len(included)} entries | {channel} {version} | plugin {package_name}")
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the skills-only OpenAI plugin ZIP")
    parser.add_argument("--dev", action="store_true", help="Build and increment simplify-med-dev")
    parser.add_argument("--out", default="dist", help="Output directory (default: dist)")
    args = parser.parse_args(argv)
    build(args.out, dev=args.dev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
