import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import render_md  # noqa: E402
from test_plan_view import NOTICE_MARKER, _fixture_plan, _glossary_doc, _minimal_plan  # noqa: E402


# PRD §3 target for the ER case, one bullet per line.
ER_GOLDEN = """\
# Your ER visit, simplified

You went to the ER because you had a headache for several days, neck pain, tingling in your left hand, and an abnormal heart tracing at urgent care.

## What did they find?

The important tests were reassuring:

- **Brain MRI:** Normal. No stroke was seen.
- **CT and CT angiogram of your head and neck:** Normal. No blocked blood vessels, aneurysm, or artery tear was found.
- **Neurologic exam:** Normal except for slightly different sensation in your left palm.
- **Blood tests:** The ER doctor described them as unremarkable.
- **Heart tracing:** It showed a right bundle branch block and first-degree AV block, but the ER doctor did not think it showed a heart attack or other acute loss of blood flow to the heart.

**The ER diagnosed you with:**

- Acute headache
- Tingling in your left arm/hand

They did not find an emergency cause for your symptoms, and you were discharged in stable condition.

## What should you do now?

- Schedule a primary-care appointment to follow up on the headache, hand tingling, and abnormal heart tracing.
- You were not prescribed any new medicines.

## When should you go back to the ER?

- Return to the ER if you develop any new or worsening symptoms.
"""


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def _write_completed_run(run_dir, run_id="fixture-er-visit"):
    _write_json(os.path.join(run_dir, "run.json"), {"run_id": run_id, "stages": {"finalize": {"status": "ok"}}})


class TestRenderMd(unittest.TestCase):
    def test_er_fixture_matches_prd_target(self):
        self.assertEqual(render_md.render(_fixture_plan()), ER_GOLDEN)

    def test_report_has_no_internal_data_or_legacy_artifacts(self):
        text = render_md.render(_fixture_plan())
        for hidden in (
            NOTICE_MARKER, "Reading level:", "unit_ids", "coverage", "fixture-er-visit",
            "Already done", "To do", "_Instruction_", "_Test_", "Medical terms explained",
        ):
            self.assertNotIn(hidden, text)
        for line in text.splitlines():
            self.assertNotIn(line.strip(), {"-", "- ", "—", "- —"})
            self.assertFalse(line.startswith("  "), line)

    def test_other_visit_type_headings_medicines_and_questions(self):
        plan = _minimal_plan("clinic_visit")
        plan["diagnoses"] = [
            {"name": "Strep throat", "plain_name": "strep throat", "unit_ids": [2]},
            {"name": "Otitis media", "plain_name": "ear infection", "unit_ids": [2]},
        ]
        plan["medicines"] = {
            "items": [{"name": "Amoxicillin", "change": "start", "text": "Take it twice a day for 10 days.", "unit_ids": [3]}],
            "none_statement": None,
        }
        plan["return_precautions"] = [{"text": "Get help right away if you cannot swallow.", "unit_ids": [4]}]
        plan["questions"] = [{"question": "When can I go back to school?", "unit_ids": [5]}]
        self.assertEqual(
            render_md.render(plan),
            "# Your visit, simplified\n\n"
            "You came in for a check-up.\n\n"
            "## What did they find?\n\n"
            "**Diagnosed with:**\n\n"
            "- Strep throat\n"
            "- Otitis media (ear infection)\n\n"
            "## What should you do now?\n\n"
            "- **Amoxicillin:** Take it twice a day for 10 days.\n\n"
            "## When to get help right away\n\n"
            "- Get help right away if you cannot swallow.\n\n"
            "## Questions you may want to ask\n\n"
            "- When can I go back to school?\n",
        )

    def test_minimal_plan_renders_only_the_lead(self):
        self.assertEqual(
            render_md.render(_minimal_plan("test_results")),
            "# Your test results, simplified\n\nYou came in for a check-up.\n",
        )

    def test_glossary_only_when_passed(self):
        text = render_md.render(_fixture_plan(), glossary=_glossary_doc())
        self.assertTrue(text.startswith(ER_GOLDEN.rstrip("\n")))
        self.assertIn("## Medical terms explained", text)
        self.assertIn("- **Bundle branch block:** A delay in the electrical signal", text)

    def test_cli_writes_only_default_markdown(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "05_plan.final.json"), _fixture_plan())
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(os.listdir(run_dir)), ["05_plan.final.json", "report.md", "run.json"])
            with open(os.path.join(run_dir, "report.md"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), ER_GOLDEN)

    def test_cli_rejects_non_final_plan(self):
        with tempfile.TemporaryDirectory() as run_dir:
            plan_path = os.path.join(run_dir, "04_plan.settled.json")
            _write_json(plan_path, _fixture_plan())
            _write_completed_run(run_dir)
            script = os.path.join(_paths.SCRIPTS_DIR, "render_md.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir, "--plan", plan_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.md")))


if __name__ == "__main__":
    unittest.main()
