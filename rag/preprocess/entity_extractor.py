"""엔티티 추출 모듈
- 사용자 질문에서 핵심 엔티티 추출
- 엔티티 그룹별 대표 키워드 선정
- 시간 관련 표현 패턴 인식
- 필터링 가능한 엔티티 구성
"""

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
    # 순서를 보장하면서 매칭되는 값만 추출
    return [candidate for candidate in candidates if candidate in text]


def _extract_group_entities(text: str, keywords: set[str], entity_names: list[str]) -> list[str]:
    # entity_names(규칙)에 정의된 순서대로 검사하므로, 우선순위가 자연스럽게 보장됨
    matched = []
    for name in entity_names:
        if name in keywords or _contains_any(text, ENTITY_LEXICON.get(name, [])):
            matched.append(name)
    return matched


def _extract_time_entities(text: str) -> list[str]:
    time_entities = _pick_matches(text, _TIME_EXACT_MATCHES)

    for pattern, label in _TIME_PATTERN_RULES:
        if re.search(pattern, text):
            time_entities.append(label)

    # 중복을 제거하되, 삽입된 순서(Exact Match -> Pattern 순)를 보장
    return list(dict.fromkeys(time_entities))


def extract_entities(query: str, keywords: list[str] | None = None) -> dict[str, list[str]]:
    # 모든 기본 스키마 필드를 빈 리스트로 안전하게 초기화
    entities = {field: [] for field in ENTITY_SCHEMA}
    
    if not query:
        return entities

    text = query
    kw = set(keywords or [])
    
    for field, names in _ENTITY_GROUP_RULES.items():
        # 추출 후 중복 제거 (순서 보장)
        extracted = _extract_group_entities(text, kw, names)
        entities[field] = list(dict.fromkeys(extracted))
        
    entities["time"] = _extract_time_entities(text)
    return entities


def build_filters(entities: dict[str, list[str]]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}

    for field in _FILTER_FIELDS:
        values = entities.get(field, [])
        if values:
            filters[field] = values

    # 수정됨: "time" 리스트 전체를 복사하지 않고, _TIME_SCOPE_VALUES에 해당하는 값만 교집합으로 추출
    time_values = filters.get("time", [])
    scope_matches = [val for val in time_values if val in _TIME_SCOPE_VALUES]
    
    if scope_matches:
        filters["time_scope"] = scope_matches

    return filters


def primary_category(entities: dict[str, list[str]]) -> str | None:
    categories = entities.get("category", [])
    # 순서가 보장되므로 [0]은 사용자의 첫 번째 의도이거나 룰에 먼저 정의된 핵심 카테고리가 됨
    return categories[0] if categories else None
