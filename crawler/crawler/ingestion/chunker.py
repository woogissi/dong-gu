# crawler/ingestion/chunker.py

import re
import hashlib


class DocumentChunker:
    def __init__(self, max_chars: int = 500, overlap_chars: int = 50):        
        self.max_chars = max_chars                                          # max_chars : chunk 최대 글자 수
        self.overlap_chars = overlap_chars                                  # overlap_chars : 강제 분할할 때 앞 chunk와 뒤 chunk가 일부 겹치게 할 글자 수

    def normalize_text(self, text: str) -> str:                             # 청킹 전 텍스트 정리 함수
        if not text:
            return ""
        text = text.replace("\xa0", " ")                                    # non-breaking space 제거
        text = re.sub(r"[ \t]+", " ", text)                                 # 연속된 공백/탭을 한 칸 공백으로
        text = re.sub(r"\n{3,}", "\n\n", text)                              # 너무 많은 빈 줄을 두 줄까지만 줄임
        return text.strip()

    def build_chunk_source_text(self, doc: dict) -> str:                    # chunking할 원본 텍스트를 만드는 함수
        parts = []

        title = doc.get("title")
        if title:
            parts.append(f"[TITLE]\n{title}")                               # 문서 제목이 있으면 [TITLE] 태그와 함께 추가

        clean_text = doc.get("normalize")                  
        if clean_text:
            parts.append(f"[BODY]\n{clean_text}")                           # 문서의 정제된 본문 텍스트가 있으면 [BODY] 태그와 함께 추가

        table_text = doc.get("table_text")
        if table_text:
            parts.append(f"[TABLE]\n{table_text}")                          # 표가 있으면 [TABLE] 태그와 함께 추가

        attachment_text = doc.get("attachment_text")
        if attachment_text:
            parts.append(f"[ATTACHMENT]\n{attachment_text}")                # 첨부파일 있으면 [ATTACHMENT] 태그와 함께 추가

        if doc.get("image_text"):
            parts.append("[IMAGE]\n" + doc["image_text"])

        return "\n\n".join(parts).strip()

    def split_paragraphs(self, text: str) -> list[str]:                     # 텍스트를 문단 단위로 분리하는 함수
        text = self.normalize_text(text)    
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n")]                # 문단 분리는 빈 한줄 기준
        paragraphs = [p for p in paragraphs if p]                           # 빈 문단 제거
        return paragraphs

    def force_split_long_text(self, text: str) -> list[str]:
        """
        문단 하나가 너무 길면 강제로 자름
        """
        if len(text) <= self.max_chars:             # 길이가 최대값을 안 넘어가면 그대로 반환
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.max_chars
            chunk = text[start:end]
            chunks.append(chunk)

            if end >= len(text):
                break

            start = max(0, end - self.overlap_chars)        # 다음 시작점을 overlap_chars 만큼 당김

        return chunks

    def make_chunk_id(self, doc_id: str, chunk_index: int) -> str:      # chunk 고유 ID 생성 함수 doc_id + chunk_index 숫자
        return f"{doc_id}_chunk_{chunk_index:03d}"

    def make_chunk_hash(self, text: str) -> str:                        # 청크 해시 생성 함수
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def chunk_document(self, doc: dict) -> list[dict]:                  # 문서 1개를 받아 chunk 리스트로 바꾸는 메인 함수
        source_text = self.build_chunk_source_text(doc)                 # 제목/본문/표/첨부를 합친 큰 텍스트
        paragraphs = self.split_paragraphs(source_text)                 # 를 문단 단위로 분리

        merged_chunks = []
        buffer = ""

        for para in paragraphs:
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para       # buffer가 있으면 buffer + 빈줄 + para, 없으면 para 만 넣어서 후보 텍스트

            if len(candidate) <= self.max_chars:
                buffer = candidate                                      # 후보텍스트가 max_chars를 안 넘으면 버퍼에 계속 저장(한 청크에 최대한 많이 넣기 위함)
                continue

            if buffer:                                                          # buffer가 있으면 지금까지의 buffer를 하나의 청크로 확정
                merged_chunks.append(buffer)

            if len(para) > self.max_chars:                                      # para가 너무 길면 force_split_long_text()로 나누기
                merged_chunks.extend(self.force_split_long_text(para))
                buffer = ""
            else:
                buffer = para

        if buffer:
            merged_chunks.append(buffer)                    #반복 종료 후에 버퍼에 남아있으면 추가

        chunks = []
        for idx, chunk_text in enumerate(merged_chunks, start=1):       # 최종 청크 객체 넣기
            chunks.append({
                "chunk_id": self.make_chunk_id(doc["doc_id"], idx),
                "doc_id": doc["doc_id"],
                "chunk_index": idx,
                "source_type": doc.get("source_type"),
                "title": doc.get("title"),
                "source_url": doc.get("source_url"),
                "published_at": doc.get("published_at"),
                "department": doc.get("department"),
                "category_lv1": doc.get("category_lv1"),
                "category_lv2": doc.get("category_lv2"),
                "content": chunk_text,
                "content_length": len(chunk_text),
                "content_hash": self.make_chunk_hash(chunk_text),
                "version": doc.get("version", 1),
            })

        return chunks