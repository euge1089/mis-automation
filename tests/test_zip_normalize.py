"""Tests for ZIP normalization (no DB required)."""
import unittest

from backend.zip_normalize import normalize_us_zip_5


class TestNormalizeUsZip5(unittest.TestCase):
    def test_four_digit_pads(self):
        self.assertEqual(normalize_us_zip_5("2127"), "02127")
        self.assertEqual(normalize_us_zip_5(" 2127 "), "02127")

    def test_already_five(self):
        self.assertEqual(normalize_us_zip_5("02127"), "02127")

    def test_zip_plus_four(self):
        self.assertEqual(normalize_us_zip_5("02127-1234"), "02127")

    def test_none_empty(self):
        self.assertIsNone(normalize_us_zip_5(None))
        self.assertIsNone(normalize_us_zip_5(""))
        self.assertIsNone(normalize_us_zip_5("   "))

    def test_leading_zero_zip_three_digit_prefix(self):
        self.assertEqual(normalize_us_zip_5("00601"), "00601")


if __name__ == "__main__":
    unittest.main()
