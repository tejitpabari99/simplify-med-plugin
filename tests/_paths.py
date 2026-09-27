"""Shared path helpers for tests.

The skills run no code, so the tests only read files: they never import
anything from `skills/`.
"""

import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "simplify")
SCHEMA_DIR = os.path.join(SKILL_DIR, "schema")
STAGES_DIR = os.path.join(SKILL_DIR, "stages")
REFERENCE_DIR = os.path.join(SKILL_DIR, "reference")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
FIXTURE_DOCUMENTS_DIR = os.path.join(FIXTURES_DIR, "documents")
BUILD_PY = os.path.join(REPO_ROOT, "build.py")
