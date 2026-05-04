# crawler/ingestion/chunker.py

import hashlib
import re


class DocumentChunker:
    def __init__(
        self,
        max_chars: int = 900,
        overlap_chars: int = 100,
        max_chunks_per_section: int = 80,
    ):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.max_chunks_per_section = max_chunks_per_section

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_repeated_lines(self, text: str, max_repeats: int = 3) -> str:
        lines = [line.strip() for line in text.splitlines()]
        counts = {}
        for line in lines:
            if len(line) >= 8 and not line.isdigit():
                counts[line] = counts.get(line, 0) + 1

        repeated = {line for line, count in counts.items() if count > max_repeats}
        cleaned = [line for line in lines if line not in repeated]
        return "\n".join(cleaned).strip()

    def build_chunk_source_text(self, doc: dict) -> str:
        return "\n\n".join(section["text"] for section in self.build_chunk_sections(doc)).strip()

    def split_attachment_sections(self, attachment_text: str) -> list[dict]:
        sections = []
        current_title = None
        current_lines = []

        for line in attachment_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("[ATTACHMENT:") and stripped.endswith("]"):
                if current_title or current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        sections.append(
                            {
                                "section_type": "attachment",
                                "section_title": current_title or "attachment",
                                "text": text,
                            }
                        )
                current_title = stripped.removeprefix("[ATTACHMENT:").removesuffix("]").strip()
                current_lines = []
                continue

            current_lines.append(line)

        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                {
                    "section_type": "attachment",
                    "section_title": current_title or "attachment",
                    "text": text,
                }
            )

        return sections

    def build_chunk_sections(self, doc: dict) -> list[dict]:
        sections = []

        clean_text = doc.get("normalize")
        if clean_text:
            sections.append(
                {
                    "section_type": "body",
                    "section_title": "body",
                    "text": self.remove_repeated_lines(clean_text),
                }
            )

        table_text = doc.get("table_text")
        if table_text:
            sections.append(
                {
                    "section_type": "table",
                    "section_title": "table",
                    "text": self.remove_repeated_lines(table_text),
                }
            )

        attachment_text = doc.get("attachment_text")
        if attachment_text:
            sections.extend(self.split_attachment_sections(attachment_text))

        image_text = doc.get("image_text")
        if image_text:
            sections.append(
                {
                    "section_type": "image",
                    "section_title": "image OCR",
                    "text": self.remove_repeated_lines(image_text),
                }
            )

        return sections

    def split_paragraphs(self, text: str) -> list[str]:
        text = self.normalize_text(text)
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n")]
        return [p for p in paragraphs if p]

    def force_split_long_text(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.max_chars
            chunks.append(text[start:end])

            if end >= len(text):
                break

            start = max(0, end - self.overlap_chars)

        return chunks

    def split_section_into_chunks(self, section_text: str) -> list[str]:
        paragraphs = self.split_paragraphs(section_text)
        merged_chunks = []
        buffer = ""

        for para in paragraphs:
            if len(para) > self.max_chars:
                if buffer:
                    merged_chunks.append(buffer)
                    buffer = ""

                merged_chunks.extend(self.force_split_long_text(para))
                continue

            candidate = f"{buffer}\n\n{para}".strip() if buffer else para

            if len(candidate) <= self.max_chars:
                buffer = candidate
                continue

            if buffer:
                merged_chunks.append(buffer)
            buffer = para

        if buffer:
            merged_chunks.append(buffer)

        return merged_chunks

    def build_chunk_content(self, doc: dict, section: dict, section_chunk_text: str) -> str:
        parts = []
        title = doc.get("title")
        if title:
            parts.append(f"[TITLE]\n{title}")

        section_type = section["section_type"].upper()
        section_title = section.get("section_title")
        if section_title:
            parts.append(f"[{section_type}]\n{section_title}")
        else:
            parts.append(f"[{section_type}]")

        parts.append(section_chunk_text)
        return "\n\n".join(part for part in parts if part).strip()

    def make_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        return f"{doc_id}_chunk_{chunk_index:03d}"

    def make_chunk_hash(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def chunk_document(self, doc: dict) -> list[dict]:
        chunks = []
        chunk_index = 1

        for section_index, section in enumerate(self.build_chunk_sections(doc), start=1):
            section_text = self.remove_repeated_lines(section["text"])
            section_chunks = self.split_section_into_chunks(section_text)
            total_section_chunks = len(section_chunks)
            truncated = total_section_chunks > self.max_chunks_per_section

            for section_chunk_text in section_chunks[: self.max_chunks_per_section]:
                chunk_text = self.build_chunk_content(doc, section, section_chunk_text)
                if len(chunk_text) < 50:
                    continue

                chunks.append(
                    {
                        "chunk_id": self.make_chunk_id(doc["doc_id"], chunk_index),
                        "doc_id": doc["doc_id"],
                        "chunk_index": chunk_index,
                        "section_index": section_index,
                        "section_type": section["section_type"],
                        "section_title": section.get("section_title"),
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
                        "metadata": {
                            "section_type": section["section_type"],
                            "section_title": section.get("section_title"),
                            "section_chunk_count": total_section_chunks,
                            "section_truncated": truncated,
                            "max_chunks_per_section": self.max_chunks_per_section,
                        },
                    }
                )
                chunk_index += 1

        return chunks
