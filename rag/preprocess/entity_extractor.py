"""Rule-based entity extraction for university FAQ queries."""

from __future__ import annotations

import re

from rag.preprocess.domain_knowledge import ENTITY_LEXICON


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _pick_matches(text: str, candidates: list[str]) -> list[str]:
    matched = [candidate for candidate in candidates if candidate in text]
    return sorted(set(matched))


def extract_entities(query: str, keywords: list[str] | None = None) -> dict[str, list[str]]:
    if not query:
        return {
            "category": [],
            "target": [],
            "time": [],
            "department": [],
            "action": [],
        }

    text = query
    kw = set(keywords or [])

    category = [
        name
        for name in ["학사", "장학", "등록", "졸업", "휴학", "복학", "수강", "기숙사", "비교과", "국제"]
        if name in kw or _contains_any(text, ENTITY_LEXICON.get(name, []))
    ]

    target = [
        name
        for name in ["신입생", "재학생", "복학생", "편입생", "대학원생", "외국인", "졸업예정자"]
        if name in kw or _contains_any(text, ENTITY_LEXICON.get(name, []))
    ]

    department = [
        name
        for name in ["교무처", "학생지원팀", "입학처", "국제교류원", "장학팀", "학과사무실"]
        if name in kw or _contains_any(text, ENTITY_LEXICON.get(name, []))
    ]

    action = [
        name
        for name in ["신청", "확인", "제출", "조회", "변경", "취소", "납부", "연장", "문의"]
        if name in kw or _contains_any(text, ENTITY_LEXICON.get(name, []))
    ]

    time = _pick_matches(text, ["오늘", "내일", "이번학기", "1학기", "2학기", "상반기", "하반기"])
    if re.search(r"(언제|기간|일정|마감|기한|까지)", text):
        time.append("기간")
    if re.search(r"(오늘|내일|지금|이번)", text):
        time.append("시점")
    time = sorted(set(time))

    return {
        "category": sorted(set(category)),
        "target": sorted(set(target)),
        "time": time,
        "department": sorted(set(department)),
        "action": sorted(set(action)),
    }


def primary_category(entities: dict[str, list[str]]) -> str | None:
    categories = entities.get("category", [])
    return categories[0] if categories else None
