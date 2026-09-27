"""Regression guards for the model-facing Simplify stage contracts.

The stage prompts must stay in lockstep with the model schemas
(`draft.schema.json`, `verify_raw.schema.json`) and the shared visible-path
definition (`plan_paths.py`). These tests read the prompts and schemas; they
run no model.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  (adds scripts/ to sys.path)

import plan_paths  # noqa: E402
import validate  # noqa: E402

REPO_ROOT = _paths.REPO_ROOT
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "simplify")
REFERENCE_DIR = os.path.join(SKILL_DIR, "reference")
STAGES_DIR = os.path.join(SKILL_DIR, "stages")
SCHEMA_DIR = os.path.join(SKILL_DIR, "schema")

PROTECTED_CATEGORIES = (
    "medication_changes",
    "follow_up",
    "return_precautions",
    "diagnoses",
    "disposition",
    "abnormal_or_pending_results",
)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


def _schema(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, name), "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _schema_vocabulary(node) -> set[str]:
    """Every property name and string enum value anywhere in a schema."""
    words: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                words.update(value.keys())
            if key == "enum" and isinstance(value, list):
                words.update(v for v in value if isinstance(v, str))
            words |= _schema_vocabulary(value)
    elif isinstance(node, list):
        for item in node:
            words |= _schema_vocabulary(item)
    return words


def _json_blocks(text: str) -> list[str]:
    return re.findall(r"```json\n(.*?)\n[ \t]*```", text, re.DOTALL)


def _worked_example(text: str) -> dict:
    for block in _json_blocks(text):
        if block.lstrip().startswith("{") and '"visit_type"' in block:
            return json.loads(block)
    raise AssertionError("write.md has no worked-example draft JSON block")


class TestStageFiles(unittest.TestCase):
    def test_only_current_stage_documents_exist(self):
        present = sorted(name for name in os.listdir(STAGES_DIR) if name.endswith(".md"))
        self.assertEqual(present, ["glossary.md", "verify.md", "write.md"])


class TestWriteStage(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "write.md"))
        self.schema = _schema("draft.schema.json")

    def test_mentions_every_draft_top_level_key(self):
        for key in self.schema["required"]:
            self.assertIn(f"`{key}`", self.text, key)

    def test_mentions_every_protected_category(self):
        for category in PROTECTED_CATEGORIES:
            self.assertIn(category, self.text)
        self.assertIn("none_in_source", self.text)
        self.assertIn("01_protected.json", self.text)

    def test_names_inputs_outputs_and_modes(self):
        for name in ("01_source.txt", "reference/style_rules.md", "schema/draft.schema.json",
                     "02_draft.raw.json", "02_draft.r2.raw.json", "04_repair.json",
                     "## Retry mode", "## Repair mode"):
            self.assertIn(name, self.text)

    def test_teaches_citation_by_unit_id(self):
        self.assertIn("unit_ids", self.text)
        self.assertRegex(self.text, r"(?i)skipped")
        self.assertRegex(self.text, r"(?i)never invent\s+an id")

    def test_keeps_translate_dont_interpret_and_conclusion_wording(self):
        self.assertIn("Translate, don't interpret", self.text)
        self.assertIn("exact conclusion", self.text)

    def test_lists_anti_patterns_from_real_runs(self):
        lowered = self.text.lower()
        for phrase in ("lab inventory", "vital signs", "contrast", "no current outpatient medications",
                       "sub-finding", "ordering provider", "no past medical history", "superseded",
                       "plain_name"):
            self.assertIn(phrase, lowered, phrase)

    def test_worked_example_is_a_valid_draft_within_budget(self):
        example = _worked_example(self.text)
        self.assertEqual(validate.validate(example, self.schema), [])
        words = sum(len(text.split()) for _path, text, _ids in plan_paths.visible_strings(example))
        self.assertGreaterEqual(words, 150)
        self.assertLessEqual(words, 300)

    def test_worked_example_is_marked_shape_not_content(self):
        self.assertIn("shape, not content", self.text)
        self.assertIn("Do not\ncopy", self.text)


class TestVerifyStage(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "verify.md"))
        self.schema = _schema("verify_raw.schema.json")

    def test_mentions_every_verify_raw_key_and_enum(self):
        for word in sorted(_schema_vocabulary(self.schema)):
            self.assertIn(word, self.text, word)

    def test_lists_every_visible_item_path_form(self):
        for kind in plan_paths.TEXT_FIELDS:
            form = kind if kind in ("why_you_went", "findings_lead", "disposition",
                                    "medicines.none_statement") else f"{kind}[i]"
            self.assertIn(f"`{form}`", self.text, form)

    def test_lists_every_replaceable_and_clearable_path(self):
        for kind, fields in plan_paths.TEXT_FIELDS.items():
            indexed = kind if kind in ("why_you_went", "findings_lead", "disposition",
                                       "medicines.none_statement") else f"{kind}[i]"
            for field in fields:
                self.assertIn(f"`{indexed}.{field}`", self.text)
        for item in plan_paths.CLEARABLE_ITEMS:
            self.assertIn(f"`{item}`", self.text)
        self.assertIn("`diagnoses[i].plain_name`", self.text)

    def test_names_inputs_outputs_and_rounds(self):
        for name in ("01_source.txt", "02_draft.json", "02_draft.r2.json", "02_check.json",
                     "02_check.r2.json", "03_verify.raw.json", "03_verify.r2.raw.json",
                     "reference/style_rules.md", "schema/verify_raw.schema.json"):
            self.assertIn(name, self.text)

    def test_is_independent_bounded_and_budget_aware(self):
        self.assertIn("independent", self.text)
        self.assertIn("did not write the draft", self.text)
        self.assertIn("over_budget", self.text)
        self.assertIn("There is no `add` operation", self.text)
        self.assertIn("highest index", self.text)

    def test_example_operations_validate(self):
        operations = [
            json.loads(block) for block in _json_blocks(self.text)
            if block.lstrip().startswith('{"op"')
        ]
        self.assertEqual({op["op"] for op in operations}, {"replace", "clear", "remove"})
        item_schema = self.schema["properties"]["operations"]
        self.assertEqual(validate.validate(operations, dict(item_schema, definitions=self.schema["definitions"])), [])


class TestStyleRules(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(REFERENCE_DIR, "style_rules.md"))

    def test_keeps_pii_numeracy_language_and_adds_show_skip(self):
        for heading in ("PII --", "NUMERACY --", "LANGUAGE RULES --", "SHOW --", "SKIP --"):
            self.assertIn(heading, self.text)
        self.assertNotIn("CRITICAL VS SUPPORTING", self.text)

    def test_does_not_reference_the_fact_ledger(self):
        self.assertIsNone(re.search(r"(?i)\bfacts?\b|fact_id", self.text))


class TestOptionalGlossary(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "glossary.md"))

    def test_glossary_is_optional_post_finalization_enrichment(self):
        self.assertIn("optional post-finalization", self.text)
        self.assertIn("05_plan.final.json", self.text)
        self.assertIn("report.md", self.text)
        self.assertIn("patient-visible finalized content", self.text)
        self.assertIn("07_glossary.raw.json", self.text)
        self.assertIn("07_glossary.json", self.text)
        self.assertIn("no more than five terms", self.text)
        self.assertIn("must not change", self.text)

    def test_glossary_does_not_reference_retired_artifacts(self):
        self.assertNotIn("06_plan.final.json", self.text)
        self.assertIsNone(re.search(r"(?i)\bfacts?\b|omissions", self.text))


if __name__ == "__main__":
    unittest.main()
