"""SETTLE stage: scripts/settle.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import check_draft  # noqa: E402
import finalize  # noqa: E402
import runlog  # noqa: E402
import settle  # noqa: E402
import validate  # noqa: E402


class SettleCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_dir = os.path.join(self.temporary.name, "run-settle")
        self.run_id = _runfix.make_source(self.run_dir)

    def path(self, name):
        return os.path.join(self.run_dir, name)

    def stage(self, name):
        return runlog.read(self.run_dir)["stages"].get(name)

    def check(self, draft, round_no=1):
        _runfix.write_draft(self.run_dir, draft, round_no)
        code, out, err = _runfix.call(check_draft.main, "--run-dir", self.run_dir, "--round", str(round_no))
        self.assertEqual(code, 0, out + err)
        return _runfix.checked(self.run_dir, round_no)

    def settle(self, verify, round_no=1):
        _runfix.write_verify(self.run_dir, verify, round_no)
        return _runfix.call(settle.main, "--run-dir", self.run_dir, "--round", str(round_no))

    def prepared(self, draft=None, round_no=1):
        """Check `draft` and return (checked draft, check, all-supported verify)."""
        checked, check = self.check(draft or _runfix.draft_raw(), round_no)
        return checked, check, _runfix.verify_raw_for(checked, check)

    def assert_contract_error(self, verify, fragment, round_no=1):
        code, out, err = self.settle(verify, round_no)
        self.assertEqual(code, 1, out + err)
        self.assertIn(fragment, err)
        self.assertFalse(os.path.exists(self.path("04_plan.settled.json")))
        return err

    def settled(self):
        return _runfix.read_json(self.path("04_plan.settled.json"))


class TestSupportedPath(SettleCase):
    def test_all_supported_settles_unchanged(self):
        draft, check, verify = self.prepared()
        code, out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        self.assertRegex(out.splitlines()[-1], r"^settle: ok \| round=1 claims=\d+ operations=0 words=\d+$")
        self.assertEqual(self.settled(), draft)
        record = _runfix.read_json(self.path("03_verify.json"))
        self.assertEqual(validate.validate(record, validate.load_schema("verify")), [])
        self.assertEqual(record["outcome"], "settled")
        self.assertEqual(record["counts"]["claims"], len(verify["claims"]))
        self.assertEqual(self.stage("verify")["status"], "ok")
        self.assertEqual(self.stage("settle")["status"], "ok")
        self.assertEqual(self.stage("settle")["checks"]["round"], 1)
        self.assertFalse(os.path.exists(self.path("04_repair.json")))

    def test_settled_plan_matches_draft_checked_schema(self):
        _draft, _check, verify = self.prepared()
        self.assertEqual(self.settle(verify)[0], 0)
        self.assertEqual(validate.validate(self.settled(), validate.load_schema("draft_checked")), [])


class TestOperations(SettleCase):
    def test_replace_sets_text_and_replaces_citations(self):
        _draft, _check, verify = self.prepared()
        verify["claims"][1]["result"] = "needs_correction"  # findings[0]
        verify["operations"] = [{
            "op": "replace", "path": "findings[0].result",
            "value": "Your heart tracing was normal.", "unit_ids": [3, 1],
        }]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        finding = self.settled()["findings"][0]
        self.assertEqual(finding["result"], "Your heart tracing was normal.")
        self.assertEqual(finding["unit_ids"], [3, 1])

    def test_removals_apply_from_the_highest_index_down(self):
        draft = _runfix.draft_raw()
        draft["next_steps"] = [
            {"text": "Rest for 2 days.", "unit_ids": [1]},
            {"text": "Make a follow-up appointment in 3 days.", "unit_ids": [6]},
            {"text": "Eat well.", "unit_ids": [10]},
        ]
        _draft, _check, verify = self.prepared(draft)
        verify["operations"] = [
            {"op": "remove", "path": "next_steps[0]", "reason": "noise"},
            {"op": "remove", "path": "next_steps[2]", "reason": "noise"},
        ]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        self.assertEqual([item["text"] for item in self.settled()["next_steps"]],
                         ["Make a follow-up appointment in 3 days."])

    def test_clear_optional_items_and_plain_name(self):
        draft = _runfix.draft_raw()
        draft["findings_lead"] = {"text": "The important tests were reassuring.", "unit_ids": [3]}
        draft["diagnoses"][0]["plain_name"] = "Pain in the chest wall"
        _draft, _check, verify = self.prepared(draft)
        verify["claims"][1]["result"] = "unsupported"  # findings_lead
        verify["operations"] = [
            {"op": "clear", "path": "findings_lead"},
            {"op": "clear", "path": "diagnoses[0].plain_name"},
        ]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        settled = self.settled()
        self.assertIsNone(settled["findings_lead"])
        self.assertEqual(settled["diagnoses"][0]["plain_name"], "")

    def test_invalid_targets_are_rejected(self):
        cases = [
            ({"op": "replace", "path": "findings[0]", "value": "x", "unit_ids": [3]}, "must target a visible text field"),
            ({"op": "replace", "path": "findings[5].result", "value": "x", "unit_ids": [3]}, "not a visible item"),
            ({"op": "replace", "path": "findings[0].result", "value": "x", "unit_ids": [2]}, "skipped boilerplate"),
            ({"op": "clear", "path": "why_you_went"}, "clear is only allowed"),
            ({"op": "remove", "path": "disposition", "reason": "noise"}, "remove must target a whole array item"),
            ({"op": "remove", "path": "findings[0].name", "reason": "noise"}, "remove must target a whole array item"),
        ]
        for operation, fragment in cases:
            with self.subTest(operation=operation):
                _draft, _check, verify = self.prepared()
                verify["operations"] = [operation]
                self.assert_contract_error(verify, fragment)
                if os.path.exists(self.path("03_verify.attempt1.raw.json")):
                    os.remove(self.path("03_verify.attempt1.raw.json"))

    def test_conflicting_operations_are_rejected(self):
        _draft, _check, verify = self.prepared()
        verify["operations"] = [
            {"op": "remove", "path": "next_steps[0]", "reason": "duplicate"},
            {"op": "replace", "path": "next_steps[0].text", "value": "Call your doctor.", "unit_ids": [6]},
        ]
        self.assert_contract_error(verify, "is removed or cleared and also edited")

    def test_noop_replace_is_rejected(self):
        draft, _check, verify = self.prepared()
        verify["operations"] = [{
            "op": "replace", "path": "findings[0].result",
            "value": draft["findings"][0]["result"], "unit_ids": [3],
        }]
        self.assert_contract_error(verify, "changes neither the text nor the citations")


class TestClaims(SettleCase):
    def test_every_visible_item_needs_exactly_one_claim(self):
        _draft, _check, verify = self.prepared()
        dropped = verify["claims"].pop()
        self.assert_contract_error(verify, f"{dropped['path']} has no claim")

    def test_duplicate_and_unknown_claims(self):
        _draft, _check, verify = self.prepared()
        verify["claims"].append(dict(verify["claims"][0]))
        verify["claims"].append({"path": "findings[0].result", "result": "supported"})
        err = self.assert_contract_error(verify, "has 2 claims")
        self.assertIn("claim for 'findings[0].result'", err)

    def test_non_supported_claim_needs_an_operation(self):
        _draft, _check, verify = self.prepared()
        verify["claims"][0]["result"] = "needs_correction"
        self.assert_contract_error(verify, "why_you_went is 'needs_correction' but no operation")

    def test_schema_error(self):
        _draft, _check, verify = self.prepared()
        verify["verdict"] = "pass"
        self.assert_contract_error(verify, "additional property 'verdict'")


class TestNumericFlags(SettleCase):
    def flagged(self):
        draft = _runfix.draft_raw()
        draft["medicines"]["items"][0]["text"] = "Take 500 mg every 8 hours as needed for pain."
        checked, check, verify = self.prepared(draft)
        self.assertEqual([flag["token"] for flag in check["numeric_flags"]], ["500 mg"])
        return checked, check, verify

    def test_equivalent_keeps_the_token(self):
        _draft, _check, verify = self.flagged()
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        record = _runfix.read_json(self.path("03_verify.json"))
        self.assertEqual(record["accepted_numeric"], [{"path": "medicines.items[0].text", "token": "500 mg"}])

    def test_equivalent_path_follows_earlier_removals(self):
        draft = _runfix.draft_raw()
        draft["next_steps"] = [
            {"text": "Rest.", "unit_ids": [1]},
            {"text": "See your doctor within 2 weeks.", "unit_ids": [6]},
        ]
        draft["coverage"]["follow_up"] = {"status": "shown", "unit_ids": [6]}
        _checked, check, verify = self.prepared(draft)
        self.assertEqual(check["numeric_flags"][0]["path"], "next_steps[1].text")
        verify["operations"] = [{"op": "remove", "path": "next_steps[0]", "reason": "noise"}]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        record = _runfix.read_json(self.path("03_verify.json"))
        self.assertEqual(record["accepted_numeric"], [{"path": "next_steps[0].text", "token": "2 weeks"}])

    def test_equivalent_contradicted_by_an_operation(self):
        _draft, _check, verify = self.flagged()
        verify["operations"] = [{
            "op": "replace", "path": "medicines.items[0].text",
            "value": "Take 400 mg every 8 hours as needed for pain.", "unit_ids": [5],
        }]
        self.assert_contract_error(verify, "contradicts replace medicines.items[0].text")

    def test_corrected_needs_the_replace_at_its_path(self):
        _draft, _check, verify = self.flagged()
        verify["claims"][5]["result"] = "needs_correction"
        verify["numeric_resolutions"][0] = {"flag_id": "n1", "resolution": "corrected",
                                            "correction_path": "medicines.items[0].text"}
        self.assert_contract_error(verify, "must set correction_path to medicines.items[0].text and replace")
        verify["operations"] = [{
            "op": "replace", "path": "medicines.items[0].text",
            "value": "Take 400 mg every 8 hours as needed for pain.", "unit_ids": [5],
        }]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.settled()["medicines"]["items"][0]["text"],
                         "Take 400 mg every 8 hours as needed for pain.")

    def test_corrected_value_must_be_backed(self):
        _draft, _check, verify = self.flagged()
        verify["numeric_resolutions"][0] = {"flag_id": "n1", "resolution": "corrected",
                                            "correction_path": "medicines.items[0].text"}
        verify["operations"] = [{
            "op": "replace", "path": "medicines.items[0].text",
            "value": "Take 600 mg every 8 hours as needed for pain.", "unit_ids": [5],
        }]
        self.assert_contract_error(verify, "contains '600 mg', which is not in its cited units")

    def test_removed_needs_a_deleting_operation(self):
        draft = _runfix.draft_raw()
        draft["next_steps"].append({"text": "Rest for 5 days.", "unit_ids": [1]})
        _checked, check, verify = self.prepared(draft)
        flag = check["numeric_flags"][0]
        self.assertEqual(flag["path"], "next_steps[1].text")
        verify["numeric_resolutions"] = [{"flag_id": flag["flag_id"], "resolution": "removed",
                                          "correction_path": "next_steps[1]"}]
        self.assert_contract_error(verify, "must set correction_path to the remove or clear operation")
        verify["operations"] = [{"op": "remove", "path": "next_steps[1]", "reason": "unsupported"}]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.settled()["next_steps"]), 1)

    def test_removed_may_name_a_replace_that_drops_the_number(self):
        _draft, _check, verify = self.flagged()
        verify["numeric_resolutions"][0] = {"flag_id": "n1", "resolution": "removed",
                                            "correction_path": "medicines.items[0].text"}
        verify["operations"] = [{
            "op": "replace", "path": "medicines.items[0].text",
            "value": "Take it as needed for pain.", "unit_ids": [5],
        }]
        code, _out, err = self.settle(verify)
        self.assertEqual(code, 0, err)

    def test_unresolved_and_unknown_flags(self):
        _draft, _check, verify = self.flagged()
        verify["numeric_resolutions"] = [{"flag_id": "n9", "resolution": "equivalent"}]
        err = self.assert_contract_error(verify, "numeric flag n1 ('500 mg' at medicines.items[0].text) is unresolved")
        self.assertIn("unknown flag 'n9'", err)

    def test_new_unbacked_number_from_a_replacement_is_rejected(self):
        _draft, _check, verify = self.prepared()
        verify["operations"] = [{
            "op": "replace", "path": "next_steps[0].text",
            "value": "Make a follow-up appointment in 7 days.", "unit_ids": [6],
        }]
        self.assert_contract_error(verify, "contains '7 days'")


class TestProtectedUnits(SettleCase):
    def test_every_uncited_unit_is_resolved_once(self):
        _draft, _check, verify = self.prepared()
        verify["protected_units"] = []
        self.assert_contract_error(verify, "uncited protected unit 9 (abnormal_or_pending_results) is unresolved")

    def test_not_needed_requires_a_reason(self):
        _draft, _check, verify = self.prepared()
        del verify["protected_units"][0]["reason"]
        self.assert_contract_error(verify, "'not_needed' without a reason")

    def test_unknown_protected_unit(self):
        _draft, _check, verify = self.prepared()
        verify["protected_units"].append({"unit_id": 5, "result": "covered"})
        self.assert_contract_error(verify, "protected unit 5 is not an uncited protected candidate")

    def test_missing_category_must_be_a_candidate_category(self):
        _draft, _check, verify = self.prepared()
        verify["protected_units"] = [{"unit_id": 9, "result": "missing", "category": "follow_up"}]
        self.assert_contract_error(verify, "is a candidate for abnormal_or_pending_results")

    def test_missing_requests_one_repair_round(self):
        self.request_repair()

    def request_repair(self):
        draft, _check, verify = self.prepared()
        verify["protected_units"] = [{"unit_id": 9, "result": "missing"}]
        code, out, err = self.settle(verify)
        self.assertEqual(code, 3, out + err)
        self.assertEqual(out.splitlines()[-1], "settle: repair requested | round=1 missing=1")
        repair = _runfix.read_json(self.path("04_repair.json"))
        self.assertEqual(repair["missing"], [{"unit_id": 9, "category": "abnormal_or_pending_results"}])
        self.assertEqual(repair["settled_draft"], draft)
        self.assertEqual(repair["run_id"], self.run_id)
        self.assertEqual(_runfix.read_json(self.path("03_verify.json"))["outcome"], "repair_requested")
        self.assertFalse(os.path.exists(self.path("04_plan.settled.json")))
        self.assertEqual(self.stage("settle")["status"], "repair_requested")
        self.assertEqual(self.stage("verify")["status"], "ok")
        return repair

    def repaired_draft(self):
        draft = _runfix.draft_raw()
        draft["findings"].append({"name": "Cholesterol test", "result": "The result is not back yet.",
                                  "unit_ids": [9]})
        draft["coverage"]["abnormal_or_pending_results"] = {"status": "shown", "unit_ids": [9]}
        return draft

    def test_repair_round_settles_and_finalizes(self):
        self.request_repair()
        _checked, _check, verify = self.prepared(self.repaired_draft(), round_no=2)
        code, out, err = self.settle(verify, round_no=2)
        self.assertEqual(code, 0, out + err)
        self.assertIn("round=2", out)
        self.assertEqual(self.settled()["findings"][-1]["unit_ids"], [9])
        self.assertEqual(_runfix.read_json(self.path("03_verify.r2.json"))["outcome"], "settled")
        self.assertEqual(self.stage("settle")["status"], "ok")
        code, out, err = _runfix.call(finalize.main, "--run-dir", self.run_dir)
        self.assertEqual(code, 0, out + err)
        self.assertIn("finalize: ok | round=2", out)

    def test_repair_round_cannot_remove_the_repaired_content(self):
        self.request_repair()
        _checked, _check, verify = self.prepared(self.repaired_draft(), round_no=2)
        verify["operations"] = [{"op": "remove", "path": "findings[1]", "reason": "noise"}]
        err = self.assert_contract_error(verify, "unit 9 was reported missing in round 1", round_no=2)
        self.assertIn("coverage.abnormal_or_pending_results", err)

    def test_second_miss_fails_the_run(self):
        self.request_repair()
        draft = self.repaired_draft()
        # Force a missing result in round 2 with a second candidate unit.
        protected = _runfix.read_json(self.path("01_protected.json"))
        protected["categories"]["follow_up"] = [6, 10]
        _runfix.write_json(self.path("01_protected.json"), protected)
        _checked, check, verify = self.prepared(draft, round_no=2)
        verify["protected_units"] = [{"unit_id": 10, "result": "missing"}]
        code, out, err = self.settle(verify, round_no=2)
        self.assertEqual(code, 1, out + err)
        self.assertIn("retry=exhausted", out)
        self.assertIn("still missing after the repair round", err)
        self.assertEqual(self.stage("settle")["status"], "failed")
        self.assertFalse(os.path.exists(self.path("04_plan.settled.json")))
        # A retried verification cannot undo the terminal miss.
        verify["protected_units"] = [{"unit_id": 10, "result": "covered"}]
        code, _out, err = self.settle(verify, round_no=2)
        self.assertEqual(code, 1)
        self.assertIn("after a terminal failure", err)
        self.assertFalse(os.path.exists(self.path("04_plan.settled.json")))
        code, _out, err = _runfix.call(finalize.main, "--run-dir", self.run_dir)
        self.assertEqual(code, 1)


class TestCoverageAndBudget(SettleCase):
    def test_removal_that_orphans_protected_coverage_is_rejected(self):
        _draft, _check, verify = self.prepared()
        verify["operations"] = [{"op": "remove", "path": "next_steps[0]", "reason": "noise"}]
        self.assert_contract_error(verify, "coverage.follow_up is 'shown' but none of its unit_ids [6]")

    def test_recitation_that_orphans_coverage_is_rejected(self):
        _draft, _check, verify = self.prepared()
        verify["operations"] = [{
            "op": "replace", "path": "disposition.text", "value": "You went home.", "unit_ids": [1],
        }]
        self.assert_contract_error(verify, "coverage.disposition")

    def test_settled_plan_must_fit_the_hard_budget(self):
        _draft, _check, verify = self.prepared()
        verify["operations"] = [{
            "op": "replace", "path": "findings[0].result", "value": "normal " * 520, "unit_ids": [3],
        }]
        self.assert_contract_error(verify, "over the hard maximum of 500")


class TestRetryAndWorkflow(SettleCase):
    def test_first_contract_error_archives_then_retry_passes(self):
        _draft, _check, verify = self.prepared()
        bad = _runfix.deep(verify)
        bad["claims"].pop()
        code, out, _err = self.settle(bad)
        self.assertEqual(code, 1)
        self.assertIn("retry=allowed", out)
        self.assertFalse(os.path.exists(self.path("03_verify.raw.json")))
        self.assertTrue(os.path.exists(self.path("03_verify.attempt1.raw.json")))
        self.assertEqual(self.stage("verify")["status"], "failed")
        self.assertEqual(self.settle(verify)[0], 0)
        self.assertEqual(self.stage("verify")["status"], "ok")
        self.assertEqual(self.stage("verify")["attempts"], 2)

    def test_second_contract_error_is_terminal(self):
        _draft, _check, verify = self.prepared()
        verify["claims"].pop()
        self.assertEqual(self.settle(verify)[0], 1)
        code, out, err = self.settle(verify)
        self.assertEqual(code, 1)
        self.assertIn("retry=exhausted", out)
        self.assertIn("Stop the run", err)

    def test_tampered_check_is_a_workflow_error(self):
        _draft, check, verify = self.prepared()
        check["uncited_protected"] = []
        _runfix.write_json(self.path("02_check.json"), check)
        code, out, err = self.settle(verify)
        self.assertEqual(code, 1)
        self.assertIn("workflow_error", out)
        self.assertIn("02_check.json does not match 02_draft.json", err)
        self.assertTrue(os.path.exists(self.path("03_verify.raw.json")))

    def test_missing_verification_does_not_consume_an_attempt(self):
        self.prepared()
        code, out, err = _runfix.call(settle.main, "--run-dir", self.run_dir)
        self.assertEqual(code, 1)
        self.assertIn("03_verify.raw.json is missing", err)
        self.assertIsNone(self.stage("verify"))


class TestPathHelpers(unittest.TestCase):
    def test_map_path(self):
        removed = {"findings": {0, 2}}
        self.assertIsNone(settle.map_path("findings[2].result", removed))
        self.assertEqual(settle.map_path("findings[3].result", removed), "findings[1].result")
        self.assertEqual(settle.map_path("findings[1]", removed), "findings[0]")
        self.assertEqual(settle.map_path("medicines.items[1].text", removed), "medicines.items[1].text")
        self.assertEqual(settle.map_path("why_you_went.text", removed), "why_you_went.text")


if __name__ == "__main__":
    unittest.main()
