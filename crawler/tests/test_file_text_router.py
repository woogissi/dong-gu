from pathlib import Path
import unittest
from zipfile import ZipFile

from crawler.parsers.file_text_router import FileTextRouter


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
