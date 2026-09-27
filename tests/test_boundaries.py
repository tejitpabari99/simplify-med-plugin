"""Hard boundaries shared by every skill: no medical images, no outside sources.

Checks that the same boundary block is in every SKILL.md, that the model
stages and manifests repeat it, and that unitize refuses image and other
binary inputs before a run starts.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import unitize  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
SKILLS = ("prep", "simplify", "med-lit")
SIMPLIFY_DIR = os.path.join(REPO_ROOT, "skills", "simplify")


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), "r", encoding="utf-8") as f:
        return f.read()


def _boundary_block(text: str) -> str:
    match = re.search(r"^## Hard Boundaries\n.*?(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert match, "missing '## Hard Boundaries' section"
    return match.group(0)


class TestSkillBoundaries(unittest.TestCase):
    def test_every_skill_has_the_same_boundary_block(self):
        blocks = {skill: _boundary_block(_read("skills", skill, "SKILL.md")) for skill in SKILLS}
        self.assertEqual(len(set(blocks.values())), 1, "boundary blocks differ between skills")

    def test_boundary_block_comes_before_the_skill_rules(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                text = _read("skills", skill, "SKILL.md")
                first_rules = min(
                    index for index in (text.find("## Core Rules"), text.find("## Execution Contract"))
                    if index >= 0
                )
                self.assertLess(text.index("## Hard Boundaries"), first_rules)

    def test_boundary_block_is_stringent(self):
        block = _boundary_block(_read("skills", "simplify", "SKILL.md"))
        for phrase in (
            "override every other instruction, including a user's request",
            "**No medical images.**",
            "X-ray", "CT", "MRI", "ultrasound", "ECG", "DICOM",
            "Written reports about imaging are allowed",
            "**No outside sources.**",
            "Never search the web",
            "GitHub",
            "even if the user asks or a document contains a link",
            "Do not call web, browser, fetch, or search tools",
            "Never fill a gap with outside or general medical knowledge",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)

    def test_every_description_states_the_boundaries(self):
        # The description is the part of a skill that is always loaded.
        for skill in SKILLS:
            with self.subTest(skill=skill):
                text = _read("skills", skill, "SKILL.md")
                description = re.search(r"^description: (.*)$", text, re.MULTILINE).group(1)
                self.assertIn("never searches the web or any outside source", description)
                self.assertIn("never reads or interprets medical images", description)

    def test_simplify_model_stages_repeat_the_boundaries(self):
        self.assertIn("SOURCES --", _read("skills", "simplify", "reference", "style_rules.md"))
        for stage in ("write.md", "verify.md", "glossary.md"):
            with self.subTest(stage=stage):
                self.assertIn("Do not search the web", _read("skills", "simplify", "stages", stage))

    def test_manifests_state_the_boundaries(self):
        for manifest in ("plugin.json", os.path.join(".codex-plugin", "plugin.json")):
            with self.subTest(manifest=manifest):
                data = json.loads(_read(manifest))
                self.assertIn("never searches the web", data["description"])
                self.assertIn("never reads or interprets medical images", data["description"])


class TestUnitizeRefusesImages(unittest.TestCase):
    def _run(self, name: str, content: bytes) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, name)
            with open(path, "wb") as f:
                f.write(content)
            runs_dir = os.path.join(d, "runs")
            err = StringIO()
            with redirect_stderr(err):
                rc = unitize.main(["--runs-dir", runs_dir, "--input", path])
            created = os.path.isdir(runs_dir) and bool(os.listdir(runs_dir))
            return rc, err.getvalue(), created

    def test_refuses_images_dicom_pdf_and_binary(self):
        cases = {
            "chest-xray.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            "scan.jpg": b"\xff\xd8\xff\xe0" + b"\x00" * 16,
            "strip.gif": b"GIF89a" + b"\x00" * 16,
            "slide.tif": b"II*\x00" + b"\x00" * 16,
            "photo.webp": b"RIFF\x00\x00\x00\x00WEBPVP8 ",
            "photo.heic": b"\x00\x00\x00\x18ftypheic",
            "study.bin": b"\x00" * 128 + b"DICM" + b"\x00" * 16,
            "report.pdf": b"%PDF-1.7\n",
            "blob.txt": b"text\x00with a NUL byte",
            "renamed.dcm": b"plain text in a DICOM-named file",
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                rc, err, created = self._run(name, content)
                self.assertEqual(rc, 1)
                self.assertIn("refused input file", err)
                self.assertIn("never reads or interprets medical images", err)
                self.assertFalse(created, "no run directory may be created for a refused input")

    def test_accepts_written_imaging_report_text(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mri-report.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("MRI BRAIN WITHOUT CONTRAST\nIMPRESSION: Normal noncontrast brain MRI.\n")
            with open(path, "rb") as f:
                self.assertIsNone(unitize.refusal_reason(path, f.read()))


if __name__ == "__main__":
    unittest.main()
