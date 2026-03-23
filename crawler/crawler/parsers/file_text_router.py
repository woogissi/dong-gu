# crawler/parsers/file_text_router.py

from pathlib import Path

from crawler.parsers.pdf_parser import PDFParser
from crawler.parsers.hwpx_parser import HWPXParser
from crawler.parsers.hwp_parser import HWPParser


class FileTextRouter:
    def __init__(self):
        self.pdf_parser = PDFParser()
        self.hwpx_parser = HWPXParser()
        self.hwp_parser = HWPParser()

    def get_extension(self, file_path: str) -> str:
        return Path(file_path).suffix.lower()

    def extract_text(self, file_path: str) -> dict:
        ext = self.get_extension(file_path)

        if ext == ".pdf":
            result = self.pdf_parser.extract_text(file_path)
            return {
                "parser_type": "pdf",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
            }

        if ext == ".hwpx":
            result = self.hwpx_parser.extract_text(file_path)
            return {
                "parser_type": "hwpx",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "raw_xml_files": result.get("raw_xml_files", []),
            }

        if ext == ".hwp":
            result = self.hwp_parser.extract_text(file_path)
            return {
                "parser_type": "hwp_fallback",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "note": result.get("note"),
            }

        return {
            "parser_type": "unsupported",
            "attachment_text": None,
            "page_count": None,
            "pages": [],
        }