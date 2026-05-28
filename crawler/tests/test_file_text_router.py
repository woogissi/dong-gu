from pathlib import Path
import unittest
from unittest.mock import Mock
from zipfile import ZipFile

from crawler.parsers.file_text_router import FileTextRouter
from crawler.parsers.pdf_parser import PDFParser


class FileTextRouterTest(unittest.TestCase):
    def test_legacy_office_extension_has_explicit_policy(self) -> None:
        file_path = Path(self._testMethodName + ".doc")
        file_path.write_bytes(b"legacy")
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))

        result = FileTextRouter().extract_text(str(file_path))

        self.assertEqual(result["parser_type"], "unsupported_legacy_office")
        self.assertIsNone(result["attachment_text"])
        self.assertIn("LibreOffice", result["note"])

    def test_zip_parser_rejects_path_traversal(self) -> None:
        zip_path = Path(self._testMethodName + ".zip")
        self.addCleanup(lambda: zip_path.unlink(missing_ok=True))

        with ZipFile(zip_path, "w") as zip_file:
            zip_file.writestr("../escape.txt", "nope")

        with self.assertRaisesRegex(ValueError, "unsafe zip member path"):
            FileTextRouter().extract_text(str(zip_path))

    def test_pdf_table_renderer_outputs_markdown_and_tsv(self) -> None:
        parser = PDFParser()
        rows = [["학년", "이수구분", "교과목명"], ["2", "전공필수", "자료구조"]]

        markdown = parser.table_to_markdown(rows)
        tsv = parser.table_to_tsv(rows)

        self.assertIn("| 학년 | 이수구분 | 교과목명 |", markdown)
        self.assertIn("| --- | --- | --- |", markdown)
        self.assertIn("2\t전공필수\t자료구조", tsv)

    def test_file_text_router_returns_pdf_tables(self) -> None:
        file_path = Path(self._testMethodName + ".pdf")
        file_path.write_bytes(b"%PDF")
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))
        router = FileTextRouter()
        router.pdf_parser.extract_text = Mock(
            return_value={
                "text": "[PDF TABLE page=1 table=1 format=markdown]\n| 학년 | 교과목명 |",
                "page_count": 1,
                "pages": [{"page_no": 1, "text": "body", "tables": [{"table_no": 1}]}],
                "tables": [{"page_no": 1, "table_no": 1, "markdown": "| 학년 | 교과목명 |"}],
                "note": "tables=1",
            }
        )

        result = router.extract_text(str(file_path))

        self.assertEqual(result["parser_type"], "pdf")
        self.assertEqual(result["attachment_tables"][0]["table_no"], 1)
        self.assertEqual(result["pages"][0]["tables"][0]["table_no"], 1)
