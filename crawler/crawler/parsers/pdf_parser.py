# crawler/parsers/pdf_parser.py

from pathlib import Path

from pypdf import PdfReader


class PDFParser:
    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        reader = PdfReader(str(path))
        pages = []
        full_text_parts = []

        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()

            pages.append({
                "page_no": page_index,
                "text": text,
            })

            if text:
                full_text_parts.append(text)

        full_text = "\n\n".join(full_text_parts).strip()

        return {
            "file_path": str(path.as_posix()),
            "page_count": len(reader.pages),
            "text": full_text,
            "pages": pages,
        }