"""Numeric tokenizer (scripts/numbers.py), moved unchanged from numeric_parity."""

import os
import subprocess
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import check_draft  # noqa: E402

numbers = check_draft.numbers


class TestExtractNumberTokens(unittest.TestCase):
    def test_number_with_unit_word(self):
        self.assertEqual(numbers.extract_number_tokens("metoprolol 25 mg twice daily"), Counter({("25", "mg"): 1}))

    def test_preserves_multiplicity(self):
        self.assertEqual(
            numbers.extract_number_tokens("25 mg plus another 25 mg"),
            Counter({("25", "mg"): 2}),
        )

    def test_dates_and_times_are_excluded(self):
        text = "Seen on 4/12/2026 at 10:30 and again March 3rd."
        self.assertEqual(numbers.extract_number_tokens(text), Counter())

    def test_slash_pair_with_known_unit_is_a_ratio_not_a_date(self):
        self.assertEqual(numbers.extract_number_tokens("take 1/2 tablet"), Counter({("1/2", "tablet"): 1}))

    def test_blood_pressure_shape_is_kept(self):
        self.assertEqual(numbers.extract_number_tokens("BP 155/99"), Counter({("155/99", ""): 1}))

    def test_formatting_is_normalized(self):
        tokens = numbers.extract_number_tokens("1,000 units, 0.50 mg, 007 days")
        self.assertEqual(tokens, Counter({("1000", "units"): 1, ("0.5", "mg"): 1, ("7", "days"): 1}))

    def test_ranges_are_one_token(self):
        self.assertEqual(numbers.extract_number_tokens("5 - 10 mg"), Counter({("5-10", "mg"): 1}))

    def test_unit_words_are_bounded(self):
        tokens = numbers.extract_number_tokens("3 extraordinarilylongword")
        self.assertEqual(list(tokens), [("3", "extraordinarily")])

    def test_percent_unit(self):
        self.assertEqual(numbers.extract_number_tokens("SpO2 100%"), Counter({("2", ""): 1, ("100", "%"): 1}))


class TestBacking(unittest.TestCase):
    def test_unbacked_tokens_are_listed_once_in_order(self):
        backing = numbers.backing_tokens(["Start metoprolol 25 mg twice daily.", "Follow up in 3 months."])
        self.assertEqual(numbers.unbacked_tokens("Take 50 mg, then 50 mg, for 3 months", backing), ["50 mg"])

    def test_presence_is_enough(self):
        backing = numbers.backing_tokens(["25 mg"])
        self.assertEqual(numbers.unbacked_tokens("25 mg in the morning and 25 mg at night", backing), [])

    def test_token_str(self):
        self.assertEqual(numbers.token_str("25", "mg"), "25 mg")
        self.assertEqual(numbers.token_str("25", ""), "25")


class TestStdlibShadowing(unittest.TestCase):
    def test_stdlib_numeric_modules_still_import_with_scripts_first_on_path(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import numbers; "
            "import fractions, decimal, statistics; "
            "assert hasattr(numbers, 'extract_number_tokens'); "
            "print(fractions.Fraction(1, 2) + 1, statistics.mean([1, 2]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, _paths.SCRIPTS_DIR], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["3/2", "1.5"])


if __name__ == "__main__":
    unittest.main()
