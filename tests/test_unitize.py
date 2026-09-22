import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import runlog  # noqa: E402
import unitize  # noqa: E402
import validate  # noqa: E402

UNITIZE_PY = os.path.join(_paths.SCRIPTS_DIR, "unitize.py")


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

    def test_chunking_page_aligned(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            # Two pages of 2 lines each; chunk size 2 -> each page its own chunk.
            _write(a, "p1l1\np1l2\n\x0cp2l1\np2l2\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a, "--chunk-size", "2"])
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            chunks = units_doc["chunks"]
            self.assertEqual(len(chunks), 2)
            self.assertEqual((chunks[0]["first_id"], chunks[0]["last_id"]), (1, 2))
            self.assertEqual((chunks[1]["first_id"], chunks[1]["last_id"]), (3, 4))
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "01_units.1.txt")))
            self.assertTrue(os.path.isfile(os.path.join(run_dir, "01_units.2.txt")))
            with open(os.path.join(run_dir, "01_units.1.txt"), "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "[1] p1l1\n[2] p1l2\n")

    def test_oversized_page_is_split_at_chunk_size(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "\n".join(f"line{i}" for i in range(1, 8)))  # 7 lines, one page
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a, "--chunk-size", "3"])
            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            chunks = units_doc["chunks"]
            ranges = [(c["first_id"], c["last_id"]) for c in chunks]
            self.assertEqual(ranges, [(1, 3), (4, 6), (7, 7)])
            covered = set()
            for first, last in ranges:
                for i in range(first, last + 1):
                    self.assertNotIn(i, covered)
                    covered.add(i)
            self.assertEqual(covered, {u["id"] for u in units_doc["units"]})

    def test_manifest_and_units_validate_against_schemas(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.txt")
            _write(a, "hello\nworld\n")
            run_dir = os.path.join(d, "run")
            unitize.main(["--run-dir", run_dir, "--input", a])

            with open(os.path.join(run_dir, "01_units.json"), "r", encoding="utf-8") as f:
                units_doc = json.load(f)
            errors = validate.validate(units_doc, validate.load_schema("units"))
            self.assertEqual(errors, [])

            with open(os.path.join(run_dir, "00_input", "manifest.json"), "r", encoding="utf-8") as f:
                manifest_doc = json.load(f)
            errors = validate.validate(manifest_doc, validate.load_schema("manifest"))
            self.assertEqual(errors, [])

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


if __name__ == "__main__":
    unittest.main()
