# crawler/ocr/korean_ocr.py

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps


EBOOK_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?ebookand\.com/.{0,200}?print-layout\.html?\|?(?:\s+\d+/\d+)?",
    re.IGNORECASE,
)
EBOOK_DATE_PREFIX_RE = re.compile(
    r"^\s*\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*(?:[^\d:.]{0,6})?\s*\d{1,2}[:.]\d{2}\s*(?:ebook)?\s*(?:\|)?\s*",
    re.IGNORECASE,
)
PAGE_MARKER_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
STANDALONE_EBOOK_NOISE_RE = re.compile(
    r"^\s*(?:ebook|print-layout\.html?|DONG-EUI UNIVERSITY)\s*$",
    re.IGNORECASE,
)


@dataclass
class OCRResult:
    text: str
    engine: str = "easyocr"
    confidence: float | None = None


class KoreanOCREngine:
    MIN_OCR_WIDTH = 1200

    def __init__(self):
        self._reader = None
        self._unavailable_reason: str | None = None

    def image_from_bytes(self, image_bytes: bytes) -> Image.Image:
        return Image.open(io.BytesIO(image_bytes))

    def preprocess_image(self, img: Image.Image) -> Image.Image:
        if img.mode in {"RGBA", "LA"} or ("transparency" in img.info):
            img = img.convert("RGBA")
            background = Image.new("RGBA", img.size, "WHITE")
            background.alpha_composite(img)
            img = background.convert("RGB")
        else:
            img = img.convert("RGB")

        if img.width < self.MIN_OCR_WIDTH:
            scale = self.MIN_OCR_WIDTH / max(img.width, 1)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        return img.filter(ImageFilter.SHARPEN)

    def normalize_ocr_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\x0c", "")
        text = text.replace("\xa0", " ")
        lines = []

        for raw_line in text.splitlines():
            line = re.sub(r"[ \t]+", " ", raw_line).strip()
            line = EBOOK_DATE_PREFIX_RE.sub("", line).strip()
            line = EBOOK_URL_RE.sub("", line).strip()
            line = re.sub(r"\bebook\b", "", line, flags=re.IGNORECASE).strip()

            if (
                not line
                or "ebookand.com" in line.lower()
                or "print-layout" in line.lower()
                or PAGE_MARKER_RE.match(line)
                or STANDALONE_EBOOK_NOISE_RE.match(line)
            ):
                if lines and lines[-1]:
                    lines.append("")
                continue

            lines.append(line)

        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def get_reader(self):
        if self._reader is not None:
            return self._reader
        if self._unavailable_reason:
            return None

        try:
            import easyocr
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return None

        try:
            self._reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
            return self._reader
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return None

    def extract_text_from_image(self, img: Image.Image) -> OCRResult:
        reader = self.get_reader()
        if reader is None:
            return OCRResult(text="", engine="easyocr_unavailable", confidence=None)

        try:
            import numpy as np

            prepared = self.preprocess_image(img).convert("RGB")
            raw_result = reader.readtext(
                np.array(prepared),
                detail=1,
                paragraph=False,
            )
        except Exception as exc:
            self._unavailable_reason = str(exc)
            return OCRResult(text="", engine="easyocr_failed", confidence=None)

        lines = []
        scores = []
        for item in raw_result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = item[1]
            if isinstance(text, str) and text.strip():
                lines.append(text)
            if len(item) >= 3:
                try:
                    scores.append(float(item[2]))
                except (TypeError, ValueError):
                    pass

        confidence = sum(scores) / len(scores) if scores else None
        return OCRResult(
            text=self.normalize_ocr_text("\n".join(lines)),
            confidence=confidence,
        )

    def extract_text_from_bytes(self, image_bytes: bytes) -> OCRResult:
        return self.extract_text_from_image(self.image_from_bytes(image_bytes))
