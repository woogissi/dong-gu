"""Rule-based reranking for retrieved RAG documents."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from rag.preprocess.query_features import (
    SPECIFIC_SCHOLARSHIP_TERMS,
    extract_query_features,
    required_entity_match_score,
    tokenize_koreanish,
    ui_noise_hits,
)
from rag.retrieval.temporal import temporal_rerank_signals
from rag.schemas.retrieved_doc import RetrievedDoc

_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_WEAK_RELEVANCE_TOKENS = {
    "",
    "deu",
    "가능",
    "개수",
    "번호",
    "알려줘",
    "어떻게",
    "오늘",
    "이름",
    "정보",
    "종류",
    "시점",
    "언제",
    "연락처",
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
    # 계절수업을 앞에 배치 (하계/동계 키워드가 있으면 우선 매칭)
    "seasonal_course_registration": {"계절수업", "계절학기", "하계", "동계"},
    # 장학금: "신청" 단독 매칭 방지 → 핵심 용어만 유지
    "장학금": {"장학", "장학금", "학자금"},
    "scholarship": {"장학", "장학금", "국가장학금"},
    "통학버스": {"통학버스", "버스", "노선", "시간표"},
    "도서관": {"도서관", "운영시간", "자료실", "열람실"},
    "학사일정": {"학사일정", "일정", "수강", "보강", "시험"},
    "academic_schedule": {"학사일정", "학사정보", "일정", "보강", "보강일정"},
    "course_registration": {"수강신청", "수강", "정정", "1학기", "학사공지"},
    "department_curriculum": {"컴퓨터공학", "컴퓨터공학과", "이수표", "전공필수", "교육과정"},
    "specific_scholarship": {"성적우수", "성적우수장학금", "성적우수장학생", "장학금"},
    # academic_admin: "신청" 단독 매칭 방지
    "academic_admin": {"휴학", "복학", "전과", "학사지원"},
    "certificate": {"제증명서", "증명서", "재학증명서", "성적증명서", "발급"},
    "institution_history": {"연혁", "연도별 연혁", "대학현황", "1960년대", "2020년대"},
    "welfare_facility": {"복지문화시설", "편의·복지", "학생식당", "헌혈의 집", "편의점", "편의시설"},
    "campus_address": {"가야 캠퍼스", "찾아오시는 길", "캠퍼스안내", "주소"},
    "dormitory": {"기숙사", "생활관", "효민생활관", "입사", "입사신청"},
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
    "dormitory": {"기숙사", "생활관", "효민생활관"},
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
_LIBRARY_JOB_NOISE_TERMS = {"채용", "공고", "기간제", "사서직", "근로자", "운영관리"}
_CAFETERIA_QUERY_TERMS = {"학생식당", "교내식당", "학식", "식당"}
_CAFETERIA_POSITIVE_TERMS = {"학생식당", "교내식당"}
_DORMITORY_FOREIGN_CONTEXT_TERMS = {"외국인", "유학생", "행복기숙사"}
_DORMITORY_FOREIGN_NOTICE_TERMS = {"외국인", "유학생", "수요조사", "행복기숙사"}
_GRADUATION_GENERAL_POSITIVE_TERMS = {"졸업인증제도", "졸업인증", "졸업기준", "졸업요건", "졸업학점", "학사정보", "학칙"}
_GRADUATION_NOTICE_NOISE_TERMS = {"졸업예정자", "졸업논문", "졸업시험 일정", "제출 안내", "학위청구논문심사", "졸업논문심사"}
_DEPARTMENT_CURRICULUM_POSITIVE_TERMS = {"교육과정", "이수표", "이수학점", "졸업기준", "졸업학점", "전공필수", "교양필수"}
_DEPARTMENT_CURRICULUM_NOISE_TERMS = {"진로", "약사", "취업 현황", "취업현황", "학위청구논문심사", "졸업논문심사", "졸업논문"}


def rerank_documents(
    docs: list[RetrievedDoc],
    *,
    query: str,
    keywords: list[str] | None = None,
    category: str | None = None,
    filters: dict[str, list[str]] | None = None,
    ranking_hints: dict[str, Any] | None = None,
) -> list[RetrievedDoc]:
    """Return documents ordered by retrieval score plus lightweight relevance signals."""
    if not docs:
        return []

    keywords = keywords or []
    filters = filters or {}
    ranking_hints = ranking_hints or {}
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
            ranking_hints=ranking_hints,
            max_base_score=max_base_score,
        )
        rerank_score = round(
            sum(
                value
                for key, value in signals.items()
                if key not in {"noise_score", "temporal_match", "temporal_mismatch", "temporal_recency"}
            ),
            6,
        )
        reranked_doc = _copy_with_rerank_metadata(doc, rerank_score, signals)
        reranked.append((rerank_score, index, reranked_doc))

    reranked.sort(key=lambda item: (-item[0], item[1]))
    return _dedup_by_content_hash(reranked)


def _dedup_by_content_hash(
    reranked: list[tuple[float, int, RetrievedDoc]],
) -> list[RetrievedDoc]:
    """동일 content_hash를 가진 chunk는 최고 rank 1개만 남긴다.

    content_hash가 없거나 빈 chunk는 dedup 대상에서 제외한다.
    이미 rerank score 기준으로 정렬된 상태에서 호출되므로
    먼저 등장한 것이 곧 최고 rank다.
    """
    seen_hashes: set[str] = set()
    result: list[RetrievedDoc] = []
    for _, _, doc in reranked:
        content_hash = str(doc.metadata.get("content_hash") or "").strip()
        if content_hash and content_hash in seen_hashes:
            continue
        if content_hash:
            seen_hashes.add(content_hash)
        result.append(doc)
    return result


def _score_doc(
    *,
    doc: RetrievedDoc,
    query: str,
    query_tokens: list[str],
    keyword_tokens: list[str],
    query_features: dict[str, Any],
    category: str | None,
    filters: dict[str, list[str]],
    ranking_hints: dict[str, Any],
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
        query_family=query_family,
    )
    exif_noise = _exif_noise_penalty(content)
    ui_static_noise = _ui_static_noise_penalty(doc, full_text)
    source_type_noise = _source_type_noise_penalty(doc, keyword_tokens, title_section_text, full_text)
    query_family_boost = _query_family_boost(
        doc=doc,
        query_text=query.lower(),
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
    content_required_match = _content_required_match_score(required_terms, content.lower())
    faculty_entity_match = _faculty_entity_match_score(faculty_entity, full_text)
    faculty_entity_penalty = _faculty_entity_penalty(
        faculty_entity=faculty_entity,
        doc=doc,
        query=query,
        title_section_text=title_section_text,
        full_text=full_text,
    )
    dept_entity = str(ranking_hints.get("department_entity") or "").strip().lower()
    department_entity_match = _department_entity_match_score(dept_entity, full_text, query_family)
    department_board_noise = _department_board_noise_penalty(
        doc=doc,
        query_family=query_family,
        query_text=query.lower(),
    )
    query_family_penalty = _query_family_penalty(
        doc=doc,
        query_text=query.lower(),
        query_family=query_family,
        title_section_text=title_section_text,
        full_text=full_text,
    )
    if required_terms and required_entity_match == 0.0:
        query_family_penalty -= 1.2
    category_match = _category_match_score(doc, category, filters, ranking_hints)
    recency = _recency_score(doc.metadata.get("published_at"))
    temporal_signals = ranking_hints.get("temporal_signals") if isinstance(ranking_hints, dict) else {}
    if not isinstance(temporal_signals, dict):
        temporal_signals = {}
    temporal = temporal_rerank_signals(doc, temporal_signals)
    noise_score = abs(
        min(attachment_noise, 0.0)
        + min(exif_noise, 0.0)
        + min(ui_static_noise, 0.0)
        + min(source_type_noise, 0.0)
        + min(faculty_entity_penalty, 0.0)
        + min(query_family_penalty, 0.0)
        + min(department_entity_match, 0.0)
        + min(department_board_noise, 0.0)
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
        "content_required_match": round(content_required_match, 6),
        "faculty_entity_match": round(faculty_entity_match, 6),
        "faculty_entity_penalty": round(faculty_entity_penalty, 6),
        "department_entity_match": round(department_entity_match, 6),
        "department_board_noise": round(department_board_noise, 6),
        "query_family_penalty": round(query_family_penalty, 6),
        "category_match": round(category_match, 6),
        "recency": round(recency, 6),
        "temporal_score": round(temporal.get("temporal_score", 0.0), 6),
        "temporal_match": round(temporal.get("temporal_match", 0.0), 6),
        "temporal_mismatch": round(temporal.get("temporal_mismatch", 0.0), 6),
        "temporal_recency": round(temporal.get("temporal_recency", 0.0), 6),
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


_DEPARTMENT_ENTITY_MATCH_FAMILIES = {
    "department_curriculum",
    "graduation",
    "faculty",
}


_DEPARTMENT_ENTITY_SUFFIX_RE = re.compile(r"(?:학과|학부|전공)$")


def _department_entity_match_score(dept_entity: str, full_text: str, query_family: str) -> float:
    """학과명 개체(department_entity)가 문서 본문에 포함되는지에 따라 boost/penalty를 반환한다.

    department_curriculum·graduation·faculty 패밀리에서만 활성화된다.
    - 학과명 일치: +1.5 (해당 학과 문서를 상위로)
    - 학과명 불일치: -1.0 (타 학과 문서를 하위로)

    질의 학과명과 문서 제목의 접미사가 달라도(예: '응용소프트웨어공학과' vs
    '응용소프트웨어공학전공') 같은 학과로 인정하기 위해 stem(접미사 제거) 매칭을 폴백으로 둔다.
    """
    if not dept_entity or query_family not in _DEPARTMENT_ENTITY_MATCH_FAMILIES:
        return 0.0
    # 경계 매칭: '경영'이 '창업투자경영학과'에 substring으로 매칭되어 타 학과 이수표까지
    # +1.5를 받던 문제(G049)를 막는다. 학과명 앞 글자가 한글이면 더 긴 합성 학과명의
    # 일부이므로 일치로 보지 않는다.
    if _dept_token_in_text(dept_entity, full_text):
        return 1.5
    # stem 폴백은 '응용소프트웨어공학'(9자)처럼 충분히 변별적인 긴 학과명에만 적용한다.
    # '심리'(2자)·'간호'(2자)처럼 짧은 stem은 타 학과 본문에 흔히 등장해 오매칭하므로 제외.
    stem = _DEPARTMENT_ENTITY_SUFFIX_RE.sub("", dept_entity)
    if len(stem) >= 4 and stem != dept_entity and _dept_token_in_text(stem, full_text):
        return 1.5
    return -1.0


def _dept_token_in_text(token: str, text: str) -> bool:
    """token이 text에 '경계 단위'로 등장하는지 판정.

    앞 글자가 한글(가~힣)이면 더 긴 합성 학과명의 일부로 보아 불일치 처리한다.
    예: '경영'은 '경영학과'에는 매칭되지만 '창업투자경영학과'에는 매칭되지 않는다.
    """
    if not token:
        return False
    start = text.find(token)
    while start != -1:
        prev = text[start - 1] if start > 0 else ""
        if not ("가" <= prev <= "힣"):
            return True
        start = text.find(token, start + 1)
    return False


# 학과 게시판 복제 공지 페널티에서 면제할 패밀리.
# 학과 교육과정/졸업 쿼리는 학과 게시판 글이 정답일 수 있으므로 제외한다.
_DEPARTMENT_BOARD_NOISE_EXEMPT_FAMILIES = {
    "department_curriculum",
    "graduation",
}

# 교육과정/졸업 질의에서 게시판 공지를 면제할 때, 그 공지가 실제로 교육과정 관련
# 내용을 담고 있는지 판단하는 용어 집합. 'AX마이크로디그리' 같은 무관 홍보 공지는
# 이 용어가 없어 면제되지 않고 페널티 대상이 된다(G060).
_CURRICULUM_NOTICE_EXEMPT_TERMS = {
    "교육과정", "이수표", "이수체계", "이수학점", "전공필수", "전공선택",
    "교양필수", "졸업학점", "졸업기준", "졸업요건", "커리큘럼", "편성표",
}


_SUBPAGE_BOARD_URL_PATTERN = re.compile(r"/sub\d+(?:_\d+)*\.do\?")


def _is_department_board_notice(doc: RetrievedDoc) -> bool:
    """학과·부서 서브페이지 게시판의 개별 공지(여러 게시판에 복제된 글)인지 판정한다.

    식별 기준: URL이 서브페이지 게시판 패턴(`/subN_NN.do?`)이면서 게시판 글
    식별자(articleNo)를 포함하는 경우. 학과/부서 서브도메인뿐 아니라
    advising·freemajor·counsel 등 본청 산하 게시판도 포함한다.

    제외 대상:
    - 이수표·학과소개 같은 정적 안내 페이지(articleNo 없는 깔끔한 sub URL)
    - 본청 공지(gra-notice.do·deu-scholarship.do·deu-notice.do 등) — sub 패턴이 아니며
      정답 공지인 경우가 많아 페널티 대상에서 자연히 빠진다.
    """
    source = _normalize_value(doc.source)
    if "articleno=" not in source:
        return False
    return bool(_SUBPAGE_BOARD_URL_PATTERN.search(source))


def _department_board_noise_penalty(
    *,
    doc: RetrievedDoc,
    query_family: str,
    query_text: str,
) -> float:
    """비학과 정보 쿼리에서 학과 게시판 복제 공지를 억제한다.

    동일 공지가 모든 학과 게시판(sub06_03.do 등)에 복제 게시되어
    상담센터·도서관 등 공식 안내 페이지를 밀어내는 문제를 방지한다.
    쿼리에 학과명이 명시되면(해당 학과 글이 정답일 수 있으므로) 적용하지 않는다.
    """
    if not _is_department_board_notice(doc):
        return 0.0
    if query_family in _DEPARTMENT_BOARD_NOISE_EXEMPT_FAMILIES:
        # (1) 사용자가 공지/공고를 명시적으로 찾으면 게시판 글이 정답이므로 면제.
        if any(term in query_text for term in ("공지", "공고", "게시판")):
            return 0.0
        # (2) 교육과정/졸업 질의: 게시판 글이라도 교육과정 관련 내용이면 정답 가능성 → 면제.
        #     무관 홍보 공지(예: 'AX마이크로디그리')는 정답 정적 교육과정 페이지를
        #     밀어내므로 페널티를 적용한다(G060).
        notice_text = f"{doc.title or ''}\n{doc.content or ''}".lower()
        if _term_hits(_CURRICULUM_NOTICE_EXEMPT_TERMS, notice_text) > 0:
            return 0.0
        return -2.0
    if _has_department_anchor(query_text):
        return 0.0
    return -2.5


def _content_required_match_score(required_terms: list[str], content_text: str) -> float:
    """쿼리 required_terms가 청크 본문(content)에 직접 매칭되는 비율 기반 boost.

    required_entity_match는 제목 포함 full_text 기반이라 같은 문서의 여러 청크(제목 동일)를
    구별하지 못한다. 이 신호는 content 전용 매칭으로, 정답 정보가 실제 담긴 청크
    (예: 학사일정 문서에서 '보강'이 든 6월 청크)를 같은 문서의 다른 청크보다 상위로 끌어올린다.
    """
    if not required_terms or not content_text:
        return 0.0
    matched = sum(1 for term in required_terms if term and term in content_text)
    return (matched / len(required_terms)) * 1.2


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
    return 0.0 if any(token in full_text for token in strong_tokens) else -0.8


_ATTACHMENT_PENALTY_EXEMPT_FAMILIES = {
    "department_curriculum",  # 교육과정/이수표는 첨부파일이 원본 소스
    "graduation",             # 졸업학점 기준도 첨부파일에 존재
}


def _attachment_noise_penalty(
    doc: RetrievedDoc,
    strong_term_match: float,
    title_match: float,
    section_title_match: float,
    query_tokens: list[str],
    query_family: str = "",
) -> float:
    section_type = _normalize_value(doc.metadata.get("section_type"))
    if section_type != "attachment":
        return 0.0
    if query_family in _ATTACHMENT_PENALTY_EXEMPT_FAMILIES:
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
    if 0 < content_length < 50:
        # 극단적으로 짧은 chunk: 메뉴·헤더·스텁 거의 확실
        penalty -= 1.5
    elif 0 < content_length < 80:
        penalty -= 0.9
    elif 0 < content_length < 120:
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
    if feature_family == "club_program":
        return "club_activity"
    return feature_family


_GRADE_QUERY_PATTERN = re.compile(r"([1-4])\s*학년")


def _grade_section_match(query_text: str, full_text: str) -> float:
    """질문에 학년(N학년)이 있고 문서 본문에 해당 학년이 있으면 소폭 가점.

    이수표가 학년별 청크로 분할된 경우 해당 학년 섹션을 우선시키기 위함.
    전체 학년을 담은 단일 청크는 항상 포함하므로 무해하다.
    """
    grades = set(_GRADE_QUERY_PATTERN.findall(query_text or ""))
    if not grades:
        return 0.0
    return 0.4 if any(f"{g}학년" in full_text for g in grades) else 0.0


def _query_family_boost(
    *,
    doc: RetrievedDoc,
    query_text: str,
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
        if _is_cafeteria_query(query_text):
            title_bonus = 2.2 if _term_hits(_CAFETERIA_POSITIVE_TERMS, title_section_text) else 0.0
            source_boost = 1.3 if source_type == "welfare" else 0.0
            body_hits = _term_hits(_CAFETERIA_POSITIVE_TERMS | {"운영시간"}, f"{title_section_text}\n{full_text}")
            return min(title_bonus + source_boost + body_hits * 0.35, 3.2)
        title_bonus = 1.8 if "복지문화시설" in title_section_text else 0.0
        facility_hits = _term_hits(_DOMAIN_SECTION_TERMS["welfare_facility"], f"{title_section_text}\n{full_text}")
        return min(title_bonus + facility_hits * 0.35, 2.4)
    if query_family == "library":
        title_bonus = 1.4 if any(term in title_section_text for term in ("도서관소개", "도서관")) else 0.0
        source_boost = 1.4 if source_type == "library" else 0.0
        return min(title_bonus + source_boost, 2.6)
    if query_family == "dormitory":
        has_application_intent = _has_dormitory_application_intent(query_text)
        title_bonus = 1.8 if any(term in title_section_text for term in ("기숙사", "생활관", "효민생활관", "입사신청")) else 0.0
        source_boost = 0.4 if has_application_intent and _is_dormitory_homepage_like(doc, title_section_text, full_text) else 1.2 if source_type == "dormitory" else 0.0
        body_hits = _term_hits(_DOMAIN_SECTION_TERMS["dormitory"], full_text)
        method_bonus = 2.4 if any(term in full_text for term in ("입사신청 방법안내", "입사 신청", "신청기간", "신청 기간")) else 0.0
        notice_bonus = 1.8 if has_application_intent and _has_dormitory_application_notice(title_section_text, full_text) else 0.0
        return min(title_bonus + source_boost + body_hits * 0.18 + method_bonus + notice_bonus, 6.2)
    if query_family == "club_activity":
        general_club_query = _is_general_club_query(query_text)
        title_hits = _term_hits({"동아리", "중앙동아리", "학생동아리", "총동아리", "학생활동", "club"}, title_section_text)
        body_hits = _term_hits({"동아리", "중앙동아리", "학생동아리", "총동아리", "학생활동", "club"}, full_text)
        source_boost = 0.6 if source_type in {"club_activity", "student_life", "institution"} else 0.0
        central_bonus = 1.8 if general_club_query and any(term in full_text for term in ("중앙동아리", "동아리 종류", "동아리 가입", "동아리 신청", "학생동아리", "총동아리", "학생활동")) else 0.0
        return min(title_hits * 0.7 + body_hits * 0.2 + source_boost + central_bonus, 3.4)
    if query_family == "facility":
        # 위치 보충검색이 의도(건물→캠퍼스맵 / 학과사무실 / 교수소개)에 맞게 고른 canonical
        # 문서를 최우선. 건물명이 타 학과사무실 페이지에 소재지로 등장해 밀리는 문제를 해소.
        if _normalize_value(doc.metadata.get("search_mode")) == "location_supplement":
            return 3.0
        section_hits = _term_hits(_FACILITY_SECTION_TERMS, title_section_text)
        source_boost = 0.5 if any(term in source_type for term in ("campus", "facility", "institution")) else 0.0
        title_bonus = 0.0
        if any(term in title_section_text for term in ("캠퍼스맵", "찾아오시는 길", "가야 캠퍼스", "복지문화시설")):
            title_bonus = 1.1
        return min(section_hits * 0.65 + source_boost + title_bonus, 2.4)
    if query_family == "institution":
        section_hits = _term_hits(_INSTITUTION_SECTION_TERMS, title_section_text)
        source_boost = 0.7 if any(term in source_type for term in _INSTITUTION_SOURCE_TERMS) else 0.0
        president_bonus = 1.6 if any(term in title_section_text for term in ("역대총장", "총장", "former president", "president")) else 0.0
        return min(section_hits * 0.65 + source_boost + president_bonus, 2.8)
    if query_family == "faculty":
        # 교수소개 보충검색이 고른 해당 학과 교수소개 페이지를 최우선.
        if _normalize_value(doc.metadata.get("search_mode")) == "faculty_supplement":
            return 3.0
        title_bonus = 1.8 if any(term in title_section_text for term in ("교수소개", "교수진", "전임교수", "교수 소개")) else 0.0
        source_boost = 0.6 if source_type in {"department", "institution"} else 0.0
        return min(title_bonus + source_boost, 2.8)
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
        # 쿼리에 등장한 특정 장학금명이 문서 제목에 있으면 높은 boost
        query_specific_terms = [t for t in SPECIFIC_SCHOLARSHIP_TERMS if t in query_text]
        if query_specific_terms and any(term in title_section_text for term in query_specific_terms):
            return 3.0
        if any(term in title_section_text for term in ("성적우수장학금", "성적우수장학생", "성적우수")):
            return 2.4
        return 0.0
    if query_family == "academic_admin":
        title_bonus = 1.8 if any(term in title_section_text for term in ("휴학", "전과", "복학")) else 0.0
        first_heading = title_section_text.splitlines()[0].strip()
        if first_heading in {"휴학", "전과", "복학"}:
            title_bonus += 2.2
        return min(title_bonus + _term_hits(_DOMAIN_SECTION_TERMS["academic_admin"], full_text) * 0.12, 4.0)
    if query_family == "department_curriculum":
        positive_text = f"{title_section_text}\n{full_text}"
        title_hits = _term_hits(_DEPARTMENT_CURRICULUM_POSITIVE_TERMS, title_section_text)
        body_hits = _term_hits(_DEPARTMENT_CURRICULUM_POSITIVE_TERMS, positive_text)
        credit_bonus = 1.4 if _is_department_graduation_credit_query(query_text) and body_hits > 0 else 0.0
        source_boost = 0.4 if source_type == "department" else 0.0
        # 질문 학년이 본문에 있으면 해당 학년 섹션 소폭 우선
        grade_bonus = _grade_section_match(query_text, full_text)
        return min(title_hits * 0.75 + body_hits * 0.3 + credit_bonus + source_boost + grade_bonus, 4.6)
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
        if _term_hits(_GRADUATION_GENERAL_POSITIVE_TERMS, title_section_text) > 0:
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
        source_boost = 0.8 if source_type in {"academic_support", "academic", "institution"} else 0.3 if source_type == "academic_notice" else 0.0
        return min(title_bonus + body_hits * 0.25 + source_boost, 5.0)
    if query_family == "certificate":
        return 2.2 if any(term in title_section_text for term in ("제증명서", "증명서 발급", "재학증명서", "성적증명서")) else 0.0
    if query_family == "career":
        # 취업지원센터(advising)·공식 취업/진로 안내 페이지 우선
        source_boost = 2.0 if source_type in {"advising", "job"} else 0.0
        title_bonus = 1.4 if any(
            term in title_section_text
            for term in ("취업지원", "진로/취업", "취업/진로", "일자리플러스", "취업센터", "플러스센터", "대학일자리")
        ) else 0.0
        body_hits = _term_hits({"취업지원", "취업프로그램", "진로프로그램", "취업/진로", "취업지원센터"}, full_text)
        return min(source_boost + title_bonus + body_hits * 0.2, 3.6)
    if query_family == "institution_history":
        title_bonus = 2.2 if any(term in title_section_text for term in ("연도별 연혁", "대학현황", "1960년대", "1970년대", "1980년대", "1990년대", "2000년대", "2010년대", "2020년대")) else 0.0
        return min(title_bonus + _term_hits(_DOMAIN_SECTION_TERMS["institution_history"], full_text) * 0.1, 2.6)
    domain_terms = _DOMAIN_SECTION_TERMS.get(query_family)
    if domain_terms:
        heading_hits = _term_hits(domain_terms, title_section_text)
        body_hits = _term_hits(domain_terms, full_text)
        return min(heading_hits * 0.45 + body_hits * 0.15, 1.2)
    return 0.0


_CANONICAL_PRIORITY_FAMILIES = {
    "academic_schedule",
    "course_registration",
    "seasonal_course_registration",
    "scholarship",
    "specific_scholarship",
    "dormitory",
    "certificate",
    "career",
}

_CANONICAL_AUTHORITY_SOURCES = {
    "institution",
    "academic_notice",
    "academic",
    "campus",
    "scholarship",
    "advising",
    "dormitory",
    "notice",
}


def _canonical_source_priority(*, doc: RetrievedDoc, query_family: str, title_section_text: str) -> float:
    if query_family not in _CANONICAL_PRIORITY_FAMILIES:
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
    if source_type in _CANONICAL_AUTHORITY_SOURCES:
        central_bonus += 0.35
    if any(term in title for term in ("학사공지", "학사지원", "학사일정", "수강신청")):
        central_bonus += 0.35

    # 장학금 계열: 공식 장학 페이지 우선
    if query_family in {"scholarship", "specific_scholarship"}:
        if source_type == "scholarship":
            central_bonus += 0.8
        if any(term in title for term in ("장학금", "국가장학금", "장학생")):
            central_bonus += 0.3

    # 기숙사/생활관 공식 출처 우선
    if query_family == "dormitory" and source_type == "dormitory":
        central_bonus += 0.8

    # 증명서 공식 출처 우선
    if query_family == "certificate" and source_type in {"institution", "academic_notice"}:
        central_bonus += 0.6

    duplicate_penalty = 0.0
    if source_type == "department" or re.search(r"/[a-z0-9_-]+/sub0[67]_", source):
        duplicate_penalty -= 0.7
    if source_type == "department" and any(term in title for term in ("수강신청 안내", "보강일정", "학사일정")):
        duplicate_penalty -= 0.3
    # 장학금 쿼리에서 학과 복사본 페널티 강화
    if query_family in {"scholarship", "specific_scholarship"} and source_type == "department":
        duplicate_penalty -= 0.5

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
        "faculty": ("교수소개", "교수진"),
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
    query_text: str,
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
        # H4: 순수 건물 위치 질의(학과/교수 anchor 없음)에서 학과사무실·연락처·교수소개 페이지는
        # 건물명이 '사무실 소재지'로 등장할 뿐 정답이 아니므로 감점 (건물명→학과사무실 혼동 차단).
        # 학과/교수 anchor가 있으면(예: '컴퓨터공학과 학과사무실 위치') 면제.
        if not _has_department_anchor(query_text):
            if source_type == "department" and any(
                term in title_section_text for term in ("학과사무실", "연락처", "교수소개", "교수진")
            ):
                penalty -= 3.0
            if source_type in {"notice", "academic_notice"}:
                penalty -= 1.5
        # H4: 교수/연구실 의도면 학과사무실(행정) 페이지보다 교수소개 페이지를 우선
        if any(term in query_text for term in ("교수", "연구실", "교수실")) and (
            "학과사무실" in title_section_text and "교수" not in title_section_text
        ):
            penalty -= 2.0
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
        if _is_cafeteria_query(query_text):
            if source_type == "dormitory" or "효민생활관" in title_section_text:
                penalty -= 3.0
            if not any(term in f"{title_section_text}\n{full_text}" for term in ("학생식당", "교내식당", "식당")):
                penalty -= 0.8
        if "캠퍼스맵" in title_section_text and "복지문화시설" not in title_section_text:
            penalty -= 1.1
        if source_type in {"job", "scholarship", "external_notice", "bids", "collabo"}:
            penalty -= 1.4
        return penalty
    if query_family == "library":
        penalty = 0.0
        if source_type == "department" and _term_hits(_LIBRARY_JOB_NOISE_TERMS, f"{title_section_text}\n{full_text}") > 0:
            penalty -= 4.0
        if source_type in {"job", "external_notice", "bids"}:
            penalty -= 2.0
        return penalty
    if query_family == "institution":
        penalty = 0.0
        if "council" in source_type or _term_hits(_INSTITUTION_NOISE_TERMS, title_section_text) > 0:
            penalty -= 1.1
        if any(term in title_section_text for term in ("총장메시지", "총장 메시지", "president message")):
            penalty -= 1.8
        if source_type in {"lifelong", "notice", "external_notice"} and not any(term in title_section_text for term in ("역대총장", "총장")):
            penalty -= 1.4
        if section_type == "attachment" and _term_hits(_INSTITUTION_SECTION_TERMS, title_section_text) == 0:
            penalty -= 0.7
        return penalty
    if query_family in _DOMAIN_SECTION_TERMS and source_type in _SERVICE_DOMAIN_NOISE_SOURCES:
        return -0.9
    if query_family == "academic_schedule" and source_type in {"scholarship", "job", "external_notice", "bids"}:
        return -1.4
    if query_family == "dormitory" and source_type in {"scholarship", "job", "external_notice", "bids", "department"}:
        return -1.6
    if (
        query_family == "dormitory"
        and source_type == "exchange"
        and _is_foreign_dormitory_notice(title_section_text, full_text)
        and not _is_foreign_dormitory_query(query_text)
    ):
        return -4.0
    # exchange 출처 문서는 외국인 기숙사 문맥이 없어도 일반 기숙사 쿼리에서 페널티.
    # 국제교류처 공지가 "기숙사" 키워드 매칭으로 rank1을 차지하는 문제 방지.
    if (
        query_family == "dormitory"
        and source_type == "exchange"
        and not _is_foreign_dormitory_query(query_text)
    ):
        return -2.4
    if query_family == "dormitory" and _has_dormitory_application_intent(query_text) and _is_dormitory_homepage_like(doc, title_section_text, full_text):
        return -1.2
    if query_family == "club_activity":
        penalty = 0.0
        general_club_query = _is_general_club_query(query_text)
        career_club_doc = any(term in full_text for term in ("학과 진로동아리", "학과진로동아리", "취업동아리", "진로동아리", "취업 동아리", "전공동아리"))
        if general_club_query and career_club_doc and not any(term in query_text for term in ("진로", "취업", "학과", "전공")):
            penalty -= 2.0
        if source_type in {"job", "department"} and general_club_query:
            penalty -= 0.8
        if "동아리" not in full_text and "club" not in full_text:
            penalty -= 1.2
        return penalty
    if query_family == "career":
        # 위치/시설 질문에서 채용공고 문서는 무관
        if source_type == "job" and any(term in query_text for term in ("위치", "어디", "어디에", "장소", "찾아")):
            return -4.0
        # 채용공고/모집공고 제목은 취업지원센터 안내와 무관
        if source_type == "job" and any(term in title_section_text for term in ("채용공고", "모집공고", "채용", "연구원", "직원")):
            if not any(term in query_text for term in ("채용", "공고", "모집", "취업정보")):
                return -3.0
        # 학과 공지 게시판은 일반 취업지원 프로그램 안내 쿼리에서 노이즈
        # (학과명이 쿼리에 없으면 특정 학과 공지가 아닌 중앙 취업지원 페이지가 우선)
        is_general_career_query = not any(
            term in query_text for term in ("학과", "전공", "학부", "대학원", "채용", "공고", "취업정보")
        )
        if source_type == "department" and is_general_career_query:
            return -2.0
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
        # 타대학 관련 문서는 본교 계절수업 신청 질문과 무관 → 강한 페널티
        if "타대학" in seasonal_heading or (
            "타대학" in title_section_text and "타대학" in full_text[:300]
        ):
            return -8.0
        if any(term in seasonal_heading for term in ("폐강", "수강정정", "마이크로디그리")):
            return -4.0
    if query_family == "faculty":
        penalty = 0.0
        # 이수표/편성표/교육과정/실습실 등은 교수소개가 아님 → 교수 질의에서 하향.
        if any(term in title_section_text for term in ("이수표", "편성표", "교육과정", "이수체계")):
            penalty -= 2.5
        if any(term in title_section_text for term in ("실습실", "실험실", "강의실")):
            penalty -= 2.0
        # 교수 인물·소개 맥락이 전혀 없는 전공소개/학과소개 정적 페이지 하향.
        if any(term in title_section_text for term in ("전공소개", "학과소개", "교육목표", "교육과정")) and not any(
            term in title_section_text for term in ("교수소개", "교수진", "교수")
        ):
            penalty -= 1.5
        # 무관한 공지/뉴스(예: 타학과 교수 표창 기사)는 교수소개 질의에서 노이즈.
        if source_type in {"notice", "academic_notice", "external_notice"} and not any(
            term in title_section_text for term in ("교수소개", "교수진")
        ):
            penalty -= 1.5
        return penalty
    if query_family == "department_curriculum":
        penalty = 0.0
        page_kind = _normalize_value(doc.metadata.get("page_kind"))
        positive_hits_all = _term_hits(_DEPARTMENT_CURRICULUM_POSITIVE_TERMS, f"{title_section_text}\n{full_text}")
        if any(term in title_section_text for term in ("실습실", "마이크로디그리")) and "이수표" not in title_section_text:
            penalty -= 1.2
        # advising(다전공 워크시트 등)·게시판 공지는 이수표가 아님 → 모든 이수표 질의에서 감점
        if source_type == "advising":
            penalty -= 2.5
        elif page_kind == "board_detail" and positive_hits_all == 0:
            penalty -= 1.6
        # 교육과정/이수표 용어가 전혀 없는 학과 안내(전공소개 등)는 이수표 질의에서 하향
        elif positive_hits_all == 0 and "이수표" not in title_section_text:
            penalty -= 1.0
        if _is_department_graduation_credit_query(query_text):
            positive_hits = positive_hits_all
            if positive_hits == 0:
                penalty -= 2.0
            if _term_hits(_DEPARTMENT_CURRICULUM_NOISE_TERMS, title_section_text) > 0:
                penalty -= 2.4
            elif _term_hits(_DEPARTMENT_CURRICULUM_NOISE_TERMS, full_text) > 0 and positive_hits <= 1:
                penalty -= 1.2
        # 쿼리에 명시된 학과와 다른 학과 문서 페널티 (학과 불일치)
        dept_mismatch = _department_mismatch_penalty(query_text, title_section_text, full_text)
        penalty += dept_mismatch
        return penalty
    if query_family == "specific_scholarship" and "성적우수" not in title_section_text:
        return -2.2
    if query_family == "academic_admin" and source_type == "scholarship":
        return -2.0
    if query_family == "academic_admin" and not any(term in title_section_text for term in ("휴학", "전과", "복학")):
        return -1.3
    if query_family == "graduation":
        penalty = 0.0
        general_graduation_query = not _has_department_anchor(query_text)
        if any(term in title_section_text for term in ("\ud68c\uc758\ub85d", "\ud3c9\uc758\uc6d0\ud68c", "\ucc44\uc6a9", "\uacf5\ubaa8\uc804", "\uc218\uc0c1\uc790")):
            penalty -= 1.6
        if general_graduation_query and source_type == "department":
            penalty -= 1.4
        if general_graduation_query and _has_department_anchor(title_section_text):
            penalty -= 1.0
        if general_graduation_query and _is_specific_department_graduation_notice(title_section_text):
            penalty -= 2.6
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


def _has_dormitory_application_intent(query_text: str) -> bool:
    text = query_text.lower()
    return any(term in text for term in ("신청", "날짜", "기간", "모집", "입사신청", "입사 신청", "언제", "deadline", "apply"))


def _is_cafeteria_query(query_text: str) -> bool:
    return any(term in query_text for term in _CAFETERIA_QUERY_TERMS)


def _is_foreign_dormitory_query(query_text: str) -> bool:
    return any(term in query_text for term in _DORMITORY_FOREIGN_CONTEXT_TERMS)


def _is_foreign_dormitory_notice(title_section_text: str, full_text: str) -> bool:
    text = f"{title_section_text}\n{full_text}"
    return _term_hits(_DORMITORY_FOREIGN_NOTICE_TERMS, text) > 0


def _is_department_graduation_credit_query(query_text: str) -> bool:
    text = query_text or ""
    return "졸업" in text and any(term in text for term in ("학점", "이수학점", "졸업학점", "졸업기준"))


def _has_department_anchor(text: str) -> bool:
    return bool(re.search(r"[가-힣A-Za-z0-9]+(?:학과|전공|학부)", text or ""))


def _is_specific_department_graduation_notice(title_section_text: str) -> bool:
    if _term_hits(_GRADUATION_NOTICE_NOISE_TERMS, title_section_text) > 0:
        return True
    return bool(_has_department_anchor(title_section_text) and any(term in title_section_text for term in ("공지", "안내", "제출", "심사", "일정")))


def _has_dormitory_application_notice(title_section_text: str, full_text: str) -> bool:
    text = f"{title_section_text}\n{full_text}".lower()
    return any(term in text for term in ("모집", "신청기간", "신청 기간", "입사신청", "입사 신청", "입사생", "생활관생", "모집 안내", "통합모집"))


def _is_dormitory_homepage_like(doc: RetrievedDoc, title_section_text: str, full_text: str) -> bool:
    source = _normalize_value(doc.source)
    source_type = _normalize_value(doc.metadata.get("source_type"))
    section_type = _normalize_value(doc.metadata.get("section_type"))
    text = f"{title_section_text}\n{full_text}".lower()
    if _has_dormitory_application_notice(title_section_text, full_text):
        return False
    homepage_markers = ("index.do", "main.do", "/main", "intro", "생활관 소개", "효민생활관", "생활관안내")
    return (
        source_type == "dormitory"
        and (section_type in {"body", "static", "menu", ""} or any(marker in source for marker in homepage_markers))
        and any(marker in text or marker in source for marker in homepage_markers)
    )


def _is_general_club_query(query_text: str) -> bool:
    text = query_text.lower()
    return "동아리" in text and not any(term in text for term in ("진로", "취업", "학과", "전공"))


def _term_hits(terms: set[str], text: str) -> int:
    return sum(1 for term in terms if term in text)


def _category_match_score(
    doc: RetrievedDoc,
    category: str | None,
    filters: dict[str, list[str]],
    ranking_hints: dict[str, Any] | None = None,
) -> float:
    candidates = {
        _normalize_value(doc.metadata.get("source_type")),
    }
    candidates.discard("")

    expected_values: list[str] = []
    if category:
        expected_values.append(category)
    for values in filters.values():
        expected_values.extend(values)
    hints = ranking_hints or {}
    for key in ("category", "category_values", "document_category", "source_boosts"):
        value = hints.get(key)
        if isinstance(value, (list, tuple, set)):
            expected_values.extend(str(item) for item in value if item is not None)
        elif value:
            expected_values.append(str(value))

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


# 학과명 키워드 목록 - 쿼리에서 특정 학과를 요청할 때 다른 학과 문서 억제
_KNOWN_DEPT_NAMES: list[str] = [
    "컴퓨터공학과", "컴퓨터공학", "컴공",
    "전자공학과", "전자공학",
    "게임공학과", "게임공학",
    "인공지능학과", "인공지능학", "인공지능",
    "소프트웨어학과", "소프트웨어",
    "간호학과", "간호학", "간호",
    "경찰행정학과", "경찰행정",
    "경영학과", "경영학", "경영",
    "시각디자인과", "시각디자인",
    "물리치료학과", "물리치료",
    "작업치료학과", "작업치료",
    "의용공학과", "의용공학",
    "건축학과", "건축",
    "화학공학과", "화학공학",
    "기계공학과", "기계공학",
    "토목공학과", "토목공학",
    "관광경영학과", "관광경영",
    "영어영문학과", "영어영문",
    "법학과",
    "사회복지학과", "사회복지",
]


def _department_mismatch_penalty(query_text: str, title_section_text: str, full_text: str) -> float:
    """쿼리에 특정 학과가 명시됐는데 문서가 다른 학과인 경우 페널티."""
    query_dept = None
    for dept in _KNOWN_DEPT_NAMES:
        if dept in query_text:
            query_dept = dept
            break
    if not query_dept:
        return 0.0
    # 쿼리 학과가 문서에 없으면 다른 학과 문서일 가능성
    if query_dept not in title_section_text and query_dept not in full_text[:400]:
        # 다른 알려진 학과명이 제목에 있으면 강한 페널티
        for dept in _KNOWN_DEPT_NAMES:
            if dept != query_dept and dept in title_section_text:
                return -3.5
    return 0.0


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
        "temporal_rerank_signals": {
            "temporal_score": signals.get("temporal_score", 0.0),
            "temporal_match": signals.get("temporal_match", 0.0),
            "temporal_mismatch": signals.get("temporal_mismatch", 0.0),
            "temporal_recency": signals.get("temporal_recency", 0.0),
        },
    }
    return doc.model_copy(update={"score": rerank_score, "metadata": metadata})


def _tokenize(text: str) -> list[str]:
    return _dedupe_tokens([*_TOKEN_PATTERN.findall(text.lower()), *tokenize_koreanish(text.lower())])


def _dedupe_tokens(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))


def _normalize_value(value: Any) -> str:
    return str(value or "").strip().lower()
