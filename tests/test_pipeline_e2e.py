"""End-to-end deterministic pipeline test.

Drives the whole chain described in SKILL.md -- unitize, ground+glossary,
merge_facts, assemble (cite_check + numeric_parity), review (sanitize_review),
correct (diff_guard), assemble-missing (cite_check --additions), finalize,
render_audit -- against the real synthetic fixture document, with
hand-written "agent" outputs standing in for the LLM stages. Every script is
invoked exactly as SKILL.md describes: `python3 <script> --run-dir <run> ...`
via subprocess with sys.executable, same flags, same order.

A second, shorter test drives the "nothing to correct, nothing missing"
path, where correct and assemble-missing are both skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
import _runfix  # noqa: E402

import validate  # noqa: E402

FIXTURE = os.path.join(_paths.TESTS_DIR, "fixtures", "documents", "synthetic-visit-note.txt")

EXPECTED_STAGES = (
    "unitize", "ground", "glossary", "assemble", "numeric_parity",
    "review_fidelity", "review_coverage", "correct", "assemble_missing", "finalize",
)


def _script(name: str) -> str:
    return os.path.join(_paths.SCRIPTS_DIR, name)


def _run(name: str, *args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, _script(name), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _run_ok(name: str, *args: str) -> subprocess.CompletedProcess:
    result = _run(name, *args)
    assert result.returncode == 0, (
        f"{name} {' '.join(args)} exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _body_only(html_text: str) -> str:
    """The rendered body, excluding the embedded plan-JSON <script> blob,
    which legitimately carries source_fact_ids and every other audit-trail
    field. Mirrors test_render_html.py's own helper."""
    start = html_text.index('<script type="application/json"')
    end = html_text.index("</script>", start)
    return html_text[:start] + html_text[end + len("</script>"):]


class TestPipelineEndToEnd(unittest.TestCase):
    """Drives the full deterministic chain against the synthetic fixture
    document, with hand-written stand-ins for every LLM stage."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        runs_dir = os.path.join(cls._tmp.name, "simplify-runs")

        # --- Stage 0: unitize ------------------------------------------
        result = _run_ok(
            "unitize.py", "--runs-dir", runs_dir, "--input", f"{FIXTURE}:native",
        )
        cls.run_dir = result.stdout.strip().splitlines()[-1]
        assert os.path.isdir(cls.run_dir)

        units_doc = _read_json(os.path.join(cls.run_dir, "01_units.json"))
        cls.chunks = units_doc["chunks"]
        assert len(cls.chunks) == 1, "fixture expected to fit in a single chunk"

        # --- Stage 1: ground (one chunk) + glossary ---------------------
        # Real, verbatim substrings of the fixture's chunk-1 unit texts.
        # unit 8: chief complaint; 16/17: assessment; 21: metoprolol order;
        # 26: stress test order; 30: angiography discussion; 32: sodium
        # instruction; 36: follow-up; 39: warning sign.
        facts_raw = {"facts": [
            {"category": "reason_for_visit", "unit_id": 8,
             "quote": "chest tightness and shortness of breath (SOB) on exertion",
             "text": "Patient has intermittent chest tightness and shortness of "
                      "breath on exertion, present for about three weeks."},
            {"category": "diagnosis", "unit_id": 16,
             "quote": "Stable angina, new diagnosis",
             "text": "New diagnosis of stable angina, likely due to underlying "
                      "coronary artery disease."},
            {"category": "diagnosis", "unit_id": 17,
             "quote": "Hypertension, poorly controlled on current regimen",
             "text": "Hypertension, poorly controlled on current regimen."},
            {"category": "medications", "unit_id": 21,
             "quote": "metoprolol 25mg BID for rate control and angina management",
             "text": "Start metoprolol 25 mg twice daily for rate control and "
                      "angina management."},
            {"category": "tests", "unit_id": 26,
             "quote": "exercise stress test to evaluate for inducible ischemia",
             "text": "Order an exercise stress test to evaluate for inducible "
                      "ischemia."},
            {"category": "procedures", "unit_id": 30,
             "quote": "coronary angiography if stress test is positive; deferred pending results",
             "text": "Discussed possible coronary angiography if the stress test "
                      "is positive; deferred pending results."},
            {"category": "follow_up", "unit_id": 36,
             "quote": "Return to clinic in four weeks, on 2026-09-08",
             "text": "Return to clinic in four weeks, on 2026-09-08, to review "
                      "stress test results and reassess blood pressure."},
            {"category": "warning_signs", "unit_id": 39,
             "quote": "call 911 or go to the nearest emergency room immediately",
             "text": "If chest tightness occurs at rest, lasts more than fifteen "
                      "minutes, or comes with sweating or nausea, call 911 or go "
                      "to the ER immediately."},
            {"category": "other", "unit_id": 32,
             "quote": "Reduce dietary sodium intake to less than 2 grams per day",
             "text": "Reduce dietary sodium intake to less than 2 grams per day."},
            # Deliberately bad: the quote is not a substring of unit 33's
            # text at all, so anchor_check must drop it at merge_facts.
            {"category": "other", "unit_id": 33,
             "quote": "this text is not actually present in the unit at all",
             "text": "Deliberately bad fact with a fabricated quote that will "
                      "fail anchor check."},
        ]}
        _write_json(os.path.join(cls.run_dir, "02_facts.1.raw.json"), facts_raw)

        glossary_raw = {"terms": [
            {"term": "Angina", "matched_term": "angina",
             "definition": "Chest pain caused by reduced blood flow to the heart.",
             "source": "llm_proposed"},
            {"term": "Hypertension", "matched_term": "hypertension",
             "definition": "High blood pressure.", "source": "llm_proposed"},
            # Absent from the source document entirely.
            {"term": "Nephrology", "matched_term": "nephrology",
             "definition": "The medical specialty focused on kidney care.",
             "source": "llm_proposed"},
        ]}
        _write_json(os.path.join(cls.run_dir, "02_glossary.raw.json"), glossary_raw)

        _run_ok("anchor_check.py", "--run-dir", cls.run_dir, "--chunk", "1")
        _run_ok("glossary_check.py", "--run-dir", cls.run_dir)
        _run_ok("merge_facts.py", "--run-dir", cls.run_dir)

        facts_doc = _read_json(os.path.join(cls.run_dir, "02_facts.json"))
        cls.facts_by_id = {f["id"]: f for f in facts_doc["facts"]}
        cls.dropped = facts_doc["dropped"]

        def fact_id_for(keyword: str) -> int:
            hits = [f["id"] for f in facts_doc["facts"] if keyword in f["quote"]]
            assert len(hits) == 1, (keyword, hits)
            return hits[0]

        cls.fid_reason = fact_id_for("chest tightness and shortness")
        cls.fid_angina = fact_id_for("Stable angina")
        cls.fid_htn = fact_id_for("Hypertension, poorly controlled")
        cls.fid_med = fact_id_for("metoprolol 25mg")
        cls.fid_test = fact_id_for("exercise stress test")
        cls.fid_procedure = fact_id_for("coronary angiography")
        cls.fid_follow_up = fact_id_for("Return to clinic")
        cls.fid_warning = fact_id_for("call 911")
        cls.fid_sodium = fact_id_for("Reduce dietary sodium")

        # --- Stage 2: assemble (cite_check + numeric_parity) -----------
        plan_raw = {
            "summary": "You have chest tightness and shortness of breath, and "
                        "your blood pressure needs better control.",
            "summary_fact_ids": [cls.fid_reason, cls.fid_htn],
            "reason_for_visit": [
                {"reason": "Chest tightness and shortness of breath",
                 "description": "You've had chest tightness and shortness of "
                                 "breath with activity for about three weeks.",
                 "source_fact_ids": [cls.fid_reason]},
            ],
            "diagnosis": {
                "changed_since_last_visit": "",
                "changed_since_last_visit_fact_ids": [],
                "details": [
                    {"title": "Stable angina",
                     "plain_name": "chest pain from reduced blood flow to the heart",
                     "description": "You have a new diagnosis of stable angina, "
                                     "likely caused by narrowed heart arteries.",
                     "what_it_means_for_you": "Your heart isn't getting enough "
                                               "blood flow during activity.",
                     "severity": "medium", "source_fact_ids": [cls.fid_angina]},
                    {"title": "Hypertension", "plain_name": "high blood pressure",
                     "description": "Your high blood pressure is not well "
                                     "controlled with your current treatment.",
                     "what_it_means_for_you": "Your treatment plan needs to "
                                               "change to better control your "
                                               "blood pressure.",
                     "severity": "medium", "source_fact_ids": [cls.fid_htn]},
                ],
            },
            "medications": [
                # Dosage deliberately wrong (fact says 25 mg): numeric_parity
                # must flag this, and review/correct must fix it.
                {"title": "Metoprolol", "plain_name": "metoprolol",
                 "why": "To control your heart rate and manage chest pain.",
                 "dosage": "50 mg", "frequency": "twice a day", "timing": "",
                 "duration": "", "instructions": "", "side_effects_to_watch": "",
                 "change": "New medication", "status": "to_do",
                 "source_fact_ids": [cls.fid_med]},
            ],
            "tests": [
                {"title": "Exercise stress test", "plain_name": "",
                 "why": "To check for reduced blood flow during exercise.",
                 "description": "A test that monitors your heart while you exercise.",
                 "preparation": "", "status": "to_do", "source_fact_ids": [cls.fid_test]},
                # Deliberately uncited (no such fact id exists): cite_check
                # must drop this item entirely.
                {"title": "Unrelated uncited test", "plain_name": "", "why": None,
                 "description": "This item has no valid citation and should be dropped.",
                 "preparation": "", "status": "to_do", "source_fact_ids": [999]},
            ],
            "procedures": [
                {"title": "Coronary angiography",
                 "plain_name": "a heart artery imaging test",
                 "why": "To look closer at your heart arteries if the stress "
                        "test shows a problem.",
                 "what_to_expect": "This test may be done if your stress test "
                                    "results are positive; it has not been "
                                    "scheduled yet.",
                 "timeframe": "To be decided", "status": "to_do",
                 "source_fact_ids": [cls.fid_procedure]},
            ],
            # Deliberately left out (missed the sodium fact entirely), so
            # review-coverage below has something genuine to flag.
            "other": [],
            "follow_up": [
                {"time_frame": "In four weeks",
                 "description": "Return to review your stress test results and blood pressure.",
                 "status": "to_do", "source_fact_ids": [cls.fid_follow_up]},
            ],
            "warning_signs": [
                {"symptom": "Chest tightness at rest or lasting more than fifteen minutes",
                 "what_it_might_mean": "This could be a sign of a heart attack.",
                 "what_to_do": "Call 911 or go to the nearest emergency room immediately.",
                 "urgency": "emergency", "related_to": "",
                 "source_fact_ids": [cls.fid_warning]},
            ],
            "questions": ["Will I need the angiography procedure?"],
            "low_priority": [],
        }
        _write_json(os.path.join(cls.run_dir, "03_plan.raw.json"), plan_raw)

        _run_ok("cite_check.py", "--run-dir", cls.run_dir)
        cls.draft = _read_json(os.path.join(cls.run_dir, "03_plan.draft.json"))

        _run_ok("numeric_parity.py", "--run-dir", cls.run_dir)
        cls.flags = _read_json(os.path.join(cls.run_dir, "03_flags.json"))

        # --- Stage 3: review (sanitize_review) --------------------------
        review_raw = {
            "verdict": "needs_correction",
            "corrections": [
                {"op": "correct", "path": "medications[0].dosage", "value": "25 mg"},
                {"op": "not_stated", "path": "tests[0].why"},
            ],
        }
        _write_json(os.path.join(cls.run_dir, "04_review.raw.json"), review_raw)

        coverage_raw = {
            "coverage": [
                {"fact_id": fid, "present": fid != cls.fid_sodium}
                for fid in sorted(cls.facts_by_id)
            ],
        }
        _write_json(os.path.join(cls.run_dir, "04_coverage.raw.json"), coverage_raw)

        _run_ok("sanitize_review.py", "--run-dir", cls.run_dir)
        cls.review = _read_json(os.path.join(cls.run_dir, "04_review.json"))
        cls.coverage = _read_json(os.path.join(cls.run_dir, "04_coverage.json"))

        # --- Stage 4: correct (diff_guard) + assemble-missing (cite_check) --
        corrected = json.loads(json.dumps(cls.draft))  # deep copy
        corrected["medications"][0]["dosage"] = "25 mg"
        corrected["tests"][0]["why"] = None
        _write_json(os.path.join(cls.run_dir, "05_plan.corrected.raw.json"), corrected)

        _run_ok("diff_guard.py", "--run-dir", cls.run_dir, "--strict")
        _run_ok("diff_guard.py", "--run-dir", cls.run_dir)
        cls.corrected_final = _read_json(os.path.join(cls.run_dir, "05_plan.corrected.json"))

        additions_raw = {
            "reason_for_visit": [], "diagnosis_details": [], "medications": [],
            "tests": [], "procedures": [],
            "other": [
                {"title": "Reduce sodium intake",
                 "why": "To help manage your blood pressure.",
                 "steps": ["Keep your sodium intake under 2 grams each day."],
                 "description": "Lowering sodium can help control your blood pressure.",
                 "frequency": "Daily", "duration": "Ongoing", "status": "to_do",
                 "source_fact_ids": [cls.fid_sodium]},
            ],
            "follow_up": [], "warning_signs": [], "low_priority": [],
        }
        _write_json(os.path.join(cls.run_dir, "05_additions.raw.json"), additions_raw)
        _run_ok("cite_check.py", "--run-dir", cls.run_dir, "--additions")
        cls.additions = _read_json(os.path.join(cls.run_dir, "05_additions.json"))

        # --- Stage 5: finalize + audit ----------------------------------
        cls.finalize_result = _run_ok("finalize.py", "--run-dir", cls.run_dir)
        _run_ok("render_audit.py", "--run-dir", cls.run_dir)

        cls.final_plan = _read_json(os.path.join(cls.run_dir, "06_plan.final.json"))
        cls.run_log = _read_json(os.path.join(cls.run_dir, "run.json"))
        with open(os.path.join(cls.run_dir, "report.html"), "r", encoding="utf-8") as f:
            cls.html_text = f.read()
        with open(os.path.join(cls.run_dir, "report.md"), "r", encoding="utf-8") as f:
            cls.md_text = f.read()
        with open(os.path.join(cls.run_dir, "report.audit.md"), "r", encoding="utf-8") as f:
            cls.audit_text = f.read()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # --- file presence ----------------------------------------------------

    def test_every_expected_file_exists(self):
        expected = [
            "01_units.json", "01_units.1.txt",
            "02_facts.1.raw.json", "02_facts.json", "02_facts.txt",
            "02_glossary.raw.json", "02_glossary.json",
            "03_plan.raw.json", "03_plan.draft.json", "03_flags.json",
            "04_review.raw.json", "04_review.json",
            "04_coverage.raw.json", "04_coverage.json",
            "05_plan.corrected.raw.json", "05_plan.corrected.json",
            "05_additions.raw.json", "05_additions.json",
            "06_plan.final.json",
            "report.md", "report.html", "report.audit.md",
            "run.json",
        ]
        for name in expected:
            path = os.path.join(self.run_dir, name)
            self.assertTrue(os.path.isfile(path), f"missing {name}")

    # --- grounding / merge --------------------------------------------------

    def test_bad_fact_was_dropped_at_merge(self):
        self.assertEqual(len(self.dropped), 1)
        self.assertEqual(self.dropped[0]["reason"], "quote_not_in_unit")

    def test_nine_facts_survived(self):
        self.assertEqual(len(self.facts_by_id), 9)

    # --- schema validation ---------------------------------------------------

    def test_final_plan_matches_schema(self):
        errors = validate.validate(self.final_plan, validate.load_schema("care_plan"))
        self.assertEqual(errors, [])

    # --- cite_check / numeric_parity -----------------------------------------

    def test_uncited_test_item_was_dropped(self):
        titles = [t["title"] for t in self.draft["tests"]]
        self.assertNotIn("Unrelated uncited test", titles)
        self.assertEqual(len(self.draft["tests"]), 1)

    def test_numeric_parity_flags_dosage_mismatch(self):
        paths = [m["path"] for m in self.flags["numeric_parity"]]
        self.assertIn("medications[0].dosage", paths)

    # --- review / correct -----------------------------------------------------

    def test_corrected_dosage_applied(self):
        self.assertEqual(self.corrected_final["medications"][0]["dosage"], "25 mg")

    def test_not_stated_why_applied(self):
        self.assertIsNone(self.corrected_final["tests"][0]["why"])

    # --- coverage / additions --------------------------------------------------

    def test_sodium_fact_was_missing(self):
        self.assertEqual(self.coverage["missing"], [self.fid_sodium])

    def test_addition_cites_only_missing_fact(self):
        self.assertEqual(len(self.additions["other"]), 1)
        self.assertEqual(self.additions["other"][0]["source_fact_ids"], [self.fid_sodium])

    # --- run log ----------------------------------------------------------------

    def test_run_log_has_every_stage_non_failed(self):
        stages = self.run_log["stages"]
        for stage in EXPECTED_STAGES:
            self.assertIn(stage, stages, f"missing stage {stage!r}")
            self.assertNotEqual(stages[stage]["status"], "failed", stage)

    # --- rendered reports ---------------------------------------------------------

    def test_corrected_dosage_in_reports_wrong_one_absent(self):
        self.assertIn("25 mg", self.html_text)
        self.assertIn("25 mg", self.md_text)
        self.assertNotIn("50 mg", self.html_text)
        self.assertNotIn("50 mg", self.md_text)

    def test_addition_appears_in_reports(self):
        self.assertIn("sodium", self.html_text.lower())
        self.assertIn("sodium", self.md_text.lower())

    def test_html_hides_internals_outside_embedded_json(self):
        body = _body_only(self.html_text)
        self.assertNotIn("source_fact_ids", body)
        self.assertNotRegex(body, r"\[\d+\]")

    def test_billing_line_absent_from_reports(self):
        self.assertNotIn("CPT 99214", self.html_text)
        self.assertNotIn("CPT 99214", self.md_text)

    def test_audit_has_provenance_line(self):
        self.assertIn("synthetic-visit-note.txt:1:", self.audit_text)


class TestPipelineNothingToCorrect(unittest.TestCase):
    """The "nothing to correct, nothing missing" path: correct and
    assemble-missing are both skipped, finalize succeeds, and no notice is
    added."""

    def test_skip_path(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run-nothing")
            os.makedirs(run_dir)
            run_id = _runfix.make_run_dir(run_dir)

            coverage_doc = _read_json(os.path.join(run_dir, "04_coverage.json"))
            fact_ids = sorted(c["fact_id"] for c in coverage_doc["coverage"])
            _write_json(os.path.join(run_dir, "04_coverage.json"), {
                "schema_version": "1.0", "plugin_version": "0.1.0", "run_id": run_id,
                "coverage": [{"fact_id": fid, "present": True} for fid in fact_ids],
                "missing": [],
            })
            # No misses -> no additions file, mirroring the real dispatcher
            # skipping the assemble-missing agent entirely.
            additions_path = os.path.join(run_dir, "05_additions.json")
            if os.path.isfile(additions_path):
                os.remove(additions_path)

            _write_json(
                os.path.join(run_dir, "04_review.raw.json"),
                {"verdict": "pass", "corrections": []},
            )
            _run_ok("sanitize_review.py", "--run-dir", run_dir, "--only", "review")

            _run_ok("diff_guard.py", "--run-dir", run_dir)
            _run_ok("cite_check.py", "--run-dir", run_dir, "--additions")
            _run_ok("finalize.py", "--run-dir", run_dir)

            run_log = _read_json(os.path.join(run_dir, "run.json"))
            self.assertEqual(run_log["stages"]["correct"]["status"], "skipped")
            self.assertEqual(run_log["stages"]["assemble_missing"]["status"], "skipped")

            final_plan = _read_json(os.path.join(run_dir, "06_plan.final.json"))
            self.assertEqual(final_plan["notices"], [])
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "report.html")))
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "report.md")))


if __name__ == "__main__":
    unittest.main()
