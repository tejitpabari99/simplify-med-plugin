#!/usr/bin/env python3
"""Convenience dispatcher for platform plugin builds."""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "packaging"))
import build as packaging_build  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a simplify-med package")
    parser.add_argument("platform", choices=sorted(packaging_build.PLATFORMS))
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
    args = parser.parse_args(argv)
    packaging_build.build(
        args.platform,
        args.out,
        repo_root=_ROOT,
        mcp_url=args.mcp_url,
        release=args.release,
        include_mcp=not args.no_mcp,
        app_id=args.app_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
