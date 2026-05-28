"""Build compact, traceable answer context from selected documents."""

from __future__ import annotations

import re

from rag.preprocess.query_features import ui_noise_hits
from rag.schemas.retrieved_doc import RetrievedDoc

_NOISE_LINE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        "OCR confidence",
        "image metadata",
        "exif",
        "본문 바로가기",
        "사이트맵",
        "로그인",
        "회원가입",
        "COPYRIGHT",
        "copyright",
    ]
]


def build_context(docs: list[RetrievedDoc]) -> str:
    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        section_title = doc.metadata.get("section_title") or "섹션 없음"
        score_parts = [
            f"score={doc.score}",
            f"lexical={doc.metadata.get('lexical_score')}",
            f"vector={doc.metadata.get('vector_score')}",
            f"rerank={doc.metadata.get('rerank_score')}",
            f"final={doc.metadata.get('final_score')}",
        ]
        blocks.append(
            "\n".join(
                [
                    f"[문서 {index}]",
                    f"chunk_id: {doc.chunk_id}",
                    f"doc_id: {doc.doc_id}",
                    f"title: {doc.title or '제목 없음'}",
                    f"section: {section_title}",
                    f"source_url: {doc.source or '출처 없음'}",
                    f"source_type: {doc.metadata.get('source_type') or doc.category or ''}",
                    f"content_type: {doc.metadata.get('content_type') or doc.metadata.get('section_type') or ''}",
                    f"published_at: {doc.metadata.get('published_at') or '날짜 없음'}",
                    f"scores: {'; '.join(score_parts)}",
                    "content:",
                    _clean_content(doc.content),
                ]
            )
        )
    return "\n\n".join(blocks)


def _clean_content(content: str) -> str:
    lines: list[str] = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in _NOISE_LINE_PATTERNS):
            continue
        if ui_noise_hits(stripped) >= 3:
            continue
        lines.append(line)
    return "\n".join(lines).strip()
