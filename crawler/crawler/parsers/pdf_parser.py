# crawler/parsers/pdf_parser.py

from __future__ import annotations

import io
import re
from pathlib import Path
import io
import os
import re

import fitz  # PyMuPDF
from PIL import Image
from pypdf import PdfReader

from crawler.ocr.korean_ocr import KoreanOCREngine


EBOOK_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?ebookand\.com/.{0,200}?print-layout\.html?\|?(?:\s+\d+/\d+)?",
    re.IGNORECASE,
)
EBOOK_DATE_RE = re.compile(
    r"^\s*\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*(?:[^\d:.]{0,6})?\s*\d{1,2}[:.]\d{2}\s*(?:ebook)?\s*$",
    re.IGNORECASE,
)
TIME_ONLY_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}\s*$")
PAGE_MARKER_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
STANDALONE_EBOOK_NOISE_RE = re.compile(
    r"^\s*(?:ebook|print-layout\.html?|DONG-EUI UNIVERSITY)\s*$",
    re.IGNORECASE,
)


class PDFParser:
    def __init__(
        self,
        skip_ocr: bool | None = None,
        ocr_max_pages: int | None = None,
        ocr_first_pages: int | None = None,
    ):
        if skip_ocr is None:
            skip_ocr = os.getenv("CRAWLER_SKIP_PDF_OCR", "1") == "1"
        if ocr_max_pages is None:
            raw_max_pages = os.getenv("CRAWLER_PDF_OCR_MAX_PAGES", "5")
            ocr_max_pages = int(raw_max_pages) if raw_max_pages else None
        if ocr_first_pages is None:
            raw_first_pages = os.getenv("CRAWLER_PDF_OCR_FIRST_PAGES", "")
            ocr_first_pages = int(raw_first_pages) if raw_first_pages else None

        self.skip_ocr = skip_ocr
        self.ocr_max_pages = ocr_max_pages
        self.ocr_first_pages = ocr_first_pages
        self.ocr = KoreanOCREngine()

    def is_ebook_noise(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()
        return (
            "ebookand.com" in lower
            or "print-layout.htm" in lower
            or re.search(r"\bebook\b", lower) is not None
        )

    def is_noise_text(self, text: str) -> bool:
        if not text or not text.strip():
            return True

        noise_removed = text.strip()
        for pattern in (
            r"ebook",
            r"www\.ebookand\.com",
            r"print-layout\.html?",
            r"\d+/\d+",
            r"\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.",
            r"(?:[^\d:.]{0,6})?\s*\d{1,2}[:.]\d{2}",
        ):
            noise_removed = re.sub(pattern, "", noise_removed, flags=re.IGNORECASE)

        noise_removed = re.sub(r"\s+", "", noise_removed)
        return len(noise_removed) < 20

    def clean_ocr_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\xa0", " ")
        cleaned_lines = []

        for raw_line in text.splitlines():
            line = re.sub(r"[ \t]+", " ", raw_line).strip()

            if not line:
                cleaned_lines.append("")
                continue

            line = EBOOK_URL_RE.sub("", line).strip()
            line = re.sub(r"\bebook\b", "", line, flags=re.IGNORECASE).strip()

            if not line:
                cleaned_lines.append("")
                continue

            if (
                "ebookand.com" in line.lower()
                or "print-layout" in line.lower()
                or EBOOK_DATE_RE.match(line)
                or TIME_ONLY_RE.match(line)
                or PAGE_MARKER_RE.match(line)
                or STANDALONE_EBOOK_NOISE_RE.match(line)
            ):
                cleaned_lines.append("")
                continue

            cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def ocr_page(self, pdf_path: Path | str, page_index: int) -> tuple[str, str]:
        """OCR a zero-based PDF page index."""
        doc = fitz.open(str(pdf_path))

        try:
            page = doc.load_page(page_index)
            matrix = fitz.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            result = self.ocr.extract_text_from_image(img)
            return self.clean_ocr_text(result.text), result.engine
        finally:
            doc.close()

    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        reader = PdfReader(str(path))
        pages = []
        full_text_parts = []

        ocr_used_count = 0
        text_layer_count = 0
        noise_page_count = 0
        ocr_skipped_count = 0
        ocr_limit_count = 0

        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            parser_type = "pdf_text_layer"

            use_ocr = False
            if self.is_ebook_noise(text):
                use_ocr = True
                noise_page_count += 1
            elif self.is_noise_text(text):
                use_ocr = True
                noise_page_count += 1
            elif len(text) < 50:
                use_ocr = True
                noise_page_count += 1

            if use_ocr:
                can_run_ocr = True
                if self.skip_ocr:
                    can_run_ocr = False
                    ocr_skipped_count += 1
                elif self.ocr_first_pages is not None and page_index > self.ocr_first_pages:
                    can_run_ocr = False
                    ocr_limit_count += 1
                elif self.ocr_max_pages is not None and ocr_used_count >= self.ocr_max_pages:
                    can_run_ocr = False
                    ocr_limit_count += 1

                if not can_run_ocr:
                    parser_type = "pdf_ocr_skipped"
                    text = self.clean_ocr_text(text)
                    pages.append({
                        "page_no": page_index,
                        "text": text,
                        "parser_type": parser_type,
                    })
                    if text:
                        full_text_parts.append(text)
                    print(
                        f"[PDF OCR SKIP] file={path.as_posix()} page={page_index} "
                        f"skip_ocr={self.skip_ocr} max_pages={self.ocr_max_pages} "
                        f"first_pages={self.ocr_first_pages}"
                    )
                    continue

                ocr_text, ocr_engine = self.ocr_page(path, page_index - 1)

                if ocr_text:
                    text = ocr_text
                    parser_type = f"pdf_ocr_{ocr_engine}"
                    ocr_used_count += 1
                else:
                    text = ""
                    parser_type = "pdf_ocr_empty"
            else:
                text_layer_count += 1
                text = self.clean_ocr_text(text)

            pages.append({
                "page_no": page_index,
                "text": text,
                "parser_type": parser_type,
            })

            if text:
                full_text_parts.append(text)

        full_text = "\n\n".join(full_text_parts).strip()

        return {
            "file_path": str(path.as_posix()),
            "page_count": len(reader.pages),
            "text": full_text if full_text else None,
            "pages": pages,
            "note": (
                "extracted with PDF text layer + EasyOCR fallback; "
                f"ocr_pages={ocr_used_count}, "
                f"text_layer_pages={text_layer_count}, "
                f"noise_pages={noise_page_count}, "
                f"ocr_skipped_pages={ocr_skipped_count}, "
                f"ocr_limited_pages={ocr_limit_count}"
            ),
        }
