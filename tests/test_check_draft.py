"""CHECK stage: scripts/check_draft.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import check_draft  # noqa: E402
import plan_paths  # noqa: E402
import runlog  # noqa: E402
import validate  # noqa: E402


class CheckCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = os.path.join(self.temporary.name, "run-check")
        self.run_id = _runfix.make_source(self.run_dir)
        self.draft = _runfix.draft_raw()

    def check(self, draft=None, round_no=1):
        if draft is not None:
            _runfix.write_draft(self.run_dir, draft, round_no)
        args = ["--run-dir", self.run_dir]
        if round_no != 1:
            args += ["--round", str(round_no)]
        return _runfix.call(check_draft.main, *args)

    def path(self, name):
        return os.path.join(self.run_dir, name)

    def stage(self, name):
        return runlog.read(self.run_dir)["stages"].get(name)

    def assert_fails_with(self, draft, fragment):
        code, out, err = self.check(draft)
        self.assertEqual(code, 1, out + err)
        self.assertIn(fragment, err)
        self.assertFalse(os.path.exists(self.path("02_draft.json")))
        self.assertFalse(os.path.exists(self.path("02_check.json")))
        return err


class TestPass(CheckCase):
    def test_valid_draft_writes_checked_draft_and_check(self):
        code, out, err = self.check(self.draft)
        self.assertEqual(code, 0, err)
        self.assertRegex(out.splitlines()[-1], r"^check: ok \| round=1 words=\d+ over_budget=false")
        draft, check = _runfix.checked(self.run_dir)
        self.assertEqual(validate.validate(draft, validate.load_schema("draft_checked")), [])
        self.assertEqual(validate.validate(check, validate.load_schema("check")), [])
        self.assertEqual(list(draft)[:2], ["schema_version", "run_id"])
        self.assertEqual(draft["run_id"], self.run_id)
        self.assertEqual({k: v for k, v in draft.items() if k not in ("schema_version", "run_id")}, self.draft)
        self.assertEqual(check["budget"], {"target": 300, "warn": 350, "max": 500})
        self.assertEqual(check["word_count"], check_draft.word_count(draft))
        self.assertFalse(check["over_budget"])
        self.assertEqual(check["numeric_flags"], [])
        self.assertEqual(check["uncited_protected"], [{"unit_id": 9, "categories": ["abnormal_or_pending_results"]}])
        self.assertEqual(self.stage("write")["status"], "ok")
        self.assertEqual(self.stage("check")["status"], "ok")
        self.assertEqual(self.stage("check")["checks"]["round"], 1)
        self.assertIn({"path": "02_draft.raw.json"}, self.stage("write")["artifacts"])

    def test_numeric_flags_name_unbacked_tokens_per_field(self):
        self.draft["medicines"]["items"][0]["text"] = "Take 500 mg every 8 hours as needed for pain."
        self.draft["next_steps"][0]["text"] = "See your doctor in 3 days or 2 weeks."
        self.assertEqual(self.check(self.draft)[0], 0)
        _draft, check = _runfix.checked(self.run_dir)
        self.assertEqual(check["numeric_flags"], [
            {"flag_id": "n1", "path": "next_steps[0].text", "token": "2 weeks", "unit_ids": [6]},
            {"flag_id": "n2", "path": "medicines.items[0].text", "token": "500 mg", "unit_ids": [5]},
        ])

    def test_uncited_protected_lists_every_category_once_per_unit(self):
        protected = dict(_runfix.PROTECTED, follow_up=[6, 9])
        _runfix.make_source(self.run_dir, protected=protected)
        self.assertEqual(self.check(self.draft)[0], 0)
        _draft, check = _runfix.checked(self.run_dir)
        self.assertEqual(check["uncited_protected"], [
            {"unit_id": 9, "categories": ["follow_up", "abnormal_or_pending_results"]},
        ])

    def test_over_warn_budget_passes_with_flag(self):
        self.draft["findings"][0]["result"] = "normal " * 340
        self.assertEqual(self.check(self.draft)[0], 0)
        _draft, check = _runfix.checked(self.run_dir)
        self.assertGreater(check["word_count"], 350)
        self.assertTrue(check["over_budget"])


class TestFailures(CheckCase):
    def test_schema_error(self):
        del self.draft["coverage"]
        self.assert_fails_with(self.draft, "missing required property 'coverage'")

    def test_unknown_unit(self):
        self.draft["findings"][0]["unit_ids"] = [99]
        self.assert_fails_with(self.draft, "findings[0] cites unknown unit 99")

    def test_skipped_unit_is_not_a_valid_citation(self):
        self.draft["findings"][0]["unit_ids"] = [3, 2]
        self.assert_fails_with(self.draft, "cites unit 2, which is skipped boilerplate (url)")

    def test_shown_coverage_must_be_backed_by_a_visible_citation(self):
        self.draft["coverage"]["abnormal_or_pending_results"] = {"status": "shown", "unit_ids": [9]}
        self.assert_fails_with(self.draft, "coverage.abnormal_or_pending_results is 'shown' but none of its unit_ids")

    def test_shown_coverage_needs_unit_ids(self):
        self.draft["coverage"]["follow_up"] = {"status": "shown", "unit_ids": []}
        self.assert_fails_with(self.draft, "coverage.follow_up is 'shown' but lists no unit_ids")

    def test_none_in_source_cites_nothing(self):
        self.draft["coverage"]["abnormal_or_pending_results"] = {"status": "none_in_source", "unit_ids": [9]}
        self.assert_fails_with(self.draft, "must have unit_ids []")

    def test_empty_brackets(self):
        self.draft["diagnoses"][0]["name"] = "Chest wall pain ()"
        self.assert_fails_with(self.draft, "diagnoses[0].name contains empty brackets")

    def test_clinician_names(self):
        self.draft["next_steps"][0]["text"] = f"See {_runfix.PII_NAME} in 3 days."
        self.assert_fails_with(self.draft, "names a clinician ('Dr. Alok Singh')")
        self.draft["next_steps"][0]["text"] = "See Alok Singh, MD in 3 days."
        self.assert_fails_with(self.draft, "names a clinician")

    def test_over_max_budget(self):
        self.draft["findings"][0]["result"] = "normal " * 520
        self.assert_fails_with(self.draft, "over the hard maximum of 500")

    def test_invalid_json(self):
        with open(_runfix.write_draft(self.run_dir, {}), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        code, _out, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("is not valid JSON", err)

    def test_missing_raw_draft_does_not_consume_an_attempt(self):
        code, out, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("workflow_error", out)
        self.assertIn("02_draft.raw.json is missing", err)
        self.assertIsNone(self.stage("write"))
        self.assertFalse(os.path.exists(self.path("02_draft.attempt1.raw.json")))

    def test_units_from_another_run_are_a_workflow_error(self):
        units = _runfix.read_json(self.path("01_units.json"))
        units["run_id"] = "stale-run"
        _runfix.write_json(self.path("01_units.json"), units)
        code, out, err = self.check(self.draft)
        self.assertEqual(code, 1)
        self.assertIn("01_units.json does not belong to the current run", err)
        self.assertTrue(os.path.exists(self.path("02_draft.raw.json")))


class TestRetryBudget(CheckCase):
    def test_first_failure_archives_then_retry_passes(self):
        bad = _runfix.deep(self.draft)
        bad["findings"][0]["unit_ids"] = [99]
        code, out, err = self.check(bad)
        self.assertEqual(code, 1)
        self.assertIn("retry=allowed", out)
        self.assertIn("Retry WRITE once", err)
        self.assertFalse(os.path.exists(self.path("02_draft.raw.json")))
        self.assertEqual(_runfix.read_json(self.path("02_draft.attempt1.raw.json")), bad)
        write = self.stage("write")
        self.assertEqual(write["status"], "failed")
        self.assertTrue(write["checks"]["retry_allowed"])
        self.assertIn({"path": "02_draft.attempt1.raw.json"}, write["artifacts"])

        code, out, err = self.check(self.draft)
        self.assertEqual(code, 0, err)
        write = self.stage("write")
        self.assertEqual(write["status"], "ok")
        self.assertEqual(write["attempts"], 2)
        self.assertEqual(write["checks"]["attempt"], 2)
        self.assertEqual(write["checks"]["errors"], [])

    def test_second_failure_exhausts_the_budget(self):
        bad = _runfix.deep(self.draft)
        bad["findings"][0]["unit_ids"] = [99]
        self.assertEqual(self.check(bad)[0], 1)
        code, out, err = self.check(bad)
        self.assertEqual(code, 1)
        self.assertIn("retry=exhausted", out)
        self.assertIn("Stop the run", err)
        self.assertTrue(os.path.exists(self.path("02_draft.raw.json")))
        write = self.stage("write")
        self.assertEqual(write["status"], "failed")
        self.assertFalse(write["checks"]["retry_allowed"])
        self.assertTrue(write["checks"]["terminal"])
        self.assertEqual(write["attempts"], 2)

    def test_a_third_attempt_is_refused_even_when_valid(self):
        bad = _runfix.deep(self.draft)
        bad["findings"][0]["unit_ids"] = [99]
        self.check(bad)
        self.check(bad)
        code, _out, err = self.check(self.draft)
        self.assertEqual(code, 1)
        self.assertIn("already stopped at stage write after a terminal failure", err)
        self.assertFalse(os.path.exists(self.path("02_draft.json")))


class TestRoundTwo(CheckCase):
    def write_repair(self, missing):
        _runfix.write_json(self.path("04_repair.json"), {
            "schema_version": "3.0", "run_id": self.run_id, "missing": missing,
            "settled_draft": {},
        })

    def test_round_two_requires_a_repair_request(self):
        code, _out, err = self.check(self.draft, round_no=2)
        self.assertEqual(code, 1)
        self.assertIn("04_repair.json", err)

    def test_round_two_must_cite_the_missing_units(self):
        self.write_repair([{"unit_id": 9, "category": "abnormal_or_pending_results"}])
        code, _out, err = self.check(self.draft, round_no=2)
        self.assertEqual(code, 1)
        self.assertIn("unit 9 (abnormal_or_pending_results) was reported missing", err)
        self.assertTrue(os.path.exists(self.path("02_draft.r2.attempt1.raw.json")))

    def test_round_two_writes_suffixed_outputs(self):
        self.write_repair([{"unit_id": 9, "category": "abnormal_or_pending_results"}])
        self.draft["findings"].append({"name": "Cholesterol test", "result": "The result is pending.", "unit_ids": [9]})
        self.draft["coverage"]["abnormal_or_pending_results"] = {"status": "shown", "unit_ids": [9]}
        code, out, err = self.check(self.draft, round_no=2)
        self.assertEqual(code, 0, err)
        self.assertIn("round=2", out)
        draft, check = _runfix.checked(self.run_dir, 2)
        self.assertEqual(check["round"], 2)
        self.assertEqual(check["uncited_protected"], [])
        self.assertEqual(draft["findings"][-1]["unit_ids"], [9])
        self.assertFalse(os.path.exists(self.path("02_draft.json")))
        self.assertEqual(self.stage("check")["checks"]["round"], 2)


class TestHelpers(unittest.TestCase):
    def test_artifact_names(self):
        self.assertEqual(check_draft.artifact_names(1)["draft_raw_attempt"], "02_draft.attempt1.raw.json")
        self.assertEqual(check_draft.artifact_names(2)["verify_raw_attempt"], "03_verify.r2.attempt1.raw.json")
        self.assertEqual(check_draft.artifact_names(2)["check"], "02_check.r2.json")
        with self.assertRaises(ValueError):
            check_draft.artifact_names(3)

    def test_word_count_counts_visible_words_only(self):
        plan = _runfix.draft_raw()
        plan["questions"] = []
        count = check_draft.word_count(plan)
        text = " ".join(t for _p, t, _u in plan_paths.visible_strings(plan))
        self.assertEqual(count, len(text.split()))


if __name__ == "__main__":
    unittest.main()
