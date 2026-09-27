"""Regression guards for the prompt-only `simplify` stage files.

`stages/write.md` teaches the draft shape and carries the worked example
(contract C6); `stages/verify.md` holds the verification checklist that
replaced the former scripts (PRD §6); `reference/style_rules.md` holds the
shared writing rules. These tests read the files; they run no model.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _minischema  # noqa: E402
import _paths  # noqa: E402

STAGES_DIR = _paths.STAGES_DIR
REFERENCE_DIR = _paths.REFERENCE_DIR
PLAN_SCHEMA_PATH = os.path.join(_paths.SCHEMA_DIR, "plan.schema.json")

TOP_LEVEL_KEYS = (
    "schema_version", "visit_type", "why_you_went", "findings_lead", "findings", "diagnoses",
    "disposition", "next_steps", "medicines", "return_precautions", "questions", "must_keep",
)
MUST_KEEP = (
    "medication_changes", "follow_up", "return_precautions", "diagnoses", "disposition",
    "abnormal_or_pending_results",
)
# Words from the previous worked example (the owner's real ER visit); the new
# example must not echo it.
FORBIDDEN_EXAMPLE_WORDS = (r"headache", r"\bECG\b", r"bundle branch", r"\bEKG\b")
TIME_WORD = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|a few|several)"
TIME_INTERVAL = re.compile(
    rf"\b{TIME_WORD}(?:\s*(?:to|-|or)\s*{TIME_WORD})?\s+(?:hours?|days?|weeks?|months?)\b"
    r"|\btomorrow\b|\bnext week\b",
    re.IGNORECASE,
)
PENDING = re.compile(
    r"\bpending\b|not (?:back|ready|available)(?: yet)?|\bwaiting\b|\bstill being\b"
    r"|will (?:call|contact|let you know)",
    re.IGNORECASE,
)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fenced_blocks(text: str) -> list[tuple[str, str]]:
    """[(language, body)] for every fenced block, in document order."""
    return [(m.group(1), m.group(2)) for m in re.finditer(r"^```([A-Za-z]*)[ \t]*\n(.*?)\n```[ \t]*$",
                                                          text, re.MULTILINE | re.DOTALL)]


def _worked_example(text: str) -> tuple[str, dict, str]:
    """The C6 example: a ```text source, then the ```json draft, then the ```markdown report."""
    blocks = _fenced_blocks(text)
    for index, (lang, body) in enumerate(blocks):
        if lang != "json" or '"schema_version"' not in body:
            continue
        sources = [b for lang_, b in blocks[:index] if lang_ == "text"]
        reports = [b for lang_, b in blocks[index + 1:] if lang_ == "markdown"]
        assert sources, "worked example: no ```text source block before the draft"
        assert reports, "worked example: no ```markdown report block after the draft"
        return sources[-1], json.loads(body), reports[0]
    raise AssertionError("write.md has no ```json worked-example draft with schema_version")


def _items(plan: dict) -> list[tuple[str, list[str], list[str]]]:
    """[(slot, visible strings, evidence)] for every visible item of a draft."""
    out = []

    def statement(slot, node):
        if node:
            out.append((slot, [node["text"]], node["evidence"]))

    statement("why_you_went", plan["why_you_went"])
    statement("findings_lead", plan["findings_lead"])
    for item in plan["findings"]:
        out.append(("findings", [item["name"], item["result"]], item["evidence"]))
    for item in plan["diagnoses"]:
        out.append(("diagnoses", [item["name"]] + ([item["plain_name"]] if item["plain_name"] else []),
                    item["evidence"]))
    statement("disposition", plan["disposition"])
    for item in plan["next_steps"]:
        statement("next_steps", item)
    for item in plan["medicines"]["items"]:
        out.append(("medicines", [item["name"], item["text"]], item["evidence"]))
    statement("medicines.none_statement", plan["medicines"]["none_statement"])
    for item in plan["return_precautions"]:
        statement("return_precautions", item)
    for item in plan["questions"]:
        out.append(("questions", [item["question"]], item["evidence"]))
    return out


def _rendered_plain(markdown: str) -> str:
    text = re.sub(r"^\s*#+\s*", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    return _norm(text)


def _word_count(markdown: str) -> int:
    return sum(1 for token in _rendered_plain(markdown).split() if re.search(r"\w", token))


class TestStageFiles(unittest.TestCase):
    def test_only_write_and_verify_stages_exist(self):
        present = sorted(name for name in os.listdir(STAGES_DIR) if not name.startswith("."))
        self.assertEqual(present, ["verify.md", "write.md"])


class TestWriteStage(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "write.md"))

    def test_names_every_top_level_key(self):
        for key in TOP_LEVEL_KEYS:
            self.assertIn(f"`{key}`", self.text, key)

    def test_names_every_must_keep_category(self):
        for category in MUST_KEEP:
            self.assertIn(category, self.text)
        self.assertIn("none_in_source", self.text)

    def test_inputs_are_source_and_style_rules(self):
        self.assertIn("reference/style_rules.md", self.text)
        self.assertRegex(self.text, r"(?i)verbatim")
        self.assertIn("evidence", self.text)

    def test_teaches_the_new_quality_rules(self):
        for pattern in (
            r"(?i)say each thing once|said once|said twice",
            r"(?i)timing",
            r"(?i)every complaint",
            r"(?i)short name",
            r"(?i)atrioventricular \(AV\) block",
            r"(?i)ST changes",
            r"plain_name",
            r"(?i)translate, don't interpret",
        ):
            with self.subTest(pattern=pattern):
                self.assertRegex(self.text, pattern)


class TestWorkedExample(unittest.TestCase):
    """Contract C6."""

    def setUp(self):
        self.write = _read(os.path.join(STAGES_DIR, "write.md"))
        self.source, self.plan, self.report = _worked_example(self.write)
        self.items = _items(self.plan)

    def test_draft_validates_against_the_plan_schema(self):
        schema = json.loads(_read(PLAN_SCHEMA_PATH))
        self.assertEqual(_minischema.validate(self.plan, schema), [])

    def test_is_a_synthetic_urgent_care_visit(self):
        self.assertEqual(self.plan["schema_version"], "4.0")
        self.assertEqual(self.plan["visit_type"], "urgent_care")

    def test_is_not_the_old_er_headache_case(self):
        example = "\n".join((self.source, json.dumps(self.plan), self.report))
        for pattern in FORBIDDEN_EXAMPLE_WORDS:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, example, re.IGNORECASE))

    def test_every_evidence_quote_is_verbatim_in_the_source(self):
        source = _norm(self.source)
        for slot, _visible, evidence in self.items:
            for quote in evidence:
                with self.subTest(slot=slot, quote=quote):
                    self.assertIn(_norm(quote), source)

    def test_every_number_is_backed_by_its_evidence(self):
        for slot, visible, evidence in self.items:
            backed = set(re.findall(r"\d+", " ".join(evidence).replace(",", "")))
            for number in re.findall(r"\d+", " ".join(visible).replace(",", "")):
                with self.subTest(slot=slot, number=number, text=visible):
                    self.assertIn(number, backed)

    def test_rendered_report_is_within_budget(self):
        self.assertLessEqual(_word_count(self.report), 300)

    def test_every_visible_string_appears_in_the_rendered_report(self):
        rendered = _rendered_plain(self.report).casefold()
        for slot, visible, _evidence in self.items:
            for string in visible:
                with self.subTest(slot=slot, string=string):
                    self.assertIn(_norm(string).rstrip(".").casefold(), rendered)

    def test_rendered_report_shows_no_evidence(self):
        # Evidence is internal; the report carries no evidence label or quote block.
        self.assertNotRegex(self.report, r"(?im)\bevidence\b|^\s*>")

    def test_rendered_report_uses_the_urgent_care_format(self):
        self.assertRegex(self.report, r"(?m)^#+\s*Your urgent care visit, simplified\s*$")
        self.assertNotIn("When should you go back to the ER?", self.report)
        self.assertNotIn("The ER diagnosed you with:", self.report)
        expected = ["What did they find?", "What should you do now?", "When to get help right away"]
        if self.plan["diagnoses"]:
            expected.insert(1, "Diagnosed with:")
        if self.plan["questions"]:
            expected.append("Questions you may want to ask")
        positions = [self.report.find(heading) for heading in expected]
        self.assertNotIn(-1, positions, dict(zip(expected, positions)))
        self.assertEqual(positions, sorted(positions), "report sections are out of order")
        why = _norm(self.plan["why_you_went"]["text"]).rstrip(".").casefold()
        why_at = _rendered_plain(self.report).casefold().find(why)
        self.assertNotEqual(why_at, -1, "why_you_went is not in the report")
        self.assertLess(why_at, _rendered_plain(self.report).find("What did they find?"))

    def test_has_a_medicine_start(self):
        self.assertIn("start", [item["change"] for item in self.plan["medicines"]["items"]])
        self.assertEqual(self.plan["must_keep"]["medication_changes"], "shown")

    def test_has_a_timed_follow_up(self):
        timed = [s["text"] for s in self.plan["next_steps"] if TIME_INTERVAL.search(s["text"])]
        self.assertTrue(timed, "no next step keeps a time interval")
        self.assertEqual(self.plan["must_keep"]["follow_up"], "shown")

    def test_has_a_pending_result(self):
        visible = " ".join(" ".join(v) for _slot, v, _e in self.items)
        self.assertRegex(visible, PENDING)
        self.assertEqual(self.plan["must_keep"]["abnormal_or_pending_results"], "shown")

    def test_must_keep_is_honest(self):
        shown_slots = {slot for slot, _v, _e in self.items}
        pairs = {
            "return_precautions": "return_precautions",
            "diagnoses": "diagnoses",
            "disposition": "disposition",
        }
        for category, slot in pairs.items():
            if self.plan["must_keep"][category] == "shown":
                with self.subTest(category=category):
                    self.assertIn(slot, shown_slots)


class TestVerifyStage(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(STAGES_DIR, "verify.md"))

    def test_covers_the_checklist(self):
        for pattern in (
            r"(?i)verbatim",
            r"(?i)boilerplate",
            r"(?i)\bnumbers?\b",
            r"(?i)must[-_ ]keep",
            r"(?i)none_in_source",
            r"300 words",
            r"(?i)privacy",
            r"(?i)brackets",
            r"(?i)said once|say each thing once|said twice",
            r"(?i)timing",
            r"(?i)reason",
            r"(?i)urgency",
            r"(?i)complaint",
            r"(?i)negation",
            r"(?i)uncertainty",
            r"plain_name",
            r"(?i)outside (?:or general )?(?:medical )?knowledge|general medical knowledge",
            r"(?i)cut",
        ):
            with self.subTest(pattern=pattern):
                self.assertRegex(self.text, pattern)

    def test_names_the_limits(self):
        for pattern in (r"\b6\b|\bsix\b", r"\b8\b|\beight\b", r"\b3\b|\bthree\b"):
            self.assertRegex(self.text, pattern)

    def test_runs_as_sub_agent_or_second_pass(self):
        self.assertRegex(self.text, r"(?i)sub-?agent")
        self.assertRegex(self.text, r"(?i)second pass")
        self.assertIn("reference/style_rules.md", self.text)

    def test_edits_are_bounded(self):
        self.assertRegex(self.text, r"(?i)never add[^.]*not in the source")

    def test_returns_a_corrected_draft_and_change_list(self):
        self.assertRegex(self.text, r"(?i)corrected draft")
        self.assertRegex(self.text, r"(?i)change list|list of changes")


class TestStyleRules(unittest.TestCase):
    def setUp(self):
        self.text = _read(os.path.join(REFERENCE_DIR, "style_rules.md"))

    def _section(self, heading: str) -> str:
        match = re.search(rf"^{re.escape(heading)} --(.*?)(?=^[A-Z][A-Z ]+ --|\Z)", self.text,
                          re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, heading)
        return match.group(1)

    def test_has_the_seven_sections(self):
        for heading in ("SOURCES", "PII", "NUMERACY", "LANGUAGE RULES", "PLAIN WORDS", "SHOW", "SKIP"):
            with self.subTest(heading=heading):
                self._section(heading)

    def test_sources_include_the_users_own_records(self):
        self.assertRegex(self._section("SOURCES"), r"(?i)health[- ]records")

    def test_plain_words_rule_is_resolved(self):
        section = self._section("PLAIN WORDS")
        self.assertRegex(section, r"(?i)only when the source")
        self.assertRegex(section, r"(?i)never[^.]*general medical knowledge")

    def test_numeracy_checks_numbers_against_evidence(self):
        self.assertRegex(self._section("NUMERACY"), r"(?i)evidence")

    def test_abbreviations_lookup_is_optional(self):
        self.assertIn("reference/abbreviations.json", self.text)
        self.assertRegex(self.text, r"(?i)optional")

    def test_no_retired_references(self):
        for pattern in (r"(?i)ahrq", r"01_source\.txt", r"unit_ids?", r"(?i)unit ids?", r"(?i)source units?"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.text, pattern)


if __name__ == "__main__":
    unittest.main()
