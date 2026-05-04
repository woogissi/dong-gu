# crawler/parsers/image_parser.py

from pathlib import Path

from crawler.ocr.korean_ocr import KoreanOCREngine


class ImageParser:
    def __init__(self):
        self.ocr = KoreanOCREngine()

    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        try:
            result = self.ocr.extract_text_from_bytes(path.read_bytes())
            text = result.text
        except Exception as e:
            return {
                "file_path": str(path.as_posix()),
                "page_count": None,
                "text": None,
                "pages": [],
                "note": f"image OCR failed: {e}",
            }

        return {
            "file_path": str(path.as_posix()),
            "page_count": 1 if text else None,
            "text": text if text else None,
            "pages": [
                {
                    "page_no": 1,
                    "text": text,
                    "parser_type": result.engine,
                }
            ] if text else [],
            "note": (
                f"extracted via local image OCR; engine={result.engine}"
                if text
                else "image OCR returned empty text"
            ),
        }
