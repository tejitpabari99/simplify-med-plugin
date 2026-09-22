#!/usr/bin/env python3
"""Build distributable zip packages for the simplify-med plugin.

Usage:
    python3 build.py --platform claude-code|claude-ai [--out dist]

Reads plugin.meta.json and .claude-plugin/plugin.json, verifies their
versions match each other and skills/simplify-med/scripts/_version.py's
PLUGIN_VERSION, then walks the repository applying a gitignore-style ignore
file for the chosen platform and writes a zip to <out>/.

Stdlib only. Runnable as ``python3 build.py ...`` from any cwd and
importable as ``build``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import zipfile

_PACKAGING_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PACKAGING_DIR)

# Maps platform name -> config. Add an entry here to support a new
# platform later; per-platform customization (extra excludes, a different
# archive layout, etc.) hangs off this dict rather than being hardcoded
# into the build logic below.
PLATFORMS = {
    "claude-code": {
        "ignore_file": "claude-code.ignore",
        # "." means: walk the whole repo root.
        "walk_root": ".",
    },
    "claude-ai": {
        "ignore_file": "claude-ai.ignore",
        # Only this subtree is included in the archive, regardless of the
        # ignore file's contents.
        "walk_root": os.path.join("skills", "simplify-med"),
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
    """Return PLUGIN_VERSION from skills/simplify-med/scripts/_version.py
    without importing it as a package (keeps this script standalone and
    import-order independent)."""
    path = os.path.join(repo_root, "skills", "simplify-med", "scripts", "_version.py")
    namespace: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, path, "exec"), namespace)
    return namespace["PLUGIN_VERSION"]


def check_versions(repo_root: str = _REPO_ROOT) -> str:
    """Verify plugin.meta.json, .claude-plugin/plugin.json, and _version.py
    all agree on the plugin version. Returns the version string on success;
    exits with status 2 (after printing an error) on any mismatch."""
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

    return meta_version


def parse_ignore_file(path: str) -> list[tuple[str, bool, bool]]:
    """Parse a gitignore-style ignore file.

    Returns a list of (pattern, anchored, dir_only) tuples:
      - anchored: pattern had a leading "/" and must match the full
        repo-root-relative path.
      - dir_only: pattern had a trailing "/" and only matches directories.
    """
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
            if not line:
                continue
            patterns.append((line, anchored, dir_only))
    return patterns


def _matches_one(rel_path: str, basename: str, is_dir: bool, pattern: str, anchored: bool, dir_only: bool) -> bool:
    if dir_only and not is_dir:
        return False
    if anchored:
        return fnmatch.fnmatch(rel_path, pattern)
    return fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(rel_path, pattern)


def is_ignored(rel_path: str, is_dir: bool, patterns: list[tuple[str, bool, bool]]) -> bool:
    rel_path = rel_path.replace(os.sep, "/")
    basename = rel_path.rsplit("/", 1)[-1]
    return any(_matches_one(rel_path, basename, is_dir, p, a, d) for p, a, d in patterns)


def iter_included_files(repo_root: str, walk_root: str, patterns: list[tuple[str, bool, bool]]):
    """Yield absolute paths of files under walk_root, skipping anything
    matched by `patterns` (evaluated as paths relative to repo_root, so
    anchoring behaves like a real repo-root-relative .gitignore)."""
    abs_walk_root = repo_root if walk_root == "." else os.path.join(repo_root, walk_root)
    for dirpath, dirnames, filenames in os.walk(abs_walk_root):
        rel_dir = os.path.relpath(dirpath, repo_root)

        kept_dirnames = []
        for d in dirnames:
            rel_d = d if rel_dir == "." else f"{rel_dir}/{d}"
            if is_ignored(rel_d, True, patterns):
                continue
            kept_dirnames.append(d)
        dirnames[:] = kept_dirnames

        for fname in filenames:
            rel_f = fname if rel_dir == "." else f"{rel_dir}/{fname}"
            if is_ignored(rel_f, False, patterns):
                continue
            yield os.path.join(dirpath, fname)


def build(platform: str, out_dir: str = "dist", repo_root: str = _REPO_ROOT) -> tuple[str, int]:
    if platform not in PLATFORMS:
        print(f"Unknown platform {platform!r}; choose from {sorted(PLATFORMS)}", file=sys.stderr)
        raise SystemExit(2)

    version = check_versions(repo_root)
    meta = load_meta(repo_root)
    plugin_name = meta["name"]

    config = PLATFORMS[platform]
    ignore_path = os.path.join(_PACKAGING_DIR, config["ignore_file"])
    # When repo_root differs from this file's own repo (e.g. a temp copy
    # used in tests), prefer that copy's own packaging/<ignore file> if it
    # exists, so the build reflects the copy being built, not this file.
    copy_ignore_path = os.path.join(repo_root, "packaging", config["ignore_file"])
    if os.path.isfile(copy_ignore_path):
        ignore_path = copy_ignore_path
    patterns = parse_ignore_file(ignore_path)

    walk_root = config["walk_root"]
    abs_walk_root = repo_root if walk_root == "." else os.path.join(repo_root, walk_root)

    out_dir_abs = out_dir if os.path.isabs(out_dir) else os.path.join(repo_root, out_dir)
    os.makedirs(out_dir_abs, exist_ok=True)
    zip_path = os.path.join(out_dir_abs, f"{plugin_name}-{version}-{platform}.zip")

    entry_count = 0
    files = sorted(iter_included_files(repo_root, walk_root, patterns))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path in files:
            rel_from_walk_root = os.path.relpath(abs_path, abs_walk_root).replace(os.sep, "/")
            arcname = f"{plugin_name}/{rel_from_walk_root}"
            zf.write(abs_path, arcname)
            entry_count += 1

    print(zip_path)
    print(f"{entry_count} entries")
    return zip_path, entry_count


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a simplify-med plugin package")
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--out", default="dist", help="Output directory (default: dist, relative to repo root)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    build(args.platform, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
