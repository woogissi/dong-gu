"""Build compact answer context from selected documents."""

import re

from rag.schemas.retrieved_doc import RetrievedDoc

_NOISE_LINE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        "원본 그림의 이름",
        "사진 찍은 날짜",
        "카메라 제조 업체",
        "카메라 모델",
        "ISO 감도",
        "노출 시간",
        "조리개 값",
        "GPS 정보",
        "이미지 크기",
        "스캔 날짜",
        "OCR confidence",
        "image metadata",
        "exif",
    ]
]


def build_context(docs: list[RetrievedDoc]) -> str:
    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        section_title = doc.metadata.get("section_title") or "섹션 없음"
        blocks.append(
            "\n".join(
                [
                    f"[문서 {index}]",
                    f"제목: {doc.title or '제목 없음'}",
                    f"섹션: {section_title}",
                    f"출처: {doc.source or doc.metadata.get('source_type') or '출처 없음'}",
                    f"게시일: {doc.metadata.get('published_at') or '날짜 없음'}",
                    "내용:",
                    _clean_content(doc.content),
                ]
            )
        )
    return "\n\n".join(blocks)


def _clean_content(content: str) -> str:
    lines = []
    for line in (content or "").splitlines():
        if any(pattern.search(line) for pattern in _NOISE_LINE_PATTERNS):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
