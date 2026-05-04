# crawler/parsers/pdf_parser.py

from pathlib import Path
import re
import io

from pypdf import PdfReader
import fitz  # PyMuPDF
from PIL import Image, ImageOps
import pytesseract


pytesseract.pytesseract.tesseract_cmd = r"E:\Tesseract-OCR\tesseract.exe"

class PDFParser:
    def is_ebook_noise(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()
        return (
            "ebookand.com" in lower
            or "print-layout.html" in lower
            or re.search(r"\bebook\b", lower) is not None
        )

    def is_noise_text(self, text: str) -> bool:
        if not text or not text.strip():
            return True

        cleaned = text.strip()

        noise_patterns = [
            r"ebook",
            r"www\.ebookand\.com",
            r"print-layout\.html",
            r"\d+/\d+",
            r"\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.",
            r"오전\s*\d+:\d+",
            r"오후\s*\d+:\d+",
        ]

        noise_removed = cleaned
        for pattern in noise_patterns:
            noise_removed = re.sub(
                pattern,
                "",
                noise_removed,
                flags=re.IGNORECASE,
            )

        noise_removed = re.sub(r"\s+", "", noise_removed)

        return len(noise_removed) < 20

    def clean_ocr_text(self, text: str) -> str:
        if not text:
            return ""

        # ebook 출력용 머리말/꼬리말 제거
        text = re.sub(
            r"\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*오[전후]\s*\d+:\d+\s*ebook",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"www\.ebookand\.com/ebook/.*?print-layout\.html\s*\d+/\d+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\bebook\b", "", text, flags=re.IGNORECASE)

        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def ocr_page(self, pdf_path: Path, page_index: int) -> str:
        """
        page_index는 0부터 시작
        """
        doc = fitz.open(str(pdf_path))

        try:
            page = doc.load_page(page_index)

            # 해상도 높일수록 OCR 정확도 증가.
            matrix = fitz.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            img = ImageOps.grayscale(img)
            img = ImageOps.autocontrast(img)

            text = pytesseract.image_to_string(img, lang="kor+eng")
            return self.clean_ocr_text(text)

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

        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()

            parser_type = "pdf_text_layer"

            # 핵심:
            # ebookand / print-layout PDF는 텍스트 레이어가 헤더/푸터뿐이라 무조건 OCR
            use_ocr = False

            if self.is_ebook_noise(text):
                use_ocr = True
                noise_page_count += 1
            elif self.is_noise_text(text):
                use_ocr = True
                noise_page_count += 1
            elif len(text.strip()) < 50:
                use_ocr = True
                noise_page_count += 1

            if use_ocr:
                ocr_text = self.ocr_page(path, page_index - 1)

                if ocr_text:
                    text = ocr_text
                    parser_type = "pdf_ocr"
                    ocr_used_count += 1
                else:
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
                "extracted with PDF text layer + OCR fallback; "
                f"ocr_pages={ocr_used_count}, "
                f"text_layer_pages={text_layer_count}, "
                f"noise_pages={noise_page_count}"
            ),
        }