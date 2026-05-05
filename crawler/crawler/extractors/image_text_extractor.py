# crawler/extractors/image_text_extractor.py

from __future__ import annotations

from typing import List

import requests
import re
from crawler.ocr.korean_ocr import KoreanOCREngine


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
        self.ocr = KoreanOCREngine()

    def fetch_image_bytes(self, image_url: str) -> bytes | None:
        try:
            res = self.session.get(image_url, timeout=60)
            res.raise_for_status()
            return res.content
        except Exception:
            return None

    def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        return self.ocr.extract_text_from_bytes(image_bytes).text

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
