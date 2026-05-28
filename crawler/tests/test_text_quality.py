import unittest

from crawler.utils.text_quality import (
    attachment_text_quality_report,
    detect_binary_markers,
    document_quality_report,
    strip_nul_value,
    text_quality_report,
)


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

    def test_text_quality_blocks_pdf_binary_markers(self) -> None:
        for marker in ("%PDF", "stream", "endobj", "xref", "%%EOF"):
            with self.subTest(marker=marker):
                report = text_quality_report(f"binary payload {marker} bytes")

                self.assertTrue(report["is_binary_like"])
                self.assertTrue(report["has_binary_marker"])
                self.assertIn("binary_marker", report["reason"])

    def test_text_quality_blocks_hwp_and_ole_markers(self) -> None:
        hwp_report = text_quality_report("HWP Document File\x00BodyText")
        ole_report = text_quality_report("\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload")

        self.assertIn("hwp_binary_marker", hwp_report["binary_markers"])
        self.assertIn("ole_compound_file_marker", ole_report["binary_markers"])
        self.assertTrue(hwp_report["is_binary_like"])
        self.assertTrue(ole_report["is_binary_like"])

    def test_document_quality_checks_table_and_downloaded_attachments(self) -> None:
        report = document_quality_report(
            {
                "normalize": "normal extracted PDF text with application dates",
                "table_text": "xref",
                "downloaded_attachments": [
                    {"attachment_text": "%%EOF"},
                ],
            }
        )

        self.assertTrue(report["is_binary_like"])
        self.assertIn("table_text", report["bad_fields"])
        self.assertIn("downloaded_attachments[1].attachment_text", report["bad_fields"])

    def test_normal_pdf_extracted_text_is_not_blocked(self) -> None:
        report = text_quality_report(
            "Scholarship application guide. Submit documents by May 31. Contact 051-890-1234."
        )

        self.assertFalse(report["is_binary_like"])
        self.assertEqual(detect_binary_markers("normal extracted PDF text"), [])

    def test_attachment_quality_blocks_binary_text(self) -> None:
        report = attachment_text_quality_report(
            "%PDF-1.7\nstream\nendobj\nxref\n%%EOF",
            parser_name="pdf",
            page_count=3,
        )

        self.assertEqual(report["parser_status"], "binary_marker_detected")
        self.assertEqual(report["quality_status"], "parse_failed")
        self.assertTrue(report["binary_marker_detected"])

    def test_attachment_quality_records_empty_parser_result(self) -> None:
        report = attachment_text_quality_report("", parser_name="pdf", page_count=2)

        self.assertEqual(report["parser_status"], "parser_empty_text")
        self.assertEqual(report["quality_status"], "parse_failed")
        self.assertEqual(report["quality_reason"], "parser_empty_text")

    def test_attachment_quality_distinguishes_empty_ocr_result(self) -> None:
        report = attachment_text_quality_report("", parser_name="pdf_ocr_empty", page_count=2)

        self.assertEqual(report["parser_status"], "ocr_empty_text")
        self.assertEqual(report["quality_status"], "parse_failed")

    def test_attachment_quality_allows_normal_pdf_text(self) -> None:
        text = (
            "Scholarship application guide for enrolled students. "
            "Submit documents between May 20 and May 31. "
            "Contact the student affairs office at 051-890-1234 for questions."
        )
        report = attachment_text_quality_report(text, parser_name="pdf", page_count=1)

        self.assertEqual(report["parser_status"], "parser_success")
        self.assertEqual(report["quality_status"], "ok")
        self.assertGreater(report["text_per_page"], 80)
        self.assertFalse(report["binary_marker_detected"])

    def test_attachment_quality_flags_low_text_per_page(self) -> None:
        text = (
            "Application period May 20 to May 31. "
            "Submit the form to the scholarship office. "
            "Contact 051-890-1234."
        )
        report = attachment_text_quality_report(text, parser_name="pdf", page_count=5)

        self.assertEqual(report["quality_status"], "needs_review")
        self.assertIn("low_text_per_page", report["quality_reason"])
