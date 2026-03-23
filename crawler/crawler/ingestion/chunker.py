# crawler/ingestion/chunker.py

import re
import hashlib


class DocumentChunker:
    def __init__(self, max_chars: int = 1200, overlap_chars: int = 150):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def build_chunk_source_text(self, doc: dict) -> str:
        parts = []

        title = doc.get("title")
        if title:
            parts.append(f"[TITLE]\n{title}")

        clean_text = doc.get("clean_text")
        if clean_text:
            parts.append(f"[BODY]\n{clean_text}")

        table_text = doc.get("table_text")
        if table_text:
            parts.append(f"[TABLE]\n{table_text}")

        attachment_text = doc.get("attachment_text")
        if attachment_text:
            parts.append(f"[ATTACHMENT]\n{attachment_text}")

        return "\n\n".join(parts).strip()

    def split_paragraphs(self, text: str) -> list[str]:
        text = self.normalize_text(text)
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n")]
        paragraphs = [p for p in paragraphs if p]
        return paragraphs

    def force_split_long_text(self, text: str) -> list[str]:
        """
        문단 하나가 너무 길면 강제로 자름
        """
        if len(text) <= self.max_chars:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.max_chars
            chunk = text[start:end]
            chunks.append(chunk)

            if end >= len(text):
                break

            start = max(0, end - self.overlap_chars)

        return chunks

    def make_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        return f"{doc_id}_chunk_{chunk_index:03d}"

    def make_chunk_hash(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def chunk_document(self, doc: dict) -> list[dict]:
        source_text = self.build_chunk_source_text(doc)
        paragraphs = self.split_paragraphs(source_text)

        merged_chunks = []
        buffer = ""

        for para in paragraphs:
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para

            if len(candidate) <= self.max_chars:
                buffer = candidate
                continue

            if buffer:
                merged_chunks.append(buffer)

            if len(para) > self.max_chars:
                merged_chunks.extend(self.force_split_long_text(para))
                buffer = ""
            else:
                buffer = para

        if buffer:
            merged_chunks.append(buffer)

        chunks = []
        for idx, chunk_text in enumerate(merged_chunks, start=1):
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