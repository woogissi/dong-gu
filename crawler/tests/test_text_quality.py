import unittest

from crawler.utils.text_quality import strip_nul_value, text_quality_report


class TextQualityTest(unittest.TestCase):
    def test_strip_nul_value_removes_raw_and_escaped_nul(self) -> None:
        value = {
            "raw": "a\x00b",
            "escaped": "c\\u0000d",
            "items": ["x\x00y", "z\\u0000q"],
        }

        self.assertEqual(
            strip_nul_value(value),
            {
                "raw": "ab",
                "escaped": "cd",
                "items": ["xy", "zq"],
            },
        )

    def test_text_quality_reports_escaped_nul_as_binary_like(self) -> None:
        report = text_quality_report("hello\\u0000world")

        self.assertEqual(report["escaped_nul_count"], 1)
        self.assertIs(report["is_binary_like"], True)
        self.assertIn("contains_nul", report["reason"])
