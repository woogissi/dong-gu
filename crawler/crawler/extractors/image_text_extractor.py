# crawler/extractors/image_text_extractor.py

from __future__ import annotations

import io
import os
from typing import List

import requests
from PIL import Image, ImageOps
import pytesseract


pytesseract.pytesseract.tesseract_cmd = r"E:\Tesseract-OCR\tesseract.exe"       # 로컬용 이미지 ocr 경로
'''
tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd '''


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class ImageTextExtractor:
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
        """
        OCR 정확도 높이기 위한 기본 전처리
        - grayscale
        - auto contrast
        """
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        return img

    def extract_text_from_image(self, image_url: str) -> str:
        image_bytes = self.fetch_image_bytes(image_url)
        if not image_bytes:
            return ""

        try:
            img = self.preprocess_image(image_bytes)
            text = pytesseract.image_to_string(img, lang="kor+eng")
            return text.strip()
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
