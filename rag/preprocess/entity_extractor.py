"""Rule-based entity extraction for university FAQ queries."""

from __future__ import annotations

import re

from rag.preprocess.domain_knowledge import ENTITY_LEXICON, ENTITY_SCHEMA

_ENTITY_GROUP_RULES: dict[str, list[str]] = {
    "category": ["학사", "장학", "등록", "졸업", "휴학", "복학", "수강", "기숙사", "비교과", "국제"],
    "target": ["신입생", "재학생", "복학생", "편입생", "대학원생", "외국인", "졸업예정자"],
    "department": ["교무처", "학생지원팀", "입학처", "국제교류원", "장학팀", "학과사무실"],
    "action": ["신청", "확인", "제출", "조회", "변경", "취소", "납부", "연장", "문의"],
}

_TIME_EXACT_MATCHES = ["오늘", "내일", "이번학기", "1학기", "2학기", "상반기", "하반기"]
_TIME_PATTERN_RULES: list[tuple[str, str]] = [
    (r"(언제|기간|일정|마감|기한|까지)", "기간"),
    (r"(오늘|내일|지금|이번)", "시점"),
]
_FILTER_FIELDS = ("category", "target", "department", "time")
_TIME_SCOPE_VALUES = {"오늘", "내일", "이번학기", "1학기", "2학기", "상반기", "하반기"}


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _pick_matches(text: str, candidates: list[str]) -> list[str]:
    matched = [candidate for candidate in candidates if candidate in text]
    return sorted(set(matched))


def _extract_group_entities(text: str, keywords: set[str], entity_names: list[str]) -> list[str]:
    return [
        name
        for name in entity_names
        if name in keywords or _contains_any(text, ENTITY_LEXICON.get(name, []))
    ]


def _extract_time_entities(text: str) -> list[str]:
    time = _pick_matches(text, _TIME_EXACT_MATCHES)

    for pattern, label in _TIME_PATTERN_RULES:
        if re.search(pattern, text):
            time.append(label)

    return sorted(set(time))


def extract_entities(query: str, keywords: list[str] | None = None) -> dict[str, list[str]]:
    if not query:
        return {field: [] for field in ENTITY_SCHEMA}

    text = query
    kw = set(keywords or [])
    entities = {
        field: sorted(set(_extract_group_entities(text, kw, names)))
        for field, names in _ENTITY_GROUP_RULES.items()
    }
    entities["time"] = _extract_time_entities(text)
    return entities


def build_filters(entities: dict[str, list[str]]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}

    for field in _FILTER_FIELDS:
        values = entities.get(field, [])
        if values:
            filters[field] = values

    if any(value in _TIME_SCOPE_VALUES for value in filters.get("time", [])):
        filters["time_scope"] = filters["time"]

    return filters


def primary_category(entities: dict[str, list[str]]) -> str | None:
    categories = entities.get("category", [])
    return categories[0] if categories else None
