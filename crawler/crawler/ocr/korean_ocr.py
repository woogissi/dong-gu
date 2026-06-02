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

        scores = []
        for item in raw_result:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                try:
                    scores.append(float(item[2]))
                except (TypeError, ValueError):
                    pass

        layout_text = self.reconstruct_layout(raw_result)
        confidence = sum(scores) / len(scores) if scores else None
        return OCRResult(
            text=self.normalize_ocr_text(layout_text),
            confidence=confidence,
        )

    def reconstruct_layout(self, raw_result) -> str:
        """OCR 박스의 좌표(bbox)로 행/열 구조를 복원해 표 형태를 보존한다.

        EasyOCR readtext(detail=1)는 [bbox, text, conf] 항목을 반환한다.
        같은 행(y 중심이 가까운) 박스들을 묶고 x 순으로 정렬하여,
        한 행에 셀이 여러 개면 탭(\\t)으로 구분한다. 이수표처럼 행-열 관계가
        중요한 표에서 교과목-학점-학기 매핑이 1차원으로 뭉개지는 것을 방지한다.
        단일 셀 행은 그대로 두어 일반 본문 텍스트에는 영향을 최소화한다.
        """
        boxes = []
        for item in raw_result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            bbox, text = item[0], item[1]
            if not (isinstance(text, str) and text.strip()):
                continue
            try:
                xs = [float(point[0]) for point in bbox]
                ys = [float(point[1]) for point in bbox]
            except (TypeError, ValueError, IndexError):
                # bbox가 없거나 형식이 다르면 단순 텍스트로 폴백
                boxes.append({"text": text.strip(), "cy": float(len(boxes)), "cx": 0.0, "h": 0.0, "x0": 0.0})
                continue
            boxes.append(
                {
                    "text": text.strip(),
                    "cy": sum(ys) / len(ys),
                    "cx": sum(xs) / len(xs),
                    "h": max(ys) - min(ys),
                    "x0": min(xs),
                }
            )

        if not boxes:
            return ""

        boxes.sort(key=lambda b: (b["cy"], b["cx"]))
        heights = [b["h"] for b in boxes if b["h"] > 0]
        avg_height = sum(heights) / len(heights) if heights else 0.0
        row_threshold = max(avg_height * 0.6, 8.0)

        rows: list[list[dict]] = [[boxes[0]]]
        for box in boxes[1:]:
            if abs(box["cy"] - rows[-1][-1]["cy"]) <= row_threshold:
                rows[-1].append(box)
            else:
                rows.append([box])

        # 다중 셀 행 간격 판정용: 평균 박스 폭 기반 임계
        widths = [b["cx"] - b["x0"] for b in boxes if b["cx"] - b["x0"] > 0]
        avg_half_width = (sum(widths) / len(widths)) if widths else 0.0
        gap_threshold = max(avg_half_width * 1.5, 20.0)

        lines: list[str] = []
        for row in rows:
            row.sort(key=lambda b: b["x0"])
            if len(row) == 1:
                lines.append(row[0]["text"])
                continue
            # 인접 셀 간 x 간격이 충분히 크면 탭(열 구분), 아니면 공백으로 병합
            parts = [row[0]["text"]]
            for prev, cur in zip(row, row[1:]):
                separator = "\t" if (cur["x0"] - prev["cx"]) >= gap_threshold else " "
                parts.append(separator + cur["text"])
            lines.append("".join(parts))

        return "\n".join(lines)

    def extract_text_from_bytes(self, image_bytes: bytes) -> OCRResult:
        return self.extract_text_from_image(self.image_from_bytes(image_bytes))
