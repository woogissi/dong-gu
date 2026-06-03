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
        section_title = doc.metadata.get("section_title") or "section 없음"
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


def build_llm_context(docs: list[RetrievedDoc]) -> str:
    """LLM 답변 생성에 넣는 슬림 컨텍스트.

    내부 ID/점수 같은 진단 메타데이터(chunk_id/doc_id/source_type/content_type/scores)는 제외하고
    근거 파악에 필요한 제목·구분·출처·날짜·본문만 남겨, 짧은 정답(날짜·시간 등)이 점수·ID 텍스트
    사이에 묻혀 모델 주의가 분산되는 것을 막는다. 추적성 메타데이터는 state.metadata의
    citation_trace/candidate_trace에 그대로 보존되므로 진단 정보 손실은 없다.
    """
    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        section_title = doc.metadata.get("section_title") or "section 없음"
        published_at = doc.metadata.get("published_at") or "날짜 없음"
        blocks.append(
            "\n".join(
                [
                    f"[문서 {index}]",
                    f"title: {doc.title or '제목 없음'}",
                    f"section: {section_title}",
                    f"source_url: {doc.source or '출처 없음'}",
                    f"published_at: {published_at}",
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
