"""엔티티 추출 모듈
- 사용자 질문에서 핵심 엔티티 추출
- 엔티티 그룹별 대표 키워드 선정
- 시간 관련 표현 패턴 인식
- 필터링 가능한 엔티티 구성
"""

from __future__ import annotations

import re

from rag.preprocess.domain_knowledge import DOMAIN_RULES, ENTITY_LEXICON, ENTITY_SCHEMA
from rag.preprocess.query_features import detect_domain

_ENTITY_GROUP_RULES: dict[str, list[str]] = {
    "category": ["학사", "장학", "등록", "졸업", "휴학", "복학", "수강", "기숙사", "비교과", "국제"],
    "target": ["신입생", "재학생", "복학생", "편입생", "대학원생", "외국인", "졸업예정자"],
    "department": ["교무처", "학생지원팀", "입학처", "국제교류원", "장학팀", "학과사무실"],
    "action": ["신청", "확인", "제출", "조회", "변경", "취소", "납부", "연장", "문의"],
}

# 실제 학과명 추출 패턴 (행정부서가 아닌 학과/학부/학전공).
# bare "전공"은 "복수전공/다전공/전공선택" 오탐을 유발하므로 "학전공"만 허용한다.
# "교육과/예과"는 유아교육과·한의예과처럼 "학과"로 끝나지 않는 학과명을 포착한다.
_DEPARTMENT_NAME_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9]{2,}(?:학과|학부|학전공|교육과|예과)"
)
# suffix 매칭으로 잘못 잡히는 일반어 제외
_DEPARTMENT_NAME_STOPWORDS = {"교육과정", "정규교육과", "재교육과", "평생교육과"}

# 학년(1~4학년) 추출 패턴 — 이수표의 해당 학년 섹션 타겟에 사용
_GRADE_PATTERN = re.compile(r"([1-4])\s*학년")

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


def _extract_grade_entities(text: str) -> list[str]:
    # "3학년" 등 학년 표현 추출 (순서 보존, 중복 제거)
    return [f"{g}학년" for g in dict.fromkeys(_GRADE_PATTERN.findall(text or ""))]


def _extract_department_names(text: str) -> list[str]:
    # 질문에 등장한 실제 학과명을 순서 보존하며 추출 (정규화 쿼리 기준)
    matches = _DEPARTMENT_NAME_PATTERN.findall(text or "")
    return [m for m in dict.fromkeys(matches) if m not in _DEPARTMENT_NAME_STOPWORDS]


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

    # 실제 학과명을 department 슬롯에 주입 (행정부서 term보다 구체적이므로 앞에 배치).
    # 이로써 build_filters → filters['department'] → reranker 학과 일치(±) 가 작동한다.
    dept_names = _extract_department_names(text)
    if dept_names:
        entities["department"] = list(dict.fromkeys([*dept_names, *entities.get("department", [])]))

    grade = _extract_grade_entities(text)
    if grade:
        entities["grade"] = grade

    entities["time"] = _extract_time_entities(text)
    domain, _ = detect_domain(text, kw)
    if domain:
        category = str(DOMAIN_RULES.get(domain, {}).get("category") or domain)
        entities.setdefault("domain", []).append(domain)
        if category:
            entities["category"] = list(dict.fromkeys([*entities.get("category", []), category]))
    return entities


def build_filters(entities: dict[str, list[str]]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}

    for field in _FILTER_FIELDS:
        values = entities.get(field, [])
        if values:
            filters[field] = values

    time_values = filters.get("time", [])
    scope_matches = [val for val in time_values if val in _TIME_SCOPE_VALUES]
    
    if scope_matches:
        filters["time_scope"] = scope_matches

    return filters


def primary_category(entities: dict[str, list[str]]) -> str | None:
    categories = entities.get("category", [])
    return categories[0] if categories else None
