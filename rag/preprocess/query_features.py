"""Query feature helpers shared across RAG preprocessing and ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from rag.preprocess.domain_knowledge import DOMAIN_BLACKLIST, DOMAIN_PRIORITY_ORDER, DOMAIN_RULES, ENTITY_ALIASES
from rag.preprocess.dynamic_entities import get_dynamic_entity_aliases


_TOKEN_PATTERN = re.compile(r"[\uac00-\ud7a3A-Za-z0-9]+")
_BUILDING_NO_PATTERN = re.compile(r"\d+\s*\ubc88\s*\uac74\ubb3c")
_FLOOR_PATTERN = re.compile(r"\d+\s*\uce35")
_YEAR_MAJOR_PATTERN = re.compile(r"\d+\s*\ud559\ub144")
_DEPARTMENT_ANCHOR_PATTERN = re.compile(r"[\uac00-\ud7a3A-Za-z0-9]+(?:\ud559\uacfc|\uc804\uacf5|\ud559\ubd80)")

GENERIC_QUERY_TERMS = {
    "동의대",
    "동의대학교",
    "동의",
    "대학교",
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

GENERIC_FAMILY_INTENT_TERMS = {
    "운영시간",
    "이용시간",
    "시간",
    "시간표",
    "방법",
    "기간",
    "신청",
    "정보",
    "안내",
    "날짜",
    "일정",
    "종류",
    "확인",
    "조회",
}
GENERIC_QUERY_TERMS.update(GENERIC_FAMILY_INTENT_TERMS)

PROTECTED_LITERAL_TERMS = (
    "정보공학관",
    "정보관",
    "국제관",
    "산학협력관",
    "의료보건관",
    "지천관",
    "상영관",
    "학생회관",
    "수덕전",
    "수덕관",
    "콜라보라운지",
    "컴퓨터공학과",
    "컴공",
    "이수표",
    "전공필수",
    "졸업학점",
    "보강일정",
    "지정보강일",
    "학사일정",
    "중간고사",
    "기말고사",
    "휴강일",
    "수강신청",
    "계절학기",
    "계절수업",
    "국가장학금",
    "성적우수장학금",
    "성적우수장학생",
    "휴학",
    "전과",
    "재학증명서",
    "성적증명서",
    "제증명서",
    "학생식당",
    "헌혈의 집",
    "동아리",
    "IPP",
    "ipp",
    "총장",
    "역대총장",
    "연혁",
    "건물번호",
    "캠퍼스맵",
    "편의점",
)

FACILITY_TERMS = {
    "건물",
    "건물번호",
    "정보공학관",
    "정보관",
    "국제관",
    "산학협력관",
    "의료보건관",
    "지천관",
    "상영관",
    "학생회관",
    "수덕전",
    "수덕관",
    "콜라보라운지",
    "가야캠퍼스",
    "가야 캠퍼스",
    "찾아오시는길",
    "찾아오시는 길",
    "캠퍼스맵",
    "층",
    "위치",
    "주소",
    "편의점",
    "학생식당",
    "헌혈의 집",
    "복지문화시설",
    "편의시설",
    "시설",
}

SCHEDULE_TERMS = {
    "학사일정",
    "보강",
    "보강일정",
    "지정보강일",
    "중간고사",
    "기말고사",
    "휴강일",
    "시험",
    # 개강/종강/방학 관련
    "개강",
    "개강일",
    "종강",
    "종강일",
    "하계방학",
    "동계방학",
    "방학",
    # 졸업식 → 학위수여식과 동의어, scheduleList에 있음
    "학위수여식",
}

SEASONAL_COURSE_TERMS = {
    "계절학기",
    "계절수업",
    "하계",
    "동계",
    "하계계절수업",
    "동계계절수업",
}

COURSE_REGISTRATION_TERMS = {
    "수강신청",
    "수강정정",
    "장바구니",
}

SCHOLARSHIP_TERMS = {
    "장학금",
    "국가장학금",
    "국가장학",
    "신청기간",
    "신청 기간",
    "신청방법",
    "신청 방법",
}

SPECIFIC_SCHOLARSHIP_TERMS = {
    "성적우수장학금",
    "성적우수장학생",
    "동의복지장학금",
    "근로장학금",
    "국가근로장학금",
    "형제장학금",
    "나눔희망장학금",
    "나눔장학금",
    "희망장학금",
    "주거안정장학금",
    "국가고시합격장학금",
    "장학사정관제장학금",
    "다전공활성화장학금",
    "연구진흥장학금",
    "인문100년장학금",
}

SPECIFIC_SCHOLARSHIP_TERMS.update(
    {
        "성적우수장학금",
        "성적우수장학생",
        "성적우수 장학금",
        "성적우수",
        "근로장학금",
        "국가근로장학금",
        "형제 장학금",
        "나눔, 희망장학금",
        "나눔·희망장학금",
    }
)

ACADEMIC_ADMIN_TERMS = {
    "휴학",
    "복학",
    "전과",
    "군휴학",
    "일반휴학",
}

CERTIFICATE_TERMS = {
    "증명서",
    "재학증명서",
    "성적증명서",
    "졸업증명서",
    "제증명서",
    "발급",
}

LIBRARY_TERMS = {"도서관", "중앙도서관", "열람실", "자료실", "운영시간"}
LIBRARY_ANCHOR_TERMS = LIBRARY_TERMS - {"운영시간"}
SHUTTLE_TERMS = {"통학버스", "셔틀", "셔틀버스", "통버", "버스노선", "시간표", "노선"}
SHUTTLE_ANCHOR_TERMS = {"통학버스", "셔틀", "셔틀버스", "통버", "버스노선", "버스"}
TUITION_TERMS = {"등록금", "수업료", "학비", "납부", "고지서", "분납"}
TUITION_ANCHOR_TERMS = TUITION_TERMS - {"납부"}
CAREER_TERMS = {"취업", "진로", "현장실습", "IPP", "일학습", "인턴", "취업지원센터"}
CAREER_ANCHOR_TERMS = CAREER_TERMS
GRADE_TERMS = {"성적", "학점", "평점", "GPA", "출석"}
GRADE_ANCHOR_TERMS = GRADE_TERMS

HISTORY_TERMS = {
    "연혁",
    "역사",
    "대학현황",
}

WELFARE_FACILITY_TERMS = {
    "학생식당",
    "학식",
    "식당",
    "헌혈",
    "헌혈의 집",
    "편의점",
    "편의시설",
    "복지문화시설",
}

CAMPUS_ADDRESS_TERMS = {
    "동의대학교 위치",
    "동의대학교 주소",
    "동의대 위치",
    "동의대 주소",
}

DORMITORY_TERMS = {
    "기숙사",
    "생활관",
    "효민생활관",
    "제2효민생활관",
    "2효민생활관",
    "입사",
    "입사신청",
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


def _term_hit(terms: Iterable[str], values: set[str], joined: str, raw_text: str) -> bool:
    for term in terms:
        normalized = str(term or "").casefold()
        if normalized and (normalized in values or normalized in joined or normalized in raw_text):
            return True
    return False


def detect_query_family(query: str, terms: Iterable[str] | None = None) -> str:
    values = {term.casefold() for term in tokenize_koreanish(query)}
    values.update(str(term).casefold() for term in (terms or []) if term)
    joined = " ".join(values)
    raw_text = (query or "").casefold()
    if (
        "\uc878\uc5c5" in raw_text
        and any(term in raw_text for term in ("\ud559\uc810", "\uc774\uc218\ud559\uc810", "\uc878\uc5c5\ud559\uc810", "\uc878\uc5c5\uae30\uc900"))
        and _has_department_anchor(values, raw_text)
    ):
        return "department_curriculum"
    if "졸업" in raw_text and any(term in raw_text for term in ("학점", "요건", "이수", "자격", "심사")):
        return "graduation"
    if any(term.casefold() in raw_text for term in CAMPUS_ADDRESS_TERMS):
        return "campus_address"
    if _term_hit(WELFARE_FACILITY_TERMS, values, joined, raw_text):
        return "welfare_facility"
    if _term_hit(SPECIFIC_SCHOLARSHIP_TERMS, values, joined, raw_text) and (
        "장학" in raw_text or "장학생" in raw_text or "장학금" in raw_text or "ν븰" in raw_text
    ):
        return "specific_scholarship"
    if _term_hit(DORMITORY_TERMS, values, joined, raw_text):
        return "dormitory"
    if any(term.casefold() in values or term.casefold() in joined for term in HISTORY_TERMS):
        return "institution_history"
    if any(term.casefold() in values or term.casefold() in joined for term in CERTIFICATE_TERMS):
        return "certificate"
    if _term_hit(SHUTTLE_ANCHOR_TERMS, values, joined, raw_text):
        return "shuttle"
    if _term_hit(LIBRARY_ANCHOR_TERMS, values, joined, raw_text):
        return "library"
    if _term_hit(TUITION_ANCHOR_TERMS, values, joined, raw_text):
        return "tuition"
    if _term_hit(CAREER_ANCHOR_TERMS, values, joined, raw_text):
        return "career"
    if _term_hit(GRADE_ANCHOR_TERMS, values, joined, raw_text):
        return "grade"
    if any(term.casefold() in values or term.casefold() in joined for term in ACADEMIC_ADMIN_TERMS):
        return "academic_admin"
    if any(term.casefold() in values or term.casefold() in joined for term in SEASONAL_COURSE_TERMS) and (
        "수강신청" in joined or "수강" in joined
    ):
        return "seasonal_course_registration"
    if any(term.casefold() in values or term.casefold() in joined for term in COURSE_REGISTRATION_TERMS):
        return "course_registration"
    if any(term.casefold() in values or term.casefold() in joined for term in FACILITY_TERMS):
        return "building_location"
    if any(term.casefold() in values or term.casefold() in joined for term in SCHEDULE_TERMS):
        return "academic_schedule"
    if any(term.casefold() in values or term.casefold() in joined for term in CURRICULUM_TERMS):
        return "department_curriculum"
    if any(term.casefold() in values or term.casefold() in joined for term in PERSON_TERMS):
        return "person_title"
    if any(term.casefold() in values or term.casefold() in joined for term in CLUB_PROGRAM_TERMS):
        return "club_program"
    return "general"


def _has_department_anchor(values: set[str], raw_text: str) -> bool:
    if _DEPARTMENT_ANCHOR_PATTERN.search(raw_text or ""):
        return True
    return any(value.endswith(("\ud559\uacfc", "\uc804\uacf5", "\ud559\ubd80")) for value in values)


def _domain_priority(domain: str) -> int:
    try:
        return DOMAIN_PRIORITY_ORDER.index(domain)
    except ValueError:
        return len(DOMAIN_PRIORITY_ORDER)


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
        if score > best_score or (
            score == best_score
            and best_domain is not None
            and _domain_priority(domain) < _domain_priority(best_domain)
        ):
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
            if any(marker in term for marker in ("정보공학관", "건물", "층", "편의점", "캠퍼스맵", "위치", "주소"))
            or re.fullmatch(r"\d+번", term)
        ]
        return preferred[:4]
    if family == "campus_address":
        return [term for term in source if any(marker in term for marker in ("주소", "가야", "찾아오시는"))][:4]
    if family == "welfare_facility":
        return [term for term in source if term in WELFARE_FACILITY_TERMS or any(marker in term for marker in ("식당", "헌혈", "편의"))][:4]
    if family == "academic_schedule":
        return [term for term in source if term in SCHEDULE_TERMS or any(
            marker in term for marker in ("보강", "학사일정", "고사", "개강", "종강", "방학", "학위수여식")
        )][:4]
    if family == "seasonal_course_registration":
        return [term for term in source if "계절" in term or "수강" in term or term in SEASONAL_COURSE_TERMS][:4]
    if family == "course_registration":
        return [term for term in source if "수강신청" in term or term in {"기간", "일정", "1학기", "2학기"}][:4]
    if family in {"scholarship", "specific_scholarship"}:
        return [term for term in source if "장학" in term or "신청" in term or "성적우수" in term][:4]
    if family == "academic_admin":
        return [term for term in source if term in ACADEMIC_ADMIN_TERMS or term in {"신청", "방법", "절차"}][:4]
    if family == "dormitory":
        return [term for term in source if term in DORMITORY_TERMS or "기숙사" in term or "생활관" in term][:4]
    if family == "graduation":
        preferred = [
            term
            for term in source
            if any(
                marker in term
                for marker in (
                    "졸업",
                    "학점",
                    "요건",
                    "이수",
                    "자격",
                    "심사",
                )
            )
        ]
        return preferred[:4] or ["졸업"]
    if family == "certificate":
        return [term for term in source if term in CERTIFICATE_TERMS or "증명서" in term][:4]
    if family == "library":
        return [term for term in source if term in LIBRARY_TERMS or "도서관" in term][:4]
    if family == "shuttle":
        return [term for term in source if term in SHUTTLE_TERMS or "버스" in term][:4]
    if family == "tuition":
        return [term for term in source if term in TUITION_TERMS or "등록금" in term][:4]
    if family == "career":
        return [term for term in source if term in CAREER_TERMS or "취업" in term or "실습" in term][:4]
    if family == "grade":
        return [term for term in source if term in GRADE_TERMS or "성적" in term or "학점" in term][:4]
    if family == "institution_history":
        return [term for term in source if term in HISTORY_TERMS or "연혁" in term][:4]
    if family == "department_curriculum":
        return [term for term in source if term in CURRICULUM_TERMS or "컴퓨터공학" in term][:4]
    if family == "person_title":
        return [term for term in source if term in PERSON_TERMS or term.endswith("총장")][:3]
    if family == "club_program":
        return [term for term in source if term.casefold() in {value.casefold() for value in CLUB_PROGRAM_TERMS}][:4]
    return []
