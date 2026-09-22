import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import readability  # noqa: E402


class TestReadability(unittest.TestCase):
    def test_none_under_thirty_words(self):
        text = "The cat sat on the mat. It was a short day."
        self.assertLess(len(text.split()), 30)
        self.assertIsNone(readability.fk_grade(text))

    def test_none_for_empty_text(self):
        self.assertIsNone(readability.fk_grade(""))
        self.assertIsNone(readability.fk_grade(None))

    def test_simple_repetitive_text_is_low_grade(self):
        # All one-syllable words, short sentences: should read as very easy.
        text = "The cat sat on the mat. The dog ran to the log. " * 5
        grade = readability.fk_grade(text)
        self.assertIsNotNone(grade)
        self.assertLess(grade, 4.0)

    def test_known_formula_value(self):
        # 6 sentences of exactly 5 one-syllable words each = 30 words.
        # words/sentence = 5, syllables/word = 1 (each word is one syllable).
        sentence = "Take the pill each day."  # 5 one-syllable words
        text = (sentence + " ") * 6
        words = [w for w in text.split() if any(c.isalpha() for c in w)]
        self.assertEqual(len(words), 30)
        expected = round(0.39 * (30 / 6) + 11.8 * (30 / 30) - 15.59, 1)
        grade = readability.fk_grade(text)
        self.assertAlmostEqual(grade, expected, places=1)

    def test_boundary_at_thirty_words(self):
        word = "cat "
        text29 = (word * 29).strip() + "."
        text30 = (word * 30).strip() + "."
        self.assertIsNone(readability.fk_grade(text29))
        self.assertIsNotNone(readability.fk_grade(text30))

    def test_syllable_heuristic_silent_e(self):
        # "like" -> 1 syllable (silent trailing e dropped)
        self.assertEqual(readability._syllables_in_word("like"), 1)
        # "table" -> "le" preceded by consonant "b": syllable retained -> 2
        self.assertEqual(readability._syllables_in_word("table"), 2)
        # "little" -> 2
        self.assertEqual(readability._syllables_in_word("little"), 2)
        # minimum of 1 even for a word with no vowel groups at all
        self.assertEqual(readability._syllables_in_word("psst"), 1)

    def test_cli_prints_grade(self):
        import subprocess
        import tempfile

        text = "Take the pill each day. " * 10
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            script = os.path.join(_paths.SCRIPTS_DIR, "readability.py")
            result = subprocess.run(
                [sys.executable, script, path], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertRegex(result.stdout.strip(), r"^-?\d+\.\d$")
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
