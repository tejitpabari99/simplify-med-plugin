"""The one schema `simplify` ships: `schema/plan.schema.json` (contract C1).

The schema is used only when the user asks for structured output. These tests
check its shape and behavior with the small test-only validator in
`_minischema.py`; they do not depend on how the schema factors its
definitions.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _minischema  # noqa: E402
import _paths  # noqa: E402

PLAN_SCHEMA_PATH = os.path.join(_paths.SCHEMA_DIR, "plan.schema.json")

TOP_LEVEL_KEYS = [
    "schema_version",
    "visit_type",
    "why_you_went",
    "findings_lead",
    "findings",
    "diagnoses",
    "disposition",
    "next_steps",
    "medicines",
    "return_precautions",
    "questions",
    "must_keep",
]
VISIT_TYPES = ["er_visit", "urgent_care", "hospital_stay", "clinic_visit", "test_results", "procedure", "other"]
MEDICINE_CHANGES = ["start", "stop", "change", "continue", "instruction"]
MUST_KEEP = [
    "medication_changes",
    "follow_up",
    "return_precautions",
    "diagnoses",
    "disposition",
    "abnormal_or_pending_results",
]
RETIRED_KEYS = {"unit_ids", "run_id", "created_at", "plugin_version", "word_count", "score", "notices", "coverage"}


def _load() -> dict:
    with open(PLAN_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _statement(text: str = "You had a cough.") -> dict:
    return {"text": text, "evidence": ["cough for 5 days"]}


def _minimal() -> dict:
    return {
        "schema_version": "4.0",
        "visit_type": "urgent_care",
        "why_you_went": _statement(),
        "findings_lead": None,
        "findings": [],
        "diagnoses": [],
        "disposition": None,
        "next_steps": [],
        "medicines": {"items": [], "none_statement": None},
        "return_precautions": [],
        "questions": [],
        "must_keep": {key: "none_in_source" for key in MUST_KEEP},
    }


def _full() -> dict:
    plan = _minimal()
    plan.update({
        "findings_lead": _statement("The doctor found a lung infection."),
        "findings": [{"name": "Chest X-ray", "result": "Pneumonia.", "evidence": ["right lower lobe pneumonia"]}],
        "diagnoses": [
            {"name": "Pneumonia", "plain_name": "a lung infection", "evidence": ["Pneumonia"]},
            {"name": "Asthma", "plain_name": "", "evidence": ["asthma"]},
        ],
        "disposition": _statement("You went home."),
        "next_steps": [_statement("See your doctor in 2 days.")],
        "medicines": {
            "items": [{"name": "Amoxicillin", "change": "start", "text": "Take it.", "evidence": ["amoxicillin"]}],
            "none_statement": _statement("No new medicines."),
        },
        "return_precautions": [_statement("Call 911 if you cannot breathe.")],
        "questions": [{"question": "When is my X-ray?", "evidence": ["repeat chest X-ray"]}],
        "must_keep": {key: "shown" for key in MUST_KEEP},
    })
    return plan


def _walk(node, path: str = "$"):
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


class TestSchemaFolder(unittest.TestCase):
    def test_schema_folder_holds_only_the_plan_schema(self):
        present = sorted(name for name in os.listdir(_paths.SCHEMA_DIR) if not name.startswith("."))
        self.assertEqual(present, ["plan.schema.json"])


class TestSchemaShape(unittest.TestCase):
    def setUp(self):
        self.schema = _load()

    def test_is_draft_07(self):
        self.assertIn("draft-07", self.schema.get("$schema", ""))

    def test_description_says_structured_output_only(self):
        self.assertRegex(self.schema.get("description", ""), r"(?i)structured output")

    def test_top_level_keys_in_contract_order(self):
        self.assertEqual(self.schema["type"], "object")
        self.assertEqual(self.schema["required"], TOP_LEVEL_KEYS)
        self.assertEqual(sorted(self.schema["properties"]), sorted(TOP_LEVEL_KEYS))

    def test_every_object_forbids_additional_properties(self):
        for path, node in _walk(self.schema):
            if isinstance(node, dict) and ("properties" in node or node.get("type") == "object"):
                with self.subTest(path=path):
                    self.assertIs(node.get("additionalProperties"), False)

    def test_no_retired_keys_anywhere(self):
        for path, node in _walk(self.schema):
            if isinstance(node, dict) and isinstance(node.get("properties"), dict):
                with self.subTest(path=path):
                    self.assertFalse(RETIRED_KEYS & set(node["properties"]))

    def test_validator_supports_every_keyword_used(self):
        # Raises _minischema.UnsupportedKeyword if the schema grows a keyword
        # the test validator would silently ignore.
        _minischema.validate(_full(), self.schema)


class TestSchemaBehavior(unittest.TestCase):
    def setUp(self):
        self.schema = _load()

    def assertValid(self, plan):
        self.assertEqual(_minischema.validate(plan, self.schema), [])

    def assertInvalid(self, plan):
        self.assertNotEqual(_minischema.validate(plan, self.schema), [], "instance should be rejected")

    def _variant(self, mutate) -> dict:
        plan = copy.deepcopy(_full())
        mutate(plan)
        return plan

    def test_minimal_and_full_instances_pass(self):
        self.assertValid(_minimal())
        self.assertValid(_full())

    def test_schema_version_is_4_0(self):
        self.assertInvalid(self._variant(lambda p: p.update(schema_version="3.0")))

    def test_visit_types(self):
        for visit_type in VISIT_TYPES:
            with self.subTest(visit_type=visit_type):
                self.assertValid(self._variant(lambda p: p.update(visit_type=visit_type)))
        self.assertInvalid(self._variant(lambda p: p.update(visit_type="telehealth")))

    def test_every_top_level_key_is_required(self):
        for key in TOP_LEVEL_KEYS:
            with self.subTest(key=key):
                self.assertInvalid(self._variant(lambda p: p.pop(key)))

    def test_why_you_went_is_a_statement_not_null(self):
        self.assertInvalid(self._variant(lambda p: p.update(why_you_went=None)))
        self.assertInvalid(self._variant(lambda p: p.update(why_you_went="You had a cough.")))

    def test_findings_lead_and_disposition_may_be_null(self):
        self.assertValid(self._variant(lambda p: p.update(findings_lead=None, disposition=None)))

    def test_evidence_is_one_to_three_nonempty_strings(self):
        self.assertValid(self._variant(lambda p: p["why_you_went"].update(evidence=["a", "b", "c"])))
        for bad in ([], ["a", "b", "c", "d"], [""], [3], "cough"):
            with self.subTest(evidence=bad):
                self.assertInvalid(self._variant(lambda p: p["why_you_went"].update(evidence=bad)))

    def test_every_visible_item_requires_evidence(self):
        paths = (
            lambda p: p["why_you_went"],
            lambda p: p["findings_lead"],
            lambda p: p["findings"][0],
            lambda p: p["diagnoses"][0],
            lambda p: p["disposition"],
            lambda p: p["next_steps"][0],
            lambda p: p["medicines"]["items"][0],
            lambda p: p["medicines"]["none_statement"],
            lambda p: p["return_precautions"][0],
            lambda p: p["questions"][0],
        )
        for index, get in enumerate(paths):
            with self.subTest(item=index):
                self.assertInvalid(self._variant(lambda p: get(p).pop("evidence")))
                self.assertInvalid(self._variant(lambda p: get(p).update(evidence=[])))

    def test_extra_keys_are_rejected(self):
        for key in sorted(RETIRED_KEYS):
            with self.subTest(key=key):
                self.assertInvalid(self._variant(lambda p: p.update({key: []})))
        self.assertInvalid(self._variant(lambda p: p["findings"][0].update(unit_ids=[1])))
        self.assertInvalid(self._variant(lambda p: p["next_steps"][0].update(unit_ids=[1])))
        self.assertInvalid(self._variant(lambda p: p["medicines"].update(notes="x")))

    def test_item_shapes(self):
        self.assertInvalid(self._variant(lambda p: p["findings"][0].pop("result")))
        self.assertInvalid(self._variant(lambda p: p["diagnoses"][0].pop("plain_name")))
        self.assertInvalid(self._variant(lambda p: p["medicines"]["items"][0].pop("text")))
        self.assertInvalid(self._variant(lambda p: p["medicines"].pop("none_statement")))
        self.assertInvalid(self._variant(lambda p: p["questions"][0].pop("question")))
        self.assertValid(self._variant(lambda p: p["medicines"].update(none_statement=None)))

    def test_medicine_change_values(self):
        for change in MEDICINE_CHANGES:
            with self.subTest(change=change):
                self.assertValid(self._variant(lambda p: p["medicines"]["items"][0].update(change=change)))
        self.assertInvalid(self._variant(lambda p: p["medicines"]["items"][0].update(change="increase")))

    def test_list_limits(self):
        limits = {
            "findings": (lambda p: p["findings"], 6),
            "diagnoses": (lambda p: p["diagnoses"], 6),
            "next_steps": (lambda p: p["next_steps"], 6),
            "return_precautions": (lambda p: p["return_precautions"], 6),
            "medicines.items": (lambda p: p["medicines"]["items"], 8),
            "questions": (lambda p: p["questions"], 3),
        }
        for name, (get, limit) in limits.items():
            with self.subTest(slot=name):
                def fill(p, n):
                    items = get(p)
                    items[:] = [copy.deepcopy(items[0]) for _ in range(n)]
                self.assertValid(self._variant(lambda p: fill(p, limit)))
                self.assertInvalid(self._variant(lambda p: fill(p, limit + 1)))

    def test_must_keep_categories_and_values(self):
        for value in ("shown", "none_in_source"):
            self.assertValid(self._variant(lambda p: p["must_keep"].update(follow_up=value)))
        self.assertInvalid(self._variant(lambda p: p["must_keep"].update(follow_up="missing")))
        self.assertInvalid(self._variant(lambda p: p["must_keep"].update(follow_up=True)))
        self.assertInvalid(self._variant(lambda p: p["must_keep"].update(allergies="shown")))
        for key in MUST_KEEP:
            with self.subTest(category=key):
                self.assertInvalid(self._variant(lambda p: p["must_keep"].pop(key)))


if __name__ == "__main__":
    unittest.main()
