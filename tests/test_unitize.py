import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import _version  # noqa: E402
import protected  # noqa: E402
import runlog  # noqa: E402
import unitize  # noqa: E402
import validate  # noqa: E402

UNITIZE_PY = os.path.join(_paths.SCRIPTS_DIR, "unitize.py")
ER_VISIT = os.path.join(_paths.FIXTURE_DOCUMENTS_DIR, "synthetic-er-visit.txt")


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


class TestUnitizeFunction(unittest.TestCase):
    """Exercise unitize.main() in-process for speed; a couple of CLI-level
    tests below confirm the `python3 unitize.py ...` invocation works too."""

    def test_two_files_form_feed_pages_and_id_continuity(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            b = os.path.join(d, "b.txt")
            _write(a, "Line one\nLine two\n\x0cSecond page line\n")
            _write(b, "File b line1\nFile b line2\n")

            run_dir = os.path.join(d, "run")
            rc = unitize.main([
                "--run-dir", run_dir,
                "--input", f"{a}:native",
                "--input", f"{b}:ocr",
            ])
            self.assertEqual(rc, 0)

            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)

            ids = [u["id"] for u in units_doc["units"]]
            self.assertEqual(ids, list(range(1, len(ids) + 1)))

            # a.txt has two pages; page numbers reset per page (line resets too).
            pages = {u["id"]: u["page"] for u in units_doc["units"]}
            self.assertEqual(pages[1], 1)
            self.assertEqual(pages[2], 1)
            self.assertEqual(pages[3], 2)  # "Second page line"
            lines = {u["id"]: u["line"] for u in units_doc["units"]}
            self.assertEqual(lines[3], 1)  # line restarts at 1 on the new page

            # extraction_method copied from the input.
            methods = {u["id"]: u["extraction_method"] for u in units_doc["units"]}
            self.assertEqual(methods[1], "native")
            self.assertEqual(methods[4], "ocr")

    def test_blank_lines_advance_line_but_emit_no_unit(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "first\n\n\nfourth\n")
            run_dir = os.path.join(d, "run")
            rc = unitize.main(["--run-dir", run_dir, "--input", a])
            self.assertEqual(rc, 0)
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            texts = [(u["line"], u["text"]) for u in units_doc["units"]]
            # "first" is line 1; "fourth" is line 4 (lines 2, 3 were blank).
            self.assertEqual(texts, [(1, "first"), (4, "fourth")])

    def test_default_method_is_native(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "hello\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a])
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            self.assertEqual(units_doc["units"][0]["extraction_method"], "native")

    def test_run_json_is_the_only_input_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "hello\nworld\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a])

            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            errors = validate.validate(units_doc, validate.load_schema("units"))
            self.assertEqual(errors, [])

            self.assertFalse(os.path.exists(os.path.join(run_dir, "00_input", "manifest.json")))
            run_doc = runlog.read(run_dir)
            errors = validate.validate(run_doc, validate.load_schema("run"))
            self.assertEqual(errors, [])
            self.assertEqual(run_doc["inputs"][0]["sha256"], hashlib.sha256(b"hello\nworld\n").hexdigest())

    def test_reusing_explicit_directory_creates_fresh_identity_and_clears_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            source = os.path.join(d, "a.txt")
            _write(source, "same clinical input\n")
            run_dir = os.path.join(d, "run")

            self.assertEqual(unitize.main(["--run-dir", run_dir, "--input", source]), 0)
            first = runlog.read(run_dir)
            first_digest = first["stages"]["unitize"]["checks"]["input_digest"]
            _write(os.path.join(run_dir, "03_stale.json"), "stale")

            self.assertEqual(unitize.main(["--run-dir", run_dir, "--input", source]), 0)
            second = runlog.read(run_dir)

            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first_digest, second["stages"]["unitize"]["checks"]["input_digest"])
            self.assertFalse(os.path.exists(os.path.join(run_dir, "03_stale.json")))
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["run_id"], second["run_id"])

    def test_duplicate_basenames_are_suffixed(self):
        with tempfile.TemporaryDirectory() as d:
            sub1 = os.path.join(d, "sub1")
            sub2 = os.path.join(d, "sub2")
            os.makedirs(sub1)
            os.makedirs(sub2)
            a = os.path.join(sub1, "note.txt")
            b = os.path.join(sub2, "note.txt")
            _write(a, "hello from one\n")
            _write(b, "hello from two\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a, "--input", b])
            entries = sorted(os.listdir(os.path.join(run_dir, "00_input")))
            self.assertIn("note.txt", entries)
            self.assertIn("note-2.txt", entries)

    def test_runs_dir_mode_creates_run_id_directory_and_prints_it(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "hello\n")
            runs_dir = os.path.join(d, "runs")
            result = subprocess.run(
                [sys.executable, UNITIZE_PY, "--runs-dir", runs_dir, "--input", a],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            printed_dir = result.stdout.strip().splitlines()[-1]
            self.assertTrue(os.path.isdir(printed_dir))
            self.assertTrue(os.path.dirname(printed_dir) == runs_dir)
            self.assertRegex(
                result.stdout.strip().splitlines()[0],
                r"^unitize: ok \| files=1 units=1 skipped=0 protected=0$",
            )

    def test_fatal_on_all_blank_document(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "\n\n\n")
            run_dir = os.path.join(d, "run")
            rc = unitize.main(["--run-dir", run_dir, "--input", a])
            self.assertEqual(rc, 1)

    def test_fatal_on_empty_input_file(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "")
            run_dir = os.path.join(d, "run")
            rc = unitize.main(["--run-dir", run_dir, "--input", a])
            self.assertEqual(rc, 1)

    def test_run_log_records_unitize_stage(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "hello\nworld\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a])
            data = runlog.read(run_dir)
            self.assertEqual(data["stages"]["unitize"]["status"], "ok")
            checks = data["stages"]["unitize"]["checks"]
            self.assertEqual(checks["units"], 2)
            self.assertEqual(checks["files"], 1)
            self.assertEqual(checks["skipped"], 0)
            self.assertEqual(checks["protected"], 0)
            self.assertEqual(data["stages"]["unitize"]["attempts"], 1)
            self.assertEqual(
                [artifact["path"] for artifact in data["stages"]["unitize"]["artifacts"]],
                ["00_input/a.txt", "01_units.json", "01_source.txt", "01_protected.json"],
            )

    def test_fatal_when_every_line_is_boilerplate(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "https://portal.example.test/x\nPage 1 of 2\n")
            run_dir = os.path.join(d, "run")
            self.assertEqual(unitize.main(["--run-dir", run_dir, "--input", a]), 1)
            self.assertEqual(runlog.read(run_dir)["stages"]["unitize"]["status"], "failed")
            self.assertFalse(os.path.exists(os.path.join(run_dir, "01_source.txt")))

    def test_chunking_is_gone(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "p1l1\np1l2\n\x0cp2l1\np2l2\n")
            run_dir = os.path.join(d, "run")
            with self.assertRaises(SystemExit), redirect_stdout(StringIO()), mock.patch("sys.stderr", StringIO()):
                unitize.main(["--run-dir", run_dir, "--input", a, "--chunk-size", "2"])
            self.assertEqual(unitize.main(["--run-dir", run_dir, "--input", a]), 0)
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                self.assertNotIn("chunks", json.load(f))
            self.assertEqual(
                sorted(name for name in os.listdir(run_dir) if name.startswith("01_")),
                ["01_protected.json", "01_source.txt", "01_units.json"],
            )


class TestBoilerplateAndSource(unittest.TestCase):
    """Boilerplate suppression, 01_source.txt, 01_protected.json, stdout."""

    def _unitize(self, d: str, *contents: str) -> tuple[str, str]:
        args = []
        for index, content in enumerate(contents, start=1):
            path = os.path.join(d, f"doc{index}.txt")
            _write(path, content)
            args += ["--input", path]
        run_dir = os.path.join(d, "run")
        out = StringIO()
        with redirect_stdout(out):
            rc = unitize.main(["--run-dir", run_dir, *args])
        self.assertEqual(rc, 0)
        return run_dir, out.getvalue()

    @staticmethod
    def _read(run_dir: str, name: str):
        with open(os.path.join(run_dir, name), "r", encoding="utf-8") as f:
            return json.load(f) if name.endswith(".json") else f.read()

    def test_skip_reasons_and_contiguous_ids(self):
        text = (
            "Portal header text\n"
            "https://portal.example.test/visits/1\n"
            "  <www.example.test/a?b=1>  \n"
            "Page 1 of 3\n"
            "Real line one\n"
            "Portal   header   text\n"   # whitespace-normalized repeat
            "  page 2 / 3 \n"
            "Short\n"
            "Short\n"                   # < 8 chars: kept
            "portal header text\n"      # case differs: kept
            "See https://example.test for details\n"  # not URL-only: kept
        )
        with tempfile.TemporaryDirectory() as d:
            run_dir, _ = self._unitize(d, text)
            units = self._read(run_dir, "01_units.json")["units"]
            self.assertEqual([u["id"] for u in units], list(range(1, 12)))
            self.assertEqual(
                {u["id"]: u["skip"] for u in units if "skip" in u},
                {2: "url", 3: "url", 4: "page_counter", 6: "repeat", 7: "page_counter"},
            )

    def test_repeat_across_files_and_pages_keeps_first_occurrence(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir, _ = self._unitize(d, "Clinic footer line\nA\x0cClinic footer line\n", "Clinic footer line\n")
            units = self._read(run_dir, "01_units.json")["units"]
            self.assertEqual([u.get("skip") for u in units], [None, None, "repeat", "repeat"])

    def test_repeated_protected_line_is_not_skipped(self):
        # Two studies with the same impression must both stay citable.
        with tempfile.TemporaryDirectory() as d:
            run_dir, _ = self._unitize(
                d,
                "CT HEAD\nIMPRESSION: No acute intracranial abnormality.\n"
                "MRI BRAIN\nIMPRESSION: No acute intracranial abnormality.\n",
            )
            units = self._read(run_dir, "01_units.json")["units"]
            self.assertEqual([u.get("skip") for u in units], [None, None, None, None])
            doc = self._read(run_dir, "01_protected.json")
            self.assertEqual(doc["categories"]["diagnoses"], [2, 4])

    def test_source_txt_headers_and_skipped_units_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir, _ = self._unitize(
                d,
                "First line here\nPage 1 of 2\n\x0chttps://x.test\n\x0cThird page line\n",
                "Other file line\n",
            )
            self.assertEqual(
                self._read(run_dir, "01_source.txt"),
                "=== doc1.txt page 1 ===\n"
                "[1] First line here\n"
                "=== doc1.txt page 3 ===\n"
                "[4] Third page line\n"
                "=== doc2.txt page 1 ===\n"
                "[5] Other file line\n",
            )

    def test_protected_json_skips_boilerplate_and_validates(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir, out = self._unitize(
                d,
                "Follow-up with your doctor in 2 weeks.\n"
                "Disposition: discharged home.\n"
                "Portal footer line\n"
                "Portal footer line\n",
            )
            doc = self._read(run_dir, "01_protected.json")
            self.assertEqual(validate.validate(doc, validate.load_schema("protected")), [])
            self.assertEqual(doc["schema_version"], _version.SCHEMA_VERSION)
            self.assertEqual(doc["run_id"], runlog.read(run_dir)["run_id"])
            self.assertEqual(list(doc["categories"]), list(protected.CATEGORIES))
            self.assertEqual(doc["categories"]["follow_up"], [1])
            self.assertEqual(doc["categories"]["disposition"], [2])
            self.assertEqual(out.splitlines(), [
                "unitize: ok | files=1 units=4 skipped=1 protected=2",
                run_dir,
            ])
            checks = runlog.read(run_dir)["stages"]["unitize"]["checks"]
            self.assertEqual((checks["units"], checks["skipped"], checks["protected"]), (4, 1, 2))
            self.assertEqual(checks["skipped_by_reason"], {"repeat": 1})

    def test_er_fixture_outputs_validate(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            with redirect_stdout(StringIO()):
                self.assertEqual(unitize.main(["--run-dir", run_dir, "--input", ER_VISIT]), 0)
            units_doc = self._read(run_dir, "01_units.json")
            self.assertEqual(units_doc["schema_version"], _version.SCHEMA_VERSION)
            self.assertEqual(validate.validate(units_doc, validate.load_schema("units")), [])
            source = self._read(run_dir, "01_source.txt")
            self.assertTrue(source.startswith("=== synthetic-er-visit.txt page 1 ===\n[1] # SYNTHETIC DOCUMENT"))
            self.assertNotIn("https://", source)
            self.assertNotIn("Page 2 of 3", source)
            self.assertEqual(source.count("Patient Portal - Visit Summary"), 1)
            self.assertEqual(source.count("ordering provider"), 1)


if __name__ == "__main__":
    unittest.main()
