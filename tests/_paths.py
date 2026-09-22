"""Shared path helpers for tests.

Adds skills/simplify-med/scripts/ to sys.path so tests can `import
validate`, `import runlog`, etc. directly, and exposes the repo root and
other useful paths.
"""

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "skills", "simplify-med", "scripts")
SCHEMA_DIR = os.path.join(REPO_ROOT, "skills", "simplify-med", "schema")
PACKAGING_DIR = os.path.join(REPO_ROOT, "packaging")
BUILD_PY = os.path.join(PACKAGING_DIR, "build.py")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
