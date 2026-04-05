# crawler/parsers/pdf_parser.py

from pathlib import Path

from pypdf import PdfReader         # PDF 파일을 열고 페이지 단위로 접근가능하게 해줌


class PDFParser:
    def extract_text(self, file_path: str) -> dict:     # 입력은 PDF 파일 경로 문자열, 출력은 dict인 PDF 파싱 함수
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        reader = PdfReader(str(path))                   # PDF 열기
        pages = []
        full_text_parts = []

        for page_index, page in enumerate(reader.pages, start=1):       # PDF 모든 페이지를 하나씩 순회
            text = page.extract_text() or ""                            # 현재 페이지에서 텍스트를 추출(OCR이 아니라 PDF 텍스트 레이어를 읽는 방식)
            text = text.strip()

            pages.append({
                "page_no": page_index,
                "text": text,
            })

            if text:
                full_text_parts.append(text)                            # 현재 페이지 텍스트가 있으면 전체 텍스트용 리스트에 추가

        full_text = "\n\n".join(full_text_parts).strip()                # 모아둔 페이지 텍스트들을 빈 줄 1개씩 띄워 이어붙여 전체 본문을 만듦

        return {
            "file_path": str(path.as_posix()),      # 예) "crawler/data/raw/files/notice/doc1/모집요강.pdf"
            "page_count": len(reader.pages),        # PDF 총 페이지 수
            "text": full_text,                      # 전체 페이지 텍스트를 이어붙인 문자열
            "pages": pages,                         # 페이지별 텍스트 리스트 반환(page_no : , text : )
        }