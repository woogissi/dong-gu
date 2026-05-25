"""Rule-based reranking for retrieved RAG documents."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from rag.preprocess.query_features import (
    extract_query_features,
    required_entity_match_score,
    tokenize_koreanish,
    ui_noise_hits,
)
from rag.schemas.retrieved_doc import RetrievedDoc

_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_WEAK_RELEVANCE_TOKENS = {
    "",
    "deu",
    "\uac00\ub2a5",
    "\uac1c\uc218",
    "\uae30\uac04",
    "\ubc29\ubc95",
    "\ubc88\ud638",
    "\uc54c\ub824\uc918",
    "\uc5b4\ub5bb\uac8c",
    "\uc624\ub298",
    "\uc704\uce58",
    "\uc774\ub984",
    "\uc77c\uc815",
    "\uc815\ubcf4",
    "\uc885\ub958",
    "\uc2dc\uc810",
    "\uc5b8\uc81c",
    "\uc5f0\ub77d\ucc98",
    "동의",
    "동의대",
    "동의대학교",
    "대학교",
}

_EXIF_NOISE_PATTERNS = [
    "원본 그림의 이름",
    "사진 찍은 날짜",
    "카메라 제조 업체",
    "카메라 모델",
    "iso 감도",
    "노출 시간",
    "조리개 값",
    "gps 정보",
    "이미지 크기",
    "스캔 날짜",
    "ocr confidence",
    "image metadata",
    "exif",
]

_FACILITY_QUERY_TERMS = {
    "건물",
    "건물번호",
    "강의실",
    "위치",
    "가는",
    "가는길",
    "길",
    "호실",
    "캠퍼스",
    "학과사무실",
}
_FACILITY_QUERY_TERMS.update(
    {
        "호관",
        "시설",
        "국제관",
        "산학협력관",
        "의료보건관",
        "찾아오시는",
        "찾아오시는길",
        "정보관",
        "정보공학관",
        "지천관",
        "상영관",
        "학생회관",
        "라운지",
        "콜라보라운지",
    }
)
_FACILITY_SECTION_TERMS = {"건물", "강의실", "학과사무실", "위치", "호실", "캠퍼스"}
_FACILITY_SECTION_TERMS.update(
    {
        "호관",
        "시설",
        "찾아오시는",
        "찾아오시는길",
        "찾아오시는 길",
        "가야 캠퍼스",
        "주소",
        "캠퍼스맵",
        "복지문화시설",
        "편의점",
        "학생식당",
        "헌혈의 집",
        "국제관",
        "산학협력관",
        "의료보건관",
        "정보관",
        "정보공학관",
        "지천관",
        "상영관",
        "학생회관",
        "라운지",
        "콜라보라운지",
    }
)
_FACILITY_NOISE_TERMS = {"모집공고", "입주기업", "회의자료", "대의원", "공문", "첨부"}
_FACILITY_NOISE_TERMS.update({"채용", "신청", "서식", "입찰", "수강신청"})

_INSTITUTION_QUERY_TERMS = {"총장", "역대총장", "역대", "학장", "조직", "기관", "소개"}
_INSTITUTION_SECTION_TERMS = {"총장", "역대총장", "인사말", "대학소개", "조직", "연혁"}
_INSTITUTION_SOURCE_TERMS = {"institution", "static", "profile", "history"}
_INSTITUTION_NOISE_TERMS = {"council", "회의자료", "대의원", "첨부"}

_DOMAIN_SECTION_TERMS = {
    "장학금": {"장학", "장학금", "신청", "학자금"},
    "scholarship": {"장학", "장학금", "국가장학금", "신청"},
    "통학버스": {"통학버스", "버스", "노선", "시간표"},
    "도서관": {"도서관", "운영시간", "자료실", "열람실"},
    "학사일정": {"학사일정", "일정", "수강", "보강", "시험"},
    "academic_schedule": {"학사일정", "학사정보", "일정", "보강", "보강일정"},
    "course_registration": {"수강신청", "수강", "정정", "1학기", "학사공지"},
    "seasonal_course_registration": {"계절수업", "계절학기", "하계", "동계", "수강신청"},
    "department_curriculum": {"컴퓨터공학", "컴퓨터공학과", "이수표", "전공필수", "교육과정"},
    "specific_scholarship": {"성적우수", "성적우수장학금", "성적우수장학생", "장학금"},
    "academic_admin": {"휴학", "복학", "전과", "신청", "학사지원"},
    "certificate": {"제증명서", "증명서", "재학증명서", "성적증명서", "발급"},
    "institution_history": {"연혁", "연도별 연혁", "대학현황", "1960년대", "2020년대"},
    "welfare_facility": {"복지문화시설", "편의·복지", "학생식당", "헌혈의 집", "편의점", "편의시설"},
    "campus_address": {"가야 캠퍼스", "찾아오시는 길", "캠퍼스안내", "주소"},
    "등록금": {"등록금", "납부", "수납", "고지서"},
}
_DOMAIN_REQUIRED_TERMS = {
    "장학금": {"장학", "장학금", "학자금"},
    "scholarship": {"장학", "장학금", "국가장학금"},
    "통학버스": {"통학버스", "버스", "셔틀버스"},
    "도서관": {"도서관", "중앙도서관"},
    "학사일정": {"학사일정"},
    "academic_schedule": {"학사일정"},
    "course_registration": {"수강신청"},
    "seasonal_course_registration": {"계절", "계절수업", "수강신청"},
    "department_curriculum": {"컴퓨터공학", "이수표"},
    "specific_scholarship": {"성적우수", "장학금"},
    "academic_admin": {"휴학", "복학", "전과"},
    "certificate": {"증명서", "제증명서"},
    "institution_history": {"연혁"},
    "welfare_facility": {"복지문화시설"},
    "campus_address": {"가야", "캠퍼스"},
    "등록금": {"등록금", "납부", "수납"},
}
_SERVICE_DOMAIN_NOISE_SOURCES = {"bids", "council_notice"}
_NOTICE_QUERY_TERMS = {"모집공고", "채용공고", "신청서", "회의자료", "첨부", "첨부파일", "서식", "입찰", "공고"}
_NOISY_SOURCE_TYPES = {"bids", "council_notice", "external_notice"}
_STATIC_SOURCE_TYPES = {"static", "index", "menu"}
_UI_NOISE_PATTERNS = (
    "본문 바로가기",
    "게시물 좌측으로 이동",
    "게시물 우측으로 이동",
    "사이트맵",
    "로그인",
    "회원가입",
    "more",
    "sns",
    "quick menu",
)
_FACULTY_QUERY_TERMS = {"교수", "교수님", "교수소개", "교수진", "faculty"}
_LIFELONG_CONTEXT_TERMS = {"평생교육원", "음악학사", "creditbank", "lifelong"}


def rerank_documents(
    docs: list[RetrievedDoc],
    *,
    query: str,
    keywords: list[str] | None = None,
    category: str | None = None,
    filters: dict[str, list[str]] | None = None,
) -> list[RetrievedDoc]:
    """Return documents ordered by retrieval score plus lightweight relevance signals."""
    if not docs:
        return []

    keywords = keywords or []
    filters = filters or {}
    query_tokens = _tokenize(query)
    keyword_tokens = _dedupe_tokens([*keywords, *query_tokens])
    query_features = extract_query_features(query, keyword_tokens)
    keyword_tokens = _dedupe_tokens([*query_features.strong_terms, *keyword_tokens])
    max_base_score = max((doc.score for doc in docs), default=0.0)

    reranked: list[tuple[float, int, RetrievedDoc]] = []
    for index, doc in enumerate(docs):
        signals = _score_doc(
            doc=doc,
            query=query,
            query_tokens=query_tokens,
            keyword_tokens=keyword_tokens,
            query_features=query_features.to_log_dict(),
            category=category,
            filters=filters,
            max_base_score=max_base_score,
        )
        rerank_score = round(
            sum(value for key, value in signals.items() if key != "noise_score"),
            6,
        )
        reranked_doc = _copy_with_rerank_metadata(doc, rerank_score, signals)
        reranked.append((rerank_score, index, reranked_doc))

    reranked.sort(key=lambda item: (-item[0], item[1]))
    return [doc for _, _, doc in reranked]


def _score_doc(
    *,
    doc: RetrievedDoc,
    query: str,
    query_tokens: list[str],
    keyword_tokens: list[str],
    query_features: dict[str, Any],
    category: str | None,
    filters: dict[str, list[str]],
    max_base_score: float,
) -> dict[str, float]:
    title = doc.title or ""
    section_title = str(doc.metadata.get("section_title") or "")
    content = doc.content or ""
    title_tokens = set(_tokenize(title))
    section_title_tokens = set(_tokenize(section_title))
    content_tokens = set(_tokenize(content))
    title_section_text = f"{title}\n{section_title}".lower()
    full_text = f"{title}\n{section_title}\n{content}".lower()
    faculty_entity = _extract_faculty_entity(query, keyword_tokens)
    query_family = _detect_query_family(query_tokens, keyword_tokens)
    feature_family = str(query_features.get("family") or "")
    if feature_family and feature_family != "general":
        query_family = _reranker_family_name(feature_family)
    required_terms = [str(value).lower() for value in query_features.get("required_terms") or [] if value]

    base_score = _normalized_base_score(doc.score, max_base_score)
    title_match = _coverage_score(keyword_tokens, title_tokens) * 1.8
    section_title_match = _coverage_score(keyword_tokens, section_title_tokens) * 2.4
    content_match = _coverage_score(keyword_tokens, content_tokens) * 0.8
    exact_query_match = 0.8 if query.strip() and query.strip().lower() in full_text else 0.0
    strong_term_match = _strong_term_match_score(keyword_tokens, full_text)
    missing_strong_terms = _missing_strong_terms_penalty(keyword_tokens, full_text)
    attachment_noise = _attachment_noise_penalty(
        doc,
        strong_term_match=strong_term_match,
        title_match=title_match,
        section_title_match=section_title_match,
        query_tokens=keyword_tokens,
    )
    exif_noise = _exif_noise_penalty(content)
    ui_static_noise = _ui_static_noise_penalty(doc, full_text)
    source_type_noise = _source_type_noise_penalty(doc, keyword_tokens, title_section_text, full_text)
    query_family_boost = _query_family_boost(
        doc=doc,
        query_family=query_family,
        title_section_text=title_section_text,
        full_text=full_text,
    )
    canonical_source_priority = _canonical_source_priority(
        doc=doc,
        query_family=query_family,
        title_section_text=title_section_text,
    )
    verified_title_boost = _verified_title_boost(query_family, title_section_text)
    required_heading_match = _required_heading_match_score(query_family, title_section_text)
    required_entity_match = required_entity_match_score(required_terms, full_text)
    faculty_entity_match = _faculty_entity_match_score(faculty_entity, full_text)
    faculty_entity_penalty = _faculty_entity_penalty(
        faculty_entity=faculty_entity,
        doc=doc,
        query=query,
        title_section_text=title_section_text,
        full_text=full_text,
    )
    query_family_penalty = _query_family_penalty(
        doc=doc,
        query_family=query_family,
        title_section_text=title_section_text,
        full_text=full_text,
    )
    if required_terms and required_entity_match == 0.0:
        query_family_penalty -= 1.2
    category_match = _category_match_score(doc, category, filters)
    recency = _recency_score(doc.metadata.get("published_at"))
    noise_score = abs(
        min(attachment_noise, 0.0)
        + min(exif_noise, 0.0)
        + min(ui_static_noise, 0.0)
        + min(source_type_noise, 0.0)
        + min(faculty_entity_penalty, 0.0)
        + min(query_family_penalty, 0.0)
    )

    return {
        "base_score": round(base_score, 6),
        "title_match": round(title_match, 6),
        "section_title_match": round(section_title_match, 6),
        "content_match": round(content_match, 6),
        "exact_query_match": round(exact_query_match, 6),
        "strong_term_match": round(strong_term_match, 6),
        "missing_strong_terms": round(missing_strong_terms, 6),
        "attachment_noise": round(attachment_noise, 6),
        "exif_noise": round(exif_noise, 6),
        "ui_static_noise": round(ui_static_noise, 6),
        "source_type_noise": round(source_type_noise, 6),
        "query_family_boost": round(query_family_boost, 6),
        "canonical_source_priority": round(canonical_source_priority, 6),
        "verified_title_boost": round(verified_title_boost, 6),
        "required_heading_match": round(required_heading_match, 6),
        "required_entity_match": round(required_entity_match, 6),
        "faculty_entity_match": round(faculty_entity_match, 6),
        "faculty_entity_penalty": round(faculty_entity_penalty, 6),
        "query_family_penalty": round(query_family_penalty, 6),
        "category_match": round(category_match, 6),
        "recency": round(recency, 6),
        "noise_score": round(noise_score, 6),
    }


def _normalized_base_score(score: float, max_base_score: float) -> float:
    if max_base_score <= 0:
        return 0.0
    return min(score / max_base_score, 1.0) * 1.2


def _coverage_score(expected_tokens: list[str], actual_tokens: set[str]) -> float:
    if not expected_tokens or not actual_tokens:
        return 0.0
    matched = sum(1 for token in expected_tokens if _token_matches(token, actual_tokens))
    return matched / len(expected_tokens)


def _token_matches(expected_token: str, actual_tokens: set[str]) -> bool:
    if expected_token in actual_tokens:
        return True
    if len(expected_token) < 2:
        return False
    return any(
        expected_token in actual_token or actual_token in expected_token
        for actual_token in actual_tokens
        if len(actual_token) >= 2
    )


def _strong_tokens(tokens: list[str]) -> list[str]:
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in _WEAK_RELEVANCE_TOKENS
    ]


def _extract_faculty_entity(query: str, tokens: list[str]) -> str:
    if not _is_faculty_query(query, tokens):
        return ""
    if _is_department_faculty_list_query(query) and not _has_explicit_faculty_name(query):
        return ""
    candidates = [query, *tokens]
    for text in candidates:
        normalized = str(text or "").strip()
        if not normalized:
            continue
        for pattern in (
            r"([가-힣]{2,5})\s*교수(?:님)?",
            r"교수(?:님)?\s*([가-힣]{2,5})",
        ):
            match = re.search(pattern, normalized)
            if match and _is_valid_faculty_entity(match.group(1)):
                return match.group(1)
        if re.fullmatch(r"[가-힣]{2,5}", normalized) and _is_valid_faculty_entity(normalized):
            return normalized
    return ""


def _is_faculty_query(query: str, tokens: list[str]) -> bool:
    joined = " ".join([query.lower(), *tokens])
    return any(term.lower() in joined for term in _FACULTY_QUERY_TERMS)


def _is_department_faculty_list_query(query: str) -> bool:
    text = re.sub(r"\s+", "", query or "").lower()
    if not any(term in text for term in ("교수목록", "교수소개", "교수진", "전임교수")):
        return False
    return any(marker in text for marker in ("학과", "전공", "학부", "대학원"))


def _has_explicit_faculty_name(query: str) -> bool:
    for pattern in (r"([가-힣]{2,5})\s*교수(?:님)?", r"교수(?:님)?\s*([가-힣]{2,5})"):
        for match in re.finditer(pattern, query or ""):
            if _is_valid_faculty_entity(match.group(1)):
                return True
    return False


def _is_valid_faculty_entity(value: str) -> bool:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"[가-힣]{2,5}", candidate):
        return False
    if candidate in {"교수", "교수님", "정보", "목록", "소개", "교수진", "전임교수"}:
        return False
    return not any(marker in candidate for marker in ("학과", "전공", "학부", "대학원", "목록", "소개"))


def _faculty_entity_match_score(entity: str, full_text: str) -> float:
    if not entity:
        return 0.0
    return 1.8 if entity.lower() in full_text else 0.0


def _faculty_entity_penalty(
    *,
    faculty_entity: str,
    doc: RetrievedDoc,
    query: str,
    title_section_text: str,
    full_text: str,
) -> float:
    if not faculty_entity:
        return 0.0
    penalty = 0.0
    if faculty_entity.lower() not in full_text:
        penalty -= 2.4
    if _is_lifelong_faculty_noise(doc, query, title_section_text):
        penalty -= 1.8
    return penalty


def _is_lifelong_faculty_noise(doc: RetrievedDoc, query: str, title_section_text: str) -> bool:
    query_text = query.lower()
    if any(term in query_text for term in _LIFELONG_CONTEXT_TERMS):
        return False
    source_type = _normalize_value(doc.metadata.get("source_type"))
    source = _normalize_value(doc.source)
    title_text = title_section_text.lower()
    return (
        source_type == "lifelong"
        or "lifelong.deu.ac.kr" in source
        or "creditbank" in source
        or "평생교육원" in title_text
        or "음악학사" in title_text
    )


def _strong_term_match_score(tokens: list[str], full_text: str) -> float:
    strong_tokens = _strong_tokens(tokens)
    if not strong_tokens:
        return 0.0
    matched = sum(1 for token in strong_tokens if token in full_text)
    return min(matched / len(strong_tokens), 1.0) * 1.2


def _missing_strong_terms_penalty(tokens: list[str], full_text: str) -> float:
    strong_tokens = _strong_tokens(tokens)
    if not strong_tokens:
        return 0.0
    return 0.0 if any(token in full_text for token in strong_tokens) else -2.0


def _attachment_noise_penalty(
    doc: RetrievedDoc,
    strong_term_match: float,
    title_match: float,
    section_title_match: float,
    query_tokens: list[str],
) -> float:
    section_type = _normalize_value(doc.metadata.get("section_type"))
    if section_type != "attachment":
        return 0.0
    if _is_explicit_notice_or_attachment_query(query_tokens):
        return 0.0
    direct_heading_match = title_match + section_title_match
    if direct_heading_match >= 0.9:
        return 0.0
    if direct_heading_match > 0.0 and strong_term_match >= 0.8:
        return -0.2
    if strong_term_match > 0.0:
        return -0.8
    return -1.2


def _ui_static_noise_penalty(doc: RetrievedDoc, full_text: str) -> float:
    source_type = _normalize_value(doc.metadata.get("source_type"))
    source = _normalize_value(doc.source)
    section_title = _normalize_value(doc.metadata.get("section_title"))
    content_length = _safe_int(doc.metadata.get("content_length"), len(doc.content or ""))
    penalty = 0.0
    if source_type in _STATIC_SOURCE_TYPES:
        penalty -= 0.5
    if any(marker in source for marker in ("index.do", "main.do", "/main", "sitemap")):
        penalty -= 0.4
    if section_title in {"menu", "navigation", "breadcrumb"}:
        penalty -= 0.6
    ui_hits = max(
        sum(1 for pattern in _UI_NOISE_PATTERNS if pattern.lower() in full_text),
        ui_noise_hits(full_text),
    )
    if ui_hits >= 4:
        penalty -= 1.0
    elif ui_hits >= 2:
        penalty -= 0.5
    if 0 < content_length < 120:
        penalty -= 0.4
    return penalty


def _source_type_noise_penalty(
    doc: RetrievedDoc,
    query_tokens: list[str],
    title_section_text: str,
    full_text: str,
) -> float:
    if _is_explicit_notice_or_attachment_query(query_tokens):
        return 0.0
    source_type = _normalize_value(doc.metadata.get("source_type"))
    if source_type not in _NOISY_SOURCE_TYPES:
        return 0.0
    strong_match = _strong_term_match_score(query_tokens, f"{title_section_text}\n{full_text}")
    if strong_match >= 0.7:
        return -0.2
    return -0.8


def _is_explicit_notice_or_attachment_query(tokens: list[str]) -> bool:
    token_set = set(tokens)
    joined = " ".join(tokens)
    return bool(token_set & _NOTICE_QUERY_TERMS or any(term in joined for term in _NOTICE_QUERY_TERMS))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _exif_noise_penalty(content: str) -> float:
    normalized = content.lower()
    matched = sum(1 for pattern in _EXIF_NOISE_PATTERNS if pattern.lower() in normalized)
    if matched >= 4:
        return -1.5
    if matched >= 2:
        return -0.9
    if matched >= 1:
        return -0.4
    return 0.0


def _detect_query_family(query_tokens: list[str], keyword_tokens: list[str]) -> str:
    tokens = set(query_tokens) | set(keyword_tokens)
    joined = " ".join(tokens)
    if tokens & _FACILITY_QUERY_TERMS or "가는 길" in joined:
        return "facility"
    if "수강신청" in tokens or "수강신청" in joined:
        return "course_registration"
    if "국가장학금" in tokens or "국가장학금" in joined:
        return "scholarship"
    if "역대총장" in tokens or "총장" in tokens or tokens & _INSTITUTION_QUERY_TERMS:
        return "institution"
    for family, terms in _DOMAIN_SECTION_TERMS.items():
        if family in tokens or tokens & terms:
            return family
    return "general"


def _reranker_family_name(feature_family: str) -> str:
    if feature_family == "building_location":
        return "facility"
    if feature_family == "person_title":
        return "institution"
    return feature_family


def _query_family_boost(
    *,
    doc: RetrievedDoc,
    query_family: str,
    title_section_text: str,
    full_text: str,
) -> float:
    source_type = _normalize_value(doc.metadata.get("source_type"))
    if query_family == "campus_address":
        title_bonus = 1.6 if any(term in title_section_text for term in ("가야 캠퍼스", "찾아오시는 길", "캠퍼스안내")) else 0.0
        source_boost = 0.5 if source_type in {"institution", "campus"} else 0.0
        return min(title_bonus + source_boost, 2.4)
    if query_family == "welfare_facility":
        title_bonus = 1.8 if "복지문화시설" in title_section_text else 0.0
        facility_hits = _term_hits(_DOMAIN_SECTION_TERMS["welfare_facility"], f"{title_section_text}\n{full_text}")
        return min(title_bonus + facility_hits * 0.35, 2.4)
    if query_family == "facility":
        section_hits = _term_hits(_FACILITY_SECTION_TERMS, title_section_text)
        source_boost = 0.5 if any(term in source_type for term in ("campus", "facility", "institution")) else 0.0
        title_bonus = 0.0
        if any(term in title_section_text for term in ("캠퍼스맵", "찾아오시는 길", "가야 캠퍼스", "복지문화시설")):
            title_bonus = 1.1
        return min(section_hits * 0.65 + source_boost + title_bonus, 2.4)
    if query_family == "institution":
        section_hits = _term_hits(_INSTITUTION_SECTION_TERMS, title_section_text)
        source_boost = 0.7 if any(term in source_type for term in _INSTITUTION_SOURCE_TERMS) else 0.0
        return min(section_hits * 0.65 + source_boost, 1.8)
    if query_family == "academic_schedule":
        title_bonus = 2.0 if "학사일정" in title_section_text else 0.0
        body_hits = _term_hits(_DOMAIN_SECTION_TERMS["academic_schedule"], full_text)
        return min(title_bonus + body_hits * 0.12, 2.6)
    if query_family == "seasonal_course_registration":
        title_bonus = 1.8 if any(term in title_section_text for term in ("계절수업", "하계계절수업", "하계 계절수업")) else 0.0
        if "2026-하계 계절수업 안내" in title_section_text:
            title_bonus += 1.2
        return min(title_bonus + _term_hits(_DOMAIN_SECTION_TERMS["seasonal_course_registration"], full_text) * 0.15, 3.0)
    if query_family == "specific_scholarship":
        return 2.4 if any(term in title_section_text for term in ("성적우수장학금", "성적우수장학생", "성적우수")) else 0.0
    if query_family == "academic_admin":
        title_bonus = 1.8 if any(term in title_section_text for term in ("휴학", "전과", "복학")) else 0.0
        first_heading = title_section_text.splitlines()[0].strip()
        if first_heading in {"휴학", "전과", "복학"}:
            title_bonus += 2.2
        return min(title_bonus + _term_hits(_DOMAIN_SECTION_TERMS["academic_admin"], full_text) * 0.12, 4.0)
    if query_family == "graduation":
        title_bonus = 0.0
        graduation_title_terms = (
            "\ud559\uc0ac\uc815\ubcf4 \uc885\ud569\uc548\ub0b4",
            "\ud559\uc0ac\uc815\ubcf4",
            "\ud559\uce59",
            "\uc878\uc5c5\uc694\uac74",
            "\uc878\uc5c5\ud559\uc810",
        )
        if any(term in title_section_text for term in graduation_title_terms):
            title_bonus += 2.8
        if "\ud559\uc0ac\uc815\ubcf4 \uc885\ud569\uc548\ub0b4" in title_section_text:
            title_bonus += 1.0
        if "\uc878\uc5c5" in title_section_text:
            title_bonus += 1.2
        body_hits = _term_hits(
            {
                "\uc878\uc5c5",
                "\uc878\uc5c5\ud559\uc810",
                "\uc878\uc5c5\uc694\uac74",
                "\uc774\uc218\ud559\uc810",
                "\uc218\ub8cc",
                "\ud559\uce59",
            },
            full_text,
        )
        source_boost = 0.5 if source_type in {"academic_notice", "academic", "institution"} else 0.0
        return min(title_bonus + body_hits * 0.25 + source_boost, 5.0)
    if query_family == "certificate":
        return 2.2 if any(term in title_section_text for term in ("제증명서", "증명서 발급", "재학증명서", "성적증명서")) else 0.0
    if query_family == "institution_history":
        title_bonus = 2.2 if any(term in title_section_text for term in ("연도별 연혁", "대학현황", "1960년대", "1970년대", "1980년대", "1990년대", "2000년대", "2010년대", "2020년대")) else 0.0
        return min(title_bonus + _term_hits(_DOMAIN_SECTION_TERMS["institution_history"], full_text) * 0.1, 2.6)
    domain_terms = _DOMAIN_SECTION_TERMS.get(query_family)
    if domain_terms:
        heading_hits = _term_hits(domain_terms, title_section_text)
        body_hits = _term_hits(domain_terms, full_text)
        return min(heading_hits * 0.45 + body_hits * 0.15, 1.2)
    return 0.0


def _canonical_source_priority(*, doc: RetrievedDoc, query_family: str, title_section_text: str) -> float:
    if query_family not in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return 0.0

    source = _normalize_value(doc.source)
    source_type = _normalize_value(doc.metadata.get("source_type"))
    title = title_section_text.casefold()
    central_bonus = 0.0
    if doc.metadata.get("is_canonical_notice"):
        central_bonus += 2.2
    if doc.metadata.get("canonical_source_supplement"):
        central_bonus += 2.0
    if any(marker in source for marker in ("dess.deu.ac.kr", "www.deu.ac.kr/www", "www.deu.ac.kr/deu")):
        central_bonus += 0.9
    if source_type in {"institution", "academic_notice", "academic", "campus"}:
        central_bonus += 0.35
    if any(term in title for term in ("학사공지", "학사지원", "학사일정", "수강신청")):
        central_bonus += 0.35

    duplicate_penalty = 0.0
    if source_type == "department" or re.search(r"/[a-z0-9_-]+/sub0[67]_", source):
        duplicate_penalty -= 0.7
    if source_type == "department" and any(term in title for term in ("수강신청 안내", "보강일정", "학사일정")):
        duplicate_penalty -= 0.3

    return max(min(central_bonus + duplicate_penalty, 3.0), -1.0)


def _verified_title_boost(query_family: str, title_section_text: str) -> float:
    first_heading = title_section_text.splitlines()[0].strip()
    title_text = first_heading or title_section_text
    family_headings = {
        "academic_schedule": ("학사일정",),
        "course_registration": ("수강신청 안내",),
        "seasonal_course_registration": ("2026-하계 계절수업 안내",),
        "campus_address": ("찾아오시는 길", "가야 캠퍼스"),
        "facility": ("캠퍼스맵",),
        "welfare_facility": ("복지문화시설",),
        "department_curriculum": ("이수표",),
        "scholarship": ("국가장학금", "scholarship"),
        "specific_scholarship": ("성적우수장학금", "성적우수장학생", "성적우수"),
        "institution": ("역대총장",),
        "person_title": ("역대총장",),
        "certificate": ("제증명서", "증명서 발급"),
        "institution_history": ("연혁", "대학현황"),
    }
    verified_headings = family_headings.get(query_family, ())
    return 1.5 if any(term in title_text for term in verified_headings) else 0.0


def _query_family_penalty(
    *,
    doc: RetrievedDoc,
    query_family: str,
    title_section_text: str,
    full_text: str,
) -> float:
    source_type = _normalize_value(doc.metadata.get("source_type"))
    section_type = _normalize_value(doc.metadata.get("section_type"))
    if query_family == "facility":
        penalty = 0.0
        if _term_hits(_FACILITY_NOISE_TERMS, title_section_text) > 0:
            penalty -= 1.8
        if source_type in {"job", "scholarship", "external_notice", "bids"}:
            penalty -= 1.6
        if "국제관" in full_text and "국제관광" in title_section_text:
            penalty -= 2.0
        if "산학협력관" in full_text and "찾아오시는 길" in title_section_text and "캠퍼스안내" not in title_section_text:
            penalty -= 1.2
        if section_type == "attachment" and _term_hits(_FACILITY_SECTION_TERMS, title_section_text) == 0:
            penalty -= 0.8
        return penalty
    if query_family == "campus_address":
        penalty = 0.0
        if source_type in {"job", "scholarship", "external_notice", "bids", "department", "collabo", "advising"}:
            penalty -= 1.5
        if "찾아오시는 길" in title_section_text and "캠퍼스안내" not in title_section_text:
            penalty -= 1.0
        return penalty
    if query_family == "welfare_facility":
        penalty = 0.0
        if "캠퍼스맵" in title_section_text and "복지문화시설" not in title_section_text:
            penalty -= 1.1
        if source_type in {"job", "scholarship", "external_notice", "bids", "collabo"}:
            penalty -= 1.4
        return penalty
    if query_family == "institution":
        penalty = 0.0
        if "council" in source_type or _term_hits(_INSTITUTION_NOISE_TERMS, title_section_text) > 0:
            penalty -= 1.1
        if section_type == "attachment" and _term_hits(_INSTITUTION_SECTION_TERMS, title_section_text) == 0:
            penalty -= 0.7
        return penalty
    if query_family in _DOMAIN_SECTION_TERMS and source_type in _SERVICE_DOMAIN_NOISE_SOURCES:
        return -0.9
    if query_family == "academic_schedule" and source_type in {"scholarship", "job", "external_notice", "bids"}:
        return -1.4
    if query_family == "academic_schedule" and "학사일정" not in title_section_text and any(term in title_section_text for term in ("수강신청", "계절수업", "장학", "선발", "졸업인증")):
        return -1.6
    if query_family == "course_registration" and any(term in title_section_text for term in ("계절수업", "타대학", "마이크로디그리")):
        if not any(term in full_text for term in ("계절", "타대학", "마이크로디그리")):
            return -0.8
    if query_family == "seasonal_course_registration":
        first_heading = title_section_text.splitlines()[0].strip()
        seasonal_heading = first_heading or title_section_text
        if "계절" not in seasonal_heading:
            return -1.4
        if any(term in seasonal_heading for term in ("타대학", "폐강", "수강정정", "마이크로디그리")):
            return -1.6
    if query_family == "department_curriculum" and any(term in title_section_text for term in ("실습실", "마이크로디그리")) and "이수표" not in title_section_text:
        return -1.2
    if query_family == "specific_scholarship" and "성적우수" not in title_section_text:
        return -2.2
    if query_family == "academic_admin" and source_type == "scholarship":
        return -2.0
    if query_family == "academic_admin" and not any(term in title_section_text for term in ("휴학", "전과", "복학")):
        return -1.3
    if query_family == "graduation":
        penalty = 0.0
        if any(term in title_section_text for term in ("\ud68c\uc758\ub85d", "\ud3c9\uc758\uc6d0\ud68c", "\ucc44\uc6a9", "\uacf5\ubaa8\uc804", "\uc218\uc0c1\uc790")):
            penalty -= 1.6
        if "\uc878\uc5c5" not in full_text and "\ud559\uce59" not in full_text:
            penalty -= 1.4
        if not any(term in title_section_text for term in ("\ud559\uc0ac\uc815\ubcf4", "\ud559\uce59", "\uc878\uc5c5")):
            penalty -= 0.7
        return penalty
    if query_family == "certificate" and not any(term in title_section_text for term in ("제증명서", "증명서")):
        return -1.8
    if query_family == "institution_history" and not any(term in title_section_text for term in ("연혁", "대학현황")):
        return -2.0
    required_terms = _DOMAIN_REQUIRED_TERMS.get(query_family)
    if required_terms and _term_hits(required_terms, full_text) == 0:
        return -1.6
    if required_terms and _term_hits(required_terms, title_section_text) == 0:
        return -1.0
    return 0.0


def _required_heading_match_score(query_family: str, title_section_text: str) -> float:
    required_terms = _DOMAIN_REQUIRED_TERMS.get(query_family)
    if required_terms and _term_hits(required_terms, title_section_text) > 0:
        return 0.8
    return 0.0


def _term_hits(terms: set[str], text: str) -> int:
    return sum(1 for term in terms if term in text)


def _category_match_score(
    doc: RetrievedDoc,
    category: str | None,
    filters: dict[str, list[str]],
) -> float:
    candidates = {
        _normalize_value(doc.category),
        _normalize_value(doc.metadata.get("source_type")),
        _normalize_value(doc.metadata.get("department")),
    }
    candidates.discard("")

    expected_values: list[str] = []
    if category:
        expected_values.append(category)
    for values in filters.values():
        expected_values.extend(values)

    for expected in expected_values:
        normalized = _normalize_value(expected)
        if normalized and any(normalized == candidate or normalized in candidate for candidate in candidates):
            return 0.7
    return 0.0


def _recency_score(value: Any) -> float:
    published_at = _parse_date(value)
    if published_at is None:
        return 0.0

    age_days = max((date.today() - published_at).days, 0)
    return 0.4 * math.exp(-age_days / 365.0)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    raw_value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw_value[:10], fmt).date()
        except ValueError:
            continue
    return None


def _copy_with_rerank_metadata(
    doc: RetrievedDoc,
    rerank_score: float,
    signals: dict[str, float],
) -> RetrievedDoc:
    metadata = {
        **doc.metadata,
        "original_score": doc.score,
        "rerank_score": rerank_score,
        "rerank_signals": signals,
    }
    return doc.model_copy(update={"score": rerank_score, "metadata": metadata})


def _tokenize(text: str) -> list[str]:
    return _dedupe_tokens([*_TOKEN_PATTERN.findall(text.lower()), *tokenize_koreanish(text.lower())])


def _dedupe_tokens(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))


def _normalize_value(value: Any) -> str:
    return str(value or "").strip().lower()
