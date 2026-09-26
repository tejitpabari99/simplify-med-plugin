import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import plan_paths  # noqa: E402
import render_audit  # noqa: E402
from test_plan_view import _fixture_plan, _minimal_plan  # noqa: E402

ER_SOURCE = os.path.join(_paths.FIXTURE_DOCUMENTS_DIR, "synthetic-er-visit.txt")


def _write_json(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def _er_units():
    """01_units.json for the synthetic ER note: one unit per non-blank line,
    numbered from 1, with URL-only lines marked skipped."""
    units = []
    with open(ER_SOURCE, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            unit = {
                "id": len(units) + 1,
                "file": "synthetic-er-visit.txt",
                "page": 1,
                "line": line_number,
                "text": text,
                "extraction_method": "pasted",
            }
            if text.startswith("https://"):
                unit["skip"] = "url"
            units.append(unit)
    return {"schema_version": "3.0", "plugin_version": "0.1.0", "run_id": "fixture-er-visit", "units": units}


def _run_log(run_id="fixture-er-visit"):
    return {
        "run_id": run_id,
        "stages": {
            "unitize": {"status": "ok", "attempts": 1, "checks": {"units": 54, "skipped": 6}},
            "write": {"status": "ok", "attempts": 2, "checks": {}},
            "check": {"status": "ok", "attempts": 1, "checks": {"word_count": 175}},
            "verify": {"status": "ok", "attempts": 1},
            "settle": {"status": "ok", "attempts": 1, "checks": {"operations": 0}},
            "finalize": {"status": "ok", "attempts": 1, "checks": {}},
        },
    }


class TestRenderAudit(unittest.TestCase):
    def test_every_visible_item_is_followed_by_its_cited_units(self):
        plan = _fixture_plan()
        text = render_audit.render(plan, _er_units(), _run_log())
        self.assertTrue(text.startswith("# Audit view — fixture-er-visit\n"))
        self.assertIn("Report: Your ER visit, simplified", text)
        paths = [path for path, _item in plan_paths.visible_items(plan)]
        positions = [text.index(f"### {path}\n") for path in paths]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "### findings[0]\n\nBrain MRI: Normal. No stroke was seen.\n"
            '  - unit 40 · synthetic-er-visit.txt:1:40 · extraction=pasted · '
            '"IMPRESSION: Normal noncontrast brain MRI. No acute infarct."\n',
            text,
        )
        self.assertIn(
            "### medicines.none_statement\n\nYou were not prescribed any new medicines.\n"
            '  - unit 52 · synthetic-er-visit.txt:1:52 · extraction=pasted · "No new medications prescribed."\n',
            text,
        )
        self.assertIn("### diagnoses[1]\n\nTingling in your left arm/hand\n", text)
        self.assertNotIn("fact ", text)

    def test_stage_table_and_coverage_follow_the_items(self):
        text = render_audit.render(_fixture_plan(), _er_units(), _run_log())
        self.assertLess(text.index("## Visible items"), text.index("## Protected content coverage"))
        self.assertLess(text.index("## Protected content coverage"), text.index("## Stages"))
        self.assertIn("- follow_up: shown · units 53", text)
        self.assertIn("| Stage | Status | Attempts | Key checks |", text)
        self.assertIn("| unitize | ok | 1 | units=54; skipped=6 |", text)
        self.assertIn("| verify | ok | 1 |  |", text)
        stage_rows = [line.split("|")[1].strip() for line in text.splitlines() if line.startswith("| ") and "Stage" not in line]
        self.assertEqual(stage_rows, ["unitize", "write", "check", "verify", "settle", "finalize"])

    def test_unknown_and_skipped_units_are_flagged(self):
        plan = _minimal_plan()
        plan["why_you_went"]["unit_ids"] = [3, 999]
        text = render_audit.render(plan, _er_units(), _run_log("run-1"))
        self.assertIn("  - unit 3 · synthetic-er-visit.txt:1:3 · extraction=pasted · skip=url ·", text)
        self.assertIn("  - unit 999 · (unknown unit)", text)

    def test_run_log_is_read_tolerantly(self):
        run_log = {"stages": {"write": "garbled", "check": {"status": "failed", "checks": "not-a-dict"}, "a|b": {}}}
        text = render_audit.render(_minimal_plan(), {"units": []}, run_log)
        self.assertIn("| write |  |  |  |", text)
        self.assertIn("| check | failed |  |  |", text)
        self.assertIn("| a\\|b |  |  |  |", text)
        self.assertIn("(no stages recorded)", render_audit.render(_minimal_plan(), {"units": []}, {}))

    def test_cli_writes_audit_without_mutating_inputs(self):
        plan = _fixture_plan()
        with tempfile.TemporaryDirectory() as run_dir:
            for name, document in (
                ("05_plan.final.json", plan),
                ("01_units.json", _er_units()),
                ("run.json", _run_log()),
            ):
                _write_json(os.path.join(run_dir, name), document)
            before = copy.deepcopy(plan)
            rc = render_audit.main(["--run-dir", run_dir])
            self.assertEqual(rc, 0)
            with open(os.path.join(run_dir, "05_plan.final.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), before)
            with open(os.path.join(run_dir, "report.audit.md"), encoding="utf-8") as handle:
                self.assertIn("### return_precautions[0]", handle.read())

    def test_cli_rejects_unfinished_run(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_json(os.path.join(run_dir, "05_plan.final.json"), _fixture_plan())
            _write_json(os.path.join(run_dir, "01_units.json"), _er_units())
            _write_json(
                os.path.join(run_dir, "run.json"),
                {"run_id": "fixture-er-visit", "stages": {"settle": {"status": "ok"}}},
            )
            script = os.path.join(_paths.SCRIPTS_DIR, "render_audit.py")
            result = subprocess.run(
                [sys.executable, script, "--run-dir", run_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("completed final report", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.audit.md")))


if __name__ == "__main__":
    unittest.main()
