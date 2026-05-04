# crawler/extractors/image_text_extractor.py

from __future__ import annotations

import io
import os
import re
from typing import List

import requests
from PIL import Image, ImageFilter, ImageOps
import pytesseract


tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


EBOOK_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?ebookand\.com/.{0,200}?print-layout\.html?\|?(?:\s+\d+/\d+)?",
    re.IGNORECASE,
)
EBOOK_DATE_PREFIX_RE = re.compile(
    r"^\s*\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*(?:[^\d:]{0,6})?\s*\d{1,2}:\d{2}\s*(?:ebook)?\s*(?:\|)?\s*",
    re.IGNORECASE,
)
PAGE_MARKER_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
STANDALONE_EBOOK_NOISE_RE = re.compile(
    r"^\s*(?:ebook|print-layout\.html?|DONG-EUI UNIVERSITY)\s*$",
    re.IGNORECASE,
)


class ImageTextExtractor:
    OCR_LANG = "kor+eng"
    OCR_LANG_CANDIDATES = ("kor+eng", "kor")
    OCR_CONFIG = "--oem 3 --psm 6"
    MIN_OCR_WIDTH = 1200

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_image_bytes(self, image_url: str) -> bytes | None:
        try:
            res = self.session.get(image_url, timeout=60)
            res.raise_for_status()
            return res.content
        except Exception:
            return None

    def preprocess_image(self, image_bytes: bytes) -> Image.Image:
        """Prepare the default image variant for Korean/English OCR."""
        img = Image.open(io.BytesIO(image_bytes))

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

    def build_ocr_candidates(self, image_bytes: bytes) -> list[Image.Image]:
        base = self.preprocess_image(image_bytes)
        threshold = base.point(lambda pixel: 255 if pixel > 175 else 0)
        inverted = ImageOps.invert(base)
        return [base, threshold, inverted]

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

            if line:
                lines.append(line)
            elif lines and lines[-1]:
                lines.append("")

        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def image_confidence(self, img: Image.Image, lang: str) -> float:
        try:
            data = pytesseract.image_to_data(
                img,
                lang=lang,
                config=self.OCR_CONFIG,
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return -1.0

        confidences = []
        for value, word in zip(data.get("conf", []), data.get("text", [])):
            if not word or not word.strip():
                continue
            try:
                confidence = float(value)
            except (TypeError, ValueError):
                continue
            if confidence >= 0:
                confidences.append(confidence)

        if not confidences:
            return -1.0
        return sum(confidences) / len(confidences)

    def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        best_img = None
        best_lang = self.OCR_LANG
        best_confidence = -1.0

        for img in self.build_ocr_candidates(image_bytes):
            for lang in self.OCR_LANG_CANDIDATES:
                confidence = self.image_confidence(img, lang)
                if confidence > best_confidence:
                    best_img = img
                    best_lang = lang
                    best_confidence = confidence

        if best_img is None:
            return ""

        text = pytesseract.image_to_string(
            best_img,
            lang=best_lang,
            config=self.OCR_CONFIG,
        )
        return self.normalize_ocr_text(text)

    def extract_text_from_image(self, image_url: str) -> str:
        image_bytes = self.fetch_image_bytes(image_url)
        if not image_bytes:
            return ""

        try:
            return self.extract_text_from_bytes(image_bytes)
        except Exception:
            return ""

    def extract_many(self, image_urls: List[str]) -> list[dict]:
        results = []

        for idx, image_url in enumerate(image_urls, start=1):
            text = self.extract_text_from_image(image_url)
            results.append({
                "image_index": idx,
                "image_url": image_url,
                "image_text": text,
            })

        return results
