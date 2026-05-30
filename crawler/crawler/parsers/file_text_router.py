# crawler/parsers/file_text_router.py

import subprocess
import tempfile
import zipfile
from pathlib import Path

from crawler.parsers.hwp_parser import HWPParser
from crawler.parsers.hwpx_parser import HWPXParser
from crawler.parsers.image_parser import ImageParser
from crawler.parsers.ooxml_parser import OOXMLParser
from crawler.parsers.pdf_parser import PDFParser

# LibreOffice 변환 대상 확장자 → 변환 후 타겟 포맷
# .hwp는 hwp5txt 실패 시 폴백으로만 사용 (LibreOffice HWP 지원이 불완전함)
_LIBREOFFICE_CONVERT_MAP = {
    ".xls": "xlsx",
    ".doc": "docx",
    ".ppt": "pptx",
    ".hwp": "docx",
}


class FileTextRouter:                                   # 파일 확장자를 보고 어떤 파서로 보낼지 결정하는 분기기(router)
    LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}

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

        # ZIP 처리
        if ext == ".zip":
            return self.extract_zip_and_parse(file_path)

        if ext == ".pdf":                               # 확장자가 pdf일때
            result = self.pdf_parser.extract_text(file_path)
            return {
                "parser_type": "pdf",
                "attachment_text": result["text"],
                "page_count": result["page_count"],
                "pages": result["pages"],
                "attachment_tables": result.get("tables", []),
                "note": result.get("note"),
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
            if result.get("text"):
                return {
                    "parser_type": "hwp",
                    "attachment_text": result["text"],
                    "page_count": result["page_count"],
                    "pages": result["pages"],
                    "note": result.get("note"),
                }
            # hwp5txt 추출 실패 → LibreOffice 폴백
            converted = self._convert_with_libreoffice(file_path, ext)
            if converted:
                return converted
            return {
                "parser_type": "hwp",
                "attachment_text": None,
                "page_count": result.get("page_count"),
                "pages": result.get("pages", []),
                "note": result.get("note") or "hwp5txt extraction failed; LibreOffice fallback also failed",
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

        if ext in self.LEGACY_OFFICE_EXTENSIONS:
            converted = self._convert_with_libreoffice(file_path, ext)
            if converted:
                return converted
            return {
                "parser_type": "unsupported_legacy_office",
                "attachment_text": None,
                "page_count": None,
                "pages": [],
                "note": (
                    f"LibreOffice conversion failed for {ext}; "
                    "install LibreOffice or convert to OOXML manually"
                ),
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

    def _convert_with_libreoffice(self, file_path: str, src_ext: str) -> dict | None:
        target_fmt = _LIBREOFFICE_CONVERT_MAP.get(src_ext)
        if not target_fmt:
            return None
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", target_fmt, file_path, "--outdir", tmpdir],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return None
            if result.returncode != 0:
                return None
            stem = Path(file_path).stem
            converted_path = Path(tmpdir) / f"{stem}.{target_fmt}"
            if not converted_path.exists():
                return None
            try:
                parse_result = self.ooxml_parser.extract_text(str(converted_path))
            except Exception:
                return None
        return {
            "parser_type": f"{src_ext.lstrip('.')}_via_libreoffice",
            "attachment_text": parse_result.get("text"),
            "page_count": parse_result.get("page_count"),
            "pages": parse_result.get("pages", []),
            "raw_xml_files": parse_result.get("raw_xml_files", []),
            "note": f"converted {src_ext} → .{target_fmt} via LibreOffice",
        }

    def extract_zip_and_parse(self, file_path: str) -> dict:
        """
        zip 파일 압축 해제 후 내부 파일들을 재귀적으로 파싱
        """
        results = []
        extracted_files = []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            with zipfile.ZipFile(file_path, "r") as zip_ref:
                self.safe_extract_zip(zip_ref, tmpdir_path)

            for inner_file in tmpdir_path.rglob("*"):
                if not inner_file.is_file():
                    continue

                try:
                    parsed = self.extract_text(str(inner_file))

                    if parsed:
                        text = parsed.get("text") or parsed.get("attachment_text")

                        if text:
                            results.append(
                                f"[ZIP:{inner_file.name}]\n{text}"
                            )

                        extracted_files.append(inner_file.name)

                except Exception as e:
                    print(f"[ZIP PARSE ERROR] {inner_file} error={e}")

        merged_text = "\n\n".join(results).strip()

        return {
            "parser_type": "zip_recursive",
            "attachment_text": merged_text if merged_text else None,
            "extracted_files": extracted_files,
            "file_count": len(extracted_files),
        }

    def safe_extract_zip(self, zip_ref: zipfile.ZipFile, target_dir: Path) -> None:
        target_root = target_dir.resolve()
        for member in zip_ref.infolist():
            destination = (target_dir / member.filename).resolve()
            if not destination.is_relative_to(target_root):
                raise ValueError(f"unsafe zip member path: {member.filename}")
        zip_ref.extractall(target_dir)
