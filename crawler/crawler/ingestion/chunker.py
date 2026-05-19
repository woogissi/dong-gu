# crawler/ingestion/chunker.py

import hashlib
import os
import re


CHUNK_HASH_NORMALIZATION_VERSION = "normalized-v2"
DEFAULT_PARAGRAPH_OVERLAP_CHARS = 80

STUB_LINE_PATTERNS = (
    re.compile(r"^(more|notice|program|sns|home|top|quick\s*menu)$", re.IGNORECASE),
    re.compile(r"^(pdf|hwp)\s*다운로드$", re.IGNORECASE),
    re.compile(r"^전체화면\s*보기$"),
    re.compile(r"^(본문\s*바로가기|전체메뉴|사이트맵|로그인|회원가입|목록)$"),
    re.compile(r"^웹진호수(?:\s*[|:]\s*\d+)?$"),
    re.compile(r"^행사사진(?:\s*more)?$", re.IGNORECASE),
    re.compile(r"^(로그인|회원가입|이용문의)$"),
    re.compile(r"^(게시물\s*(좌측|우측)으로\s*이동|이전\s*정지\s*시작\s*다음)$"),
)
STUB_PHRASE_PATTERN = re.compile(
    r"(PDF\s*다운로드|HWP\s*다운로드|전체화면\s*보기|웹진호수|"
    r"본문\s*바로가기|전체메뉴|사이트맵|로그인|회원가입|SNS\s*공유|"
    r"게시물\s*좌측으로\s*이동|게시물\s*우측으로\s*이동|이전\s*정지\s*시작\s*다음)",
    re.IGNORECASE,
)
TABLE_SHELL_PATTERN = re.compile(
    r"^(번호|제목|작성자|작성일|등록일|조회|첨부|내용|파일)(\s*[|/]\s*"
    r"(번호|제목|작성자|작성일|등록일|조회|첨부|내용|파일))*$"
)
DECORATIVE_RUN_PATTERN = re.compile(r"([|ㆍ·\-_=*#])\1{2,}")


class DocumentChunker:
    def __init__(
        self,
        max_chars: int = 900,
        overlap_chars: int = 100,
        max_chunks_per_section: int = 80,
        paragraph_overlap_chars: int | None = None,
        dedupe_normalized_chunks: bool = True,
        skip_stub_chunks: bool = True,
    ):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.max_chunks_per_section = max_chunks_per_section
        self.paragraph_overlap_chars = self._resolve_paragraph_overlap_chars(paragraph_overlap_chars)
        self.dedupe_normalized_chunks = dedupe_normalized_chunks
        self.skip_stub_chunks = skip_stub_chunks

    def _resolve_paragraph_overlap_chars(self, paragraph_overlap_chars: int | None) -> int:
        if paragraph_overlap_chars is None:
            raw_value = os.getenv("CRAWLER_CHUNK_PARAGRAPH_OVERLAP_CHARS", str(DEFAULT_PARAGRAPH_OVERLAP_CHARS))
            try:
                paragraph_overlap_chars = int(raw_value)
            except ValueError:
                paragraph_overlap_chars = DEFAULT_PARAGRAPH_OVERLAP_CHARS
        return max(0, min(paragraph_overlap_chars, self.max_chars // 4))

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = STUB_PHRASE_PATTERN.sub(" ", text)
        text = DECORATIVE_RUN_PATTERN.sub(r"\1", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def normalize_for_hash(self, text: str) -> str:
        """Normalize semantically identical chunk text before hashing."""
        text = self.normalize_text(text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s*([|:/])\s*", r"\1", text)
        return text.casefold().strip()

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

        structured_sections = doc.get("structured_sections") or []
        if structured_sections:
            for section in structured_sections:
                text = section.get("text")
                if not text:
                    continue
                sections.append(
                    {
                        "section_type": section.get("section_type") or "body",
                        "section_title": section.get("section_title") or "body",
                        "text": self.remove_repeated_lines(text),
                        "metadata": section.get("metadata", {}),
                    }
                )
            if sections:
                return sections

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

    def build_paragraph_overlap(self, text: str) -> str:
        if self.paragraph_overlap_chars <= 0:
            return ""

        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return ""

        sentences = [sentence.strip() for sentence in re.findall(r"[^.!?。]+[.!?。]?", normalized)]
        candidate = sentences[-1].strip() if sentences else normalized
        if len(candidate) > self.paragraph_overlap_chars:
            candidate = normalized[-self.paragraph_overlap_chars :].strip()
        return candidate

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
                carryover = self.build_paragraph_overlap(buffer)
                overlapped = f"{carryover}\n\n{para}".strip() if carryover else para
                buffer = overlapped if len(overlapped) <= self.max_chars else para
            else:
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

    def make_chunk_id(self, doc_id: str, version: int, chunk_index: int) -> str:
        return f"{doc_id}_v{int(version):03d}_chunk_{chunk_index:03d}"

    def make_chunk_hash(self, text: str) -> str:
        normalized = self.normalize_for_hash(text)
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def is_meaningful_short_chunk(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text).strip()
        if len(normalized) < 8:
            return False

        has_number = bool(re.search(r"\d", normalized))
        if has_number and re.search(r"(전화|연락처|문의|담당|내선|fax|tel)", normalized, re.IGNORECASE):
            return True
        if has_number and re.search(r"(\d{2,4}[-.]\d{3,4}[-.]\d{4})", normalized):
            return True
        if has_number and re.search(r"(기간|일정|신청|접수|마감|부터|까지|월|일)", normalized):
            return True
        if has_number and re.search(r"(원|만원|천원|장학금|등록금|지원금|%)", normalized):
            return True
        if len(normalized) >= 18 and re.search(r"(대상|자격|조건|제출|신청|모집|선발)", normalized):
            return True
        return False

    def is_stub_chunk(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return True
        if self.is_meaningful_short_chunk(normalized):
            return False

        lines = [line.strip(" -*ㆍ·|:/") for line in text.splitlines() if line.strip()]
        if lines and all(any(pattern.search(line) for pattern in STUB_LINE_PATTERNS) for line in lines):
            return True
        if len(normalized) <= 80 and STUB_PHRASE_PATTERN.search(normalized):
            return True
        if len(normalized) <= 120 and TABLE_SHELL_PATTERN.fullmatch(normalized):
            return True
        if len(normalized) <= 40 and re.fullmatch(r"[A-Z\s|/]+", normalized):
            return True
        if self.ui_noise_ratio(normalized) >= 0.35 and len(normalized) <= 220:
            return True
        return False

    def ui_noise_ratio(self, text: str) -> float:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", text.lower())
        if not tokens:
            return 1.0
        noise_terms = {
            "home",
            "top",
            "more",
            "sns",
            "로그인",
            "회원가입",
            "사이트맵",
            "전체메뉴",
            "목록",
            "이전",
            "다음",
            "바로가기",
        }
        hits = sum(1 for token in tokens if token in noise_terms)
        return hits / len(tokens)

    def chunk_document(self, doc: dict) -> list[dict]:
        chunks = []
        chunk_index = 1
        seen_hashes: set[str] = set()

        for section_index, section in enumerate(self.build_chunk_sections(doc), start=1):
            section_text = self.remove_repeated_lines(section["text"])
            section_chunks = self.split_section_into_chunks(section_text)
            total_section_chunks = len(section_chunks)
            truncated = total_section_chunks > self.max_chunks_per_section

            for section_chunk_text in section_chunks[: self.max_chunks_per_section]:
                if self.skip_stub_chunks and self.is_stub_chunk(section_chunk_text):
                    continue
                if len(section_chunk_text) < 50 and not self.is_meaningful_short_chunk(section_chunk_text):
                    continue

                chunk_text = self.build_chunk_content(doc, section, section_chunk_text)
                content_hash = self.make_chunk_hash(chunk_text)
                if self.dedupe_normalized_chunks and content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)

                chunks.append(
                    {
                        "chunk_id": self.make_chunk_id(doc["doc_id"], doc.get("version", 1), chunk_index),
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
                        "content": chunk_text,
                        "content_length": len(chunk_text),
                        "content_hash": content_hash,
                        "version": doc.get("version", 1),
                        "metadata": {
                            "section_type": section["section_type"],
                            "section_title": section.get("section_title"),
                            "source_section_metadata": section.get("metadata", {}),
                            "section_chunk_count": total_section_chunks,
                            "section_truncated": truncated,
                            "max_chunks_per_section": self.max_chunks_per_section,
                            "content_hash_normalization": CHUNK_HASH_NORMALIZATION_VERSION,
                            "dedupe_scope": "document",
                            "paragraph_overlap_chars": self.paragraph_overlap_chars,
                            "long_document_split_todo": (
                                "For high section_truncated counts, split attachments/regulations/admissions guides "
                                "by heading, article, table, or table-of-contents anchors before chunking."
                            )
                            if truncated
                            else None,
                        },
                    }
                )
                chunk_index += 1

        return chunks
