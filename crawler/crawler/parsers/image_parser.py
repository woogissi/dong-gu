# crawler/parsers/image_parser.py

import os
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


class ImageParser:
    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        try:
            img = Image.open(path).convert("RGB")
            img = ImageOps.grayscale(img)
            img = ImageOps.autocontrast(img)
            text = pytesseract.image_to_string(img, lang="kor+eng").strip()
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
            "pages": [{"page_no": 1, "text": text}] if text else [],
            "note": "extracted via local image OCR" if text else "image OCR returned empty text",
        }
