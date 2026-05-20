"""Query feature helpers shared across RAG preprocessing and ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_BUILDING_NO_PATTERN = re.compile(r"\d+\s*번\s*건물")
_FLOOR_PATTERN = re.compile(r"\d+\s*층")
_YEAR_MAJOR_PATTERN = re.compile(r"\d+\s*학년")

GENERIC_QUERY_TERMS = {
    "동의대",
    "동의대학교",
    "정보",
    "안내",
    "관련",
    "내용",
    "알려줘",
    "뭐",
    "무엇",
    "어디",
    "이름",
}

PROTECTED_LITERAL_TERMS = (
    "정보공학관",
    "컴퓨터공학과",
    "이수표",
    "전공필수",
    "동아리",
    "IPP",
    "ipp",
    "총장",
    "건물번호",
    "캠퍼스맵",
    "편의점",
)

FACILITY_TERMS = {
    "건물",
    "건물번호",
    "정보공학관",
    "캠퍼스맵",
    "층",
    "위치",
    "편의점",
    "시설",
}

CURRICULUM_TERMS = {
    "컴퓨터공학과",
    "이수표",
    "전공필수",
    "전공",
    "학년",
    "과목",
    "교육과정",
}

PERSON_TERMS = {"총장", "7대", "역대총장", "역대"}
CLUB_PROGRAM_TERMS = {"동아리", "IPP", "ipp", "사업"}

INVALID_DEPARTMENT_FILTER_VALUES = {
    "학과사무실",
    "학과소개",
    "사무실",
    "위치",
    "연락처",
}

UI_NOISE_MARKERS = (
    "HOME",
    "Home",
    "home",
    "공유",
    "SNS",
    "sns",
    "More",
    "more",
    "메뉴",
    "사이트맵",
    "로그인",
    "회원가입",
    "본문 바로가기",
    "footer",
    "navigation",
    "copyright",
    "COPYRIGHT",
)


@dataclass(frozen=True)
class QueryFeatures:
    family: str = "general"
    protected_terms: list[str] = field(default_factory=list)
    strong_terms: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)

    def to_log_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "protected_terms": self.protected_terms,
            "strong_terms": self.strong_terms,
            "required_terms": self.required_terms,
        }


def extract_query_features(query: str, keywords: Iterable[str] | None = None) -> QueryFeatures:
    text = query or ""
    keyword_values = [str(value) for value in (keywords or []) if value]
    tokens = tokenize_koreanish(" ".join([text, *keyword_values]))
    protected = _protected_terms(text, keyword_values, tokens)
    strong = _strong_terms(tokens, protected)
    family = detect_query_family(text, [*strong, *protected])
    required = _required_terms_for_family(family, strong, protected)
    return QueryFeatures(
        family=family,
        protected_terms=ordered_unique(protected),
        strong_terms=ordered_unique(strong),
        required_terms=ordered_unique(required),
    )


def tokenize_koreanish(text: str) -> list[str]:
    return ordered_unique(match.group(0) for match in _TOKEN_PATTERN.finditer(text or ""))


def ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def detect_query_family(query: str, terms: Iterable[str] | None = None) -> str:
    values = {term.casefold() for term in tokenize_koreanish(query)}
    values.update(str(term).casefold() for term in (terms or []) if term)
    joined = " ".join(values)
    if any(term.casefold() in values or term.casefold() in joined for term in FACILITY_TERMS):
        return "building_location"
    if any(term.casefold() in values or term.casefold() in joined for term in CURRICULUM_TERMS):
        return "department_curriculum"
    if any(term.casefold() in values or term.casefold() in joined for term in PERSON_TERMS):
        return "person_title"
    if any(term.casefold() in values or term.casefold() in joined for term in CLUB_PROGRAM_TERMS):
        return "club_program"
    return "general"


def sanitize_filters(filters: dict[str, list[str]] | None) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    sanitized: dict[str, list[str]] = {}
    dropped: list[dict[str, str]] = []
    for field, values in (filters or {}).items():
        kept: list[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if not text:
                continue
            if field == "department" and text in INVALID_DEPARTMENT_FILTER_VALUES:
                dropped.append({"field": field, "value": text, "reason": "invalid_department_facet"})
                continue
            kept.append(text)
        if kept:
            sanitized[field] = ordered_unique(kept)
    return sanitized, dropped


def ui_noise_hits(text: str) -> int:
    haystack = text or ""
    haystack_lower = haystack.casefold()
    return sum(1 for marker in UI_NOISE_MARKERS if marker.casefold() in haystack_lower)


def required_entity_match_score(required_terms: Iterable[str], text: str) -> float:
    required = [term for term in required_terms if term]
    if not required:
        return 0.0
    haystack = (text or "").casefold()
    matched = sum(1 for term in required if term.casefold() in haystack)
    return matched / len(required)


def _protected_terms(text: str, keywords: list[str], tokens: list[str]) -> list[str]:
    protected: list[str] = []
    protected.extend(match.group(0).replace(" ", "") for match in _BUILDING_NO_PATTERN.finditer(text))
    protected.extend(match.group(0).replace(" ", "") for match in _FLOOR_PATTERN.finditer(text))
    protected.extend(match.group(0).replace(" ", "") for match in _YEAR_MAJOR_PATTERN.finditer(text))
    for term in PROTECTED_LITERAL_TERMS:
        if term in text or any(term.casefold() == keyword.casefold() for keyword in keywords):
            protected.append(term.upper() if term.casefold() == "ipp" else term)
    for token in tokens:
        if re.fullmatch(r"\d+번", token) or re.fullmatch(r"\d+층", token) or re.fullmatch(r"\d+학년", token):
            protected.append(token)
    return protected


def _strong_terms(tokens: list[str], protected_terms: list[str]) -> list[str]:
    terms = [*protected_terms]
    for token in tokens:
        if token in GENERIC_QUERY_TERMS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        terms.append(token)
    return terms[:16]


def _required_terms_for_family(family: str, strong_terms: list[str], protected_terms: list[str]) -> list[str]:
    source = [*protected_terms, *strong_terms]
    if family == "building_location":
        preferred = [
            term
            for term in source
            if any(marker in term for marker in ("정보공학관", "건물", "층", "편의점", "캠퍼스맵"))
            or re.fullmatch(r"\d+번", term)
        ]
        return preferred[:4]
    if family == "department_curriculum":
        return [term for term in source if term in CURRICULUM_TERMS or "컴퓨터공학" in term][:4]
    if family == "person_title":
        return [term for term in source if term in PERSON_TERMS or term.endswith("총장")][:3]
    if family == "club_program":
        return [term for term in source if term.casefold() in {value.casefold() for value in CLUB_PROGRAM_TERMS}][:4]
    return []
