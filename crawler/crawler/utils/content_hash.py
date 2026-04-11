# crawler/utils/content_hash.py

from __future__ import annotations

import hashlib


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return text.strip()


def build_content_fingerprint_text(
    raw_text: str | None = None,
    table_text: str | None = None,
    attachment_text: str | None = None,
) -> str:
    """
    문서 변경 비교용 fingerprint 문자열 생성

    비교 기준:
    - 본문(raw_text)
    - 표(table_text)
    - 첨부 텍스트(attachment_text)

    각 영역을 구분 태그와 함께 합쳐서
    변경 시 해시가 달라지도록 만든다.
    """
    parts: list[str] = []

    body = normalize_text(raw_text)
    table = normalize_text(table_text)
    attachment = normalize_text(attachment_text)

    if body:
        parts.append("[BODY]\n" + body)

    if table:
        parts.append("[TABLE]\n" + table)

    if attachment:
        parts.append("[ATTACHMENT]\n" + attachment)

    return "\n\n".join(parts).strip()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_content_hash(
    raw_text: str | None = None,
    table_text: str | None = None,
    attachment_text: str | None = None,
) -> str:
    fingerprint = build_content_fingerprint_text(
        raw_text=raw_text,
        table_text=table_text,
        attachment_text=attachment_text,
    )
    return sha1_text(fingerprint)