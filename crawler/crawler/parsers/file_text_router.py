# crawler/parsers/file_text_router.py

from pathlib import Path

from crawler.parsers.pdf_parser import PDFParser
from crawler.parsers.hwpx_parser import HWPXParser
from crawler.parsers.hwp_parser import HWPParser
from crawler.parsers.ooxml_parser import OOXMLParser
from crawler.parsers.image_parser import ImageParser


class FileTextRouter:                                   # 파일 확장자를 보고 어떤 파서로 보낼지 결정하는 분기기(router)
    def __init__(self):
        self.pdf_parser = PDFParser()
        self.hwpx_parser = HWPXParser()
        self.hwp_parser = HWPParser()
        self.ooxml_parser = OOXMLParser()
        self.image_parser = ImageParser()

    def get_extension(self, file_path: str) -> str:     # 파일 경로에서 확장자만 뽑는 함수
        return Path(file_path).suffix.lower()

    def extract_text(self, file_path: str) -> dict:     # 메인 함수
        ext = self.get_extension(file_path)

        if ext == ".pdf":                               # 확장자가 pdf일때
            result = self.pdf_parser.extract_text(file_path)
            return {
                "parser_type": "pdf",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
            }

        if ext == ".hwpx":                              # 확장자가 hwpx일때
            result = self.hwpx_parser.extract_text(file_path)
            return {
                "parser_type": "hwpx",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "raw_xml_files": result.get("raw_xml_files", []),
            }

        if ext == ".hwp":                               # 확장자가 hwp일때
            result = self.hwp_parser.extract_text(file_path)
            return {
                "parser_type": "hwp",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "note": result.get("note"),
            }

        if ext in {".xlsx", ".pptx", ".docx"}:
            result = self.ooxml_parser.extract_text(file_path)
            return {
                "parser_type": ext.lstrip("."),
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "note": result.get("note"),
                "raw_xml_files": result.get("raw_xml_files", []),
            }

        if ext in {".jpg", ".jpeg", ".png"}:
            result = self.image_parser.extract_text(file_path)
            return {
                "parser_type": "image_ocr",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "note": result.get("note"),
            }

        return {                                        # 미지원 확장자일때
            "parser_type": "unsupported",
            "attachment_text": None,
            "page_count": None,
            "pages": [],
            "note": f"unsupported extension: {ext or '(none)'}",
        }
