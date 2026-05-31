"""Source type policy shared by retrieval and regression checks."""

from __future__ import annotations


KNOWN_SOURCE_TYPES = {
    "academic",
    "academic_notice",
    "academic_support",
    "admission",
    "campus",
    "cafeteria",
    "club_activity",
    "council_notice",
    "department",
    "dormitory",
    "exchange",
    "external_notice",
    "facility",
    "institution",
    "job",
    "library",
    "lifelong",
    "notice",
    "scholarship",
    "static",
    "student_life",
    "shuttle",
    "tuition",
    "welfare",
}

SOURCE_TYPE_ALIASES = {
    "기숙사": "dormitory",
    "생활관": "dormitory",
    "효민생활관": "dormitory",
    "장학": "scholarship",
    "장학금": "scholarship",
    "학사": "academic_notice",
    "수강": "academic_notice",
    "휴학": "academic_support",
    "복학": "academic_support",
    "증명서": "academic_support",
    "제증명": "academic_support",
}

SOURCE_TYPE_ALIASES.update(
    {
        "library": "library",
        "shuttle": "shuttle",
        "tuition": "tuition",
        "career": "job",
        "grade": "academic_support",
    }
)

CATEGORY_SOURCE_TYPES = {
    "academic": ["academic_support", "academic_notice", "notice", "institution"],
    "certificate": ["academic_support", "institution", "notice"],
    "course": ["academic_notice", "academic_support", "department", "institution"],
    "dormitory": ["dormitory", "notice"],
    "grade": ["academic_support", "academic_notice", "department", "institution"],
    "graduation": ["academic_notice", "academic_support", "department", "institution"],
    "library": ["library", "institution", "academic_support"],
    "career": ["advising", "job", "notice", "institution", "department"],
    "cafeteria": ["cafeteria", "welfare", "institution", "static", "facility"],
    "club_activity": ["club_activity", "student_life", "institution", "notice", "department"],
    "facility": ["institution", "department", "static", "facility"],
    "scholarship": ["scholarship", "notice"],
    "shuttle": ["shuttle", "campus", "student_life", "notice", "institution"],
    "tuition": ["tuition", "admission", "notice", "academic_notice", "academic_support", "institution"],
}

FORBIDDEN_SOURCE_TYPES_BY_FAMILY = {
    "shuttle": {"bids", "job", "scholarship", "external_notice"},
    "tuition": {"scholarship", "job", "bids", "external_notice", "dormitory"},
    "course_registration": {"job", "bids", "external_notice"},
    "seasonal_course_registration": {"job", "bids", "external_notice", "scholarship"},
    # exchange 문서는 국제교류처 공지로, 일반 기숙사 쿼리에서 rank1~3을 차지하는 노이즈.
    # 단, 외국인/유학생 기숙사 쿼리는 예외 처리 (retriever._filter_forbidden_source_types 참조).
    "dormitory": {"scholarship", "job", "bids", "external_notice", "exchange"},
    "campus_address": {"job", "scholarship", "bids", "external_notice"},
    "building_location": {"job", "scholarship", "bids", "external_notice"},
}

# 외국인/유학생 기숙사 쿼리 감지 — 이 경우 exchange 문서 필터를 해제한다
DORMITORY_FOREIGN_QUERY_TERMS: frozenset[str] = frozenset({"외국인", "유학생", "행복기숙사"})


def normalize_source_type(value: str) -> str:
    text = str(value or "").strip()
    return SOURCE_TYPE_ALIASES.get(text, text)


def allowed_source_types_for_values(values: list[str]) -> list[str]:
    source_types: list[str] = []
    for value in values:
        normalized = normalize_source_type(value)
        candidates = CATEGORY_SOURCE_TYPES.get(normalized, [normalized])
        for candidate in candidates:
            if candidate in KNOWN_SOURCE_TYPES and candidate not in source_types:
                source_types.append(candidate)
    return source_types


def forbidden_source_types_for_family(family: str | None) -> set[str]:
    return set(FORBIDDEN_SOURCE_TYPES_BY_FAMILY.get(str(family or ""), set()))
