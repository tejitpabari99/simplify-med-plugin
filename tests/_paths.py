"""Shared path helpers for tests.

Adds skills/simplify/scripts/ to sys.path so tests can `import
validate`, `import runlog`, etc. directly, and exposes the repo root and
other useful paths.
"""

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "scripts")
SCHEMA_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "schema")
STAGES_DIR = os.path.join(REPO_ROOT, "skills", "simplify", "stages")
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "simplify")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
FIXTURE_DOCUMENTS_DIR = os.path.join(FIXTURES_DIR, "documents")
BUILD_PY = os.path.join(REPO_ROOT, "build.py")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
