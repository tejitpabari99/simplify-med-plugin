import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import textnorm  # noqa: E402


class TestNormalizeText(unittest.TestCase):
    def test_accents_stripped_and_lowercased(self):
        self.assertEqual(textnorm.normalize_text("Café Déjà-vu"), "cafe deja-vu")

    def test_whitespace_collapsed_and_stripped(self):
        self.assertEqual(textnorm.normalize_text("  hello   world  \t\n"), "hello world")

    def test_empty_string(self):
        self.assertEqual(textnorm.normalize_text(""), "")

    def test_case_folded(self):
        self.assertEqual(textnorm.normalize_text("METOPROLOL"), "metoprolol")


class TestNormalizeWithOffsets(unittest.TestCase):
    def test_matches_normalize_text(self):
        for text in [
            "Café  Déjà-vu\t noted",
            "  leading and trailing  ",
            "PLAIN text 123",
            "",
            "a\n\nb",
        ]:
            normalized, spans = textnorm.normalize_with_offsets(text)
            self.assertEqual(normalized, textnorm.normalize_text(text))
            self.assertEqual(len(normalized), len(spans))

    def test_offsets_recover_raw_span_for_simple_text(self):
        text = "Hello world"
        normalized, spans = textnorm.normalize_with_offsets(text)
        self.assertEqual(normalized, "hello world")
        # "world" starts at normalized index 6.
        idx = normalized.find("world")
        raw_start = spans[idx][0]
        raw_end = spans[idx + len("world") - 1][1]
        self.assertEqual(text[raw_start:raw_end], "world")

    def test_interior_whitespace_run_collapses_to_one_span(self):
        text = "a    b"  # four spaces
        normalized, spans = textnorm.normalize_with_offsets(text)
        self.assertEqual(normalized, "a b")
        # The single normalized space should span the whole raw run.
        space_span = spans[1]
        self.assertEqual(text[space_span[0]:space_span[1]], "    ")

    def test_accented_char_offset_is_single_raw_char(self):
        text = "café"
        normalized, spans = textnorm.normalize_with_offsets(text)
        self.assertEqual(normalized, "cafe")
        # The final raw char "é" (index 3) produced normalized "e" (index 3).
        self.assertEqual(spans[3], (3, 4))


class TestIsInformative(unittest.TestCase):
    def test_contains_digit(self):
        self.assertTrue(textnorm.is_informative("40 mg"))

    def test_long_word(self):
        self.assertTrue(textnorm.is_informative("warfarin"))

    def test_min_length_floor(self):
        self.assertTrue(textnorm.is_informative("as needed now"))

    def test_short_uninformative(self):
        self.assertFalse(textnorm.is_informative("ok"))

    def test_short_common_word_not_informative(self):
        self.assertFalse(textnorm.is_informative("stop"))


class TestFindNormalized(unittest.TestCase):
    def test_finds_simple_substring(self):
        result = textnorm.find_normalized("world", "Hello world!")
        self.assertEqual(result, (6, 11))
        start, end = result
        self.assertEqual("Hello world!"[start:end], "world")

    def test_finds_across_normalized_whitespace(self):
        haystack = "Continue   metoprolol  25 mg  twice daily"
        result = textnorm.find_normalized("metoprolol 25 mg", haystack)
        self.assertIsNotNone(result)
        start, end = result
        raw = haystack[start:end]
        self.assertEqual(textnorm.normalize_text(raw), "metoprolol 25 mg")

    def test_case_and_accent_insensitive(self):
        result = textnorm.find_normalized("DEJA-VU", "a café déjà-vu moment")
        self.assertIsNotNone(result)

    def test_not_found_returns_none(self):
        self.assertIsNone(textnorm.find_normalized("nonexistent", "some text here"))

    def test_empty_needle_returns_none(self):
        self.assertIsNone(textnorm.find_normalized("   ", "some text here"))


if __name__ == "__main__":
    unittest.main()
