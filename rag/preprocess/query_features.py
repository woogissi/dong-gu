"""Query feature helpers shared across RAG preprocessing and ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from rag.preprocess.domain_knowledge import DOMAIN_BLACKLIST, DOMAIN_RULES, ENTITY_ALIASES
from rag.preprocess.dynamic_entities import get_dynamic_entity_aliases


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
GENERIC_QUERY_TERMS.update(DOMAIN_BLACKLIST)

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
    domain: str | None = None
    category: str | None = None
    protected_terms: list[str] = field(default_factory=list)
    strong_terms: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)
    source_boosts: list[str] = field(default_factory=list)
    rule_hit_names: list[str] = field(default_factory=list)

    def to_log_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "domain": self.domain,
            "category": self.category,
            "protected_terms": self.protected_terms,
            "strong_terms": self.strong_terms,
            "required_terms": self.required_terms,
            "source_boosts": self.source_boosts,
            "rule_hit_names": self.rule_hit_names,
        }


def extract_query_features(query: str, keywords: Iterable[str] | None = None) -> QueryFeatures:
    text = query or ""
    keyword_values = [str(value) for value in (keywords or []) if value]
    tokens = tokenize_koreanish(" ".join([text, *keyword_values]))
    protected = _protected_terms(text, keyword_values, tokens)
    strong = _strong_terms(tokens, protected)
    domain, domain_rule_hits = detect_domain(text, [*strong, *protected])
    family = detect_query_family(text, [*strong, *protected])
    required = _required_terms_for_family(family, strong, protected)
    rule = DOMAIN_RULES.get(domain or "", {})
    return QueryFeatures(
        family=family,
        domain=domain,
        category=str(rule.get("category")) if rule.get("category") else None,
        protected_terms=ordered_unique(protected),
        strong_terms=ordered_unique(strong),
        required_terms=ordered_unique(required),
        source_boosts=[str(value) for value in rule.get("source_boosts", [])],
        rule_hit_names=domain_rule_hits,
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


def detect_domain(query: str, terms: Iterable[str] | None = None) -> tuple[str | None, list[str]]:
    query_text = (query or "").casefold()
    term_text = " ".join(str(term) for term in (terms or []) if term).casefold()
    haystack = f"{query_text} {term_text}"
    best_domain: str | None = None
    best_score = 0
    hits: list[str] = []
    for domain, rule in DOMAIN_RULES.items():
        score = 0
        matched_terms: list[str] = []
        for keyword in rule.get("keywords", []):
            text = str(keyword)
            if text and text.casefold() not in DOMAIN_BLACKLIST and text.casefold() in haystack:
                score += 3 if text.casefold() in query_text else 1
                matched_terms.append(text)
        synonyms = rule.get("synonyms", {})
        if isinstance(synonyms, dict):
            for key, values in synonyms.items():
                for value in [key, *values]:
                    text = str(value)
                    if text and text.casefold() not in DOMAIN_BLACKLIST and text.casefold() in haystack:
                        score += 2 if text.casefold() in query_text else 1
                        matched_terms.append(text)
        if score > best_score:
            best_domain = domain
            best_score = score
            hits = [f"domain:{domain}:{term}" for term in ordered_unique(matched_terms)]
    return best_domain, hits


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
    for canonical, aliases in _merged_entity_aliases().items():
        if canonical in text or any(alias in text for alias in aliases):
            protected.append(canonical)
            protected.extend(alias for alias in aliases if alias in text)
    for token in tokens:
        if re.fullmatch(r"\d+번", token) or re.fullmatch(r"\d+층", token) or re.fullmatch(r"\d+학년", token):
            protected.append(token)
    return protected


def _merged_entity_aliases() -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in ENTITY_ALIASES.items()}
    for canonical, aliases in get_dynamic_entity_aliases().items():
        merged.setdefault(canonical, [])
        merged[canonical] = ordered_unique([*merged[canonical], *aliases])
    return merged


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
