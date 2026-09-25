#!/usr/bin/env python3
"""Build the Claude Code package through the shared staged builder."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402

if __name__ == "__main__":
    sys.exit(build.main(["--platform", "claude-code", *sys.argv[1:]]))
