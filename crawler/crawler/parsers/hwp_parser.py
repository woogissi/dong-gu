# crawler/parsers/hwp_parser.py

from pathlib import Path


class HWPParser:
    """
    현재 버전은 HWP 원본 존재 여부만 확인하고,
    텍스트 추출은 미지원 fallback 처리.
    이후 변환기/전용 라이브러리 연결 가능.
    """

    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"HWP file not found: {file_path}")

        return {
            "file_path": str(path.as_posix()),
            "page_count": None,
            "text": None,
            "pages": [],
            "note": "hwp text extraction is not implemented yet",
        }