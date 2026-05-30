"""문서 검색기 (Retriever).

- 현재는 BM25 기반 키워드 검색만 지원한다.
- 한국어 검색 성능을 위해 Kiwi 형태소 분석기를 우선 사용한다.
- 인덱스는 `crawler/crawler/data/rag_ready/chunks` 아래 JSON 청크 파일들로부터 구성된다.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rag.schemas.retrieval import RetrievalRequest
from rag.schemas.retrieved_doc import RetrievedDoc
from rag.retrieval.source_policy import allowed_source_types_for_values, forbidden_source_types_for_family
from rag.preprocess.query_features import (
    extract_query_features,
    required_entity_match_score,
    ui_noise_hits,
)
from rag.retrieval.canonical_source import canonical_notice_metadata

try:
    from kiwipiepy import Kiwi
except ImportError:  # pragma: no cover - 테스트 환경에서 선택적 의존성으로 허용
    Kiwi = None

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:  # pragma: no cover - psycopg2가 없는 환경에서는 파일 기반 검색을 유지
    psycopg2 = None
    DictCursor = None

_DB_USE_ENV_VAR = "RAG_USE_DB"
_DB_URL_ENV_VAR = "DATABASE_URL"
_RETRIEVAL_MODE_ENV_VAR = "RETRIEVAL_MODE"
_HYBRID_SCORE_MODE_ENV_VAR = "HYBRID_SCORE_MODE"
_HYBRID_LEXICAL_WEIGHT_ENV_VAR = "HYBRID_LEXICAL_WEIGHT"
_HYBRID_VECTOR_WEIGHT_ENV_VAR = "HYBRID_VECTOR_WEIGHT"
_HYBRID_SRRF_BETA_ENV_VAR = "HYBRID_SRRF_BETA"
_RESULT_DEDUPE_ENV_VAR = "RAG_DEDUPE_RESULTS"
_MAX_RESULTS_PER_DOC_ENV_VAR = "RAG_MAX_RESULTS_PER_DOC"
_MAX_RESULTS_PER_SOURCE_ENV_VAR = "RAG_MAX_RESULTS_PER_SOURCE"
_VECTOR_CANDIDATE_LIMIT_ENV_VAR = "RAG_VECTOR_CANDIDATE_LIMIT"

_DEFAULT_TOP_K = 10
_MIN_DB_SCORE = 0.35
_CATEGORY_SCORE_BONUS = 0.1
_ILIKE_SCORE_CAP = 0.6
_TITLE_MATCH_SCORE_CAP = 0.9
_SECTION_MATCH_SCORE_CAP = 0.7
_NOISE_PENALTY_CAP = 1.5
_DEFAULT_HYBRID_LEXICAL_WEIGHT = 0.55
_DEFAULT_HYBRID_VECTOR_WEIGHT = 0.45
_DEFAULT_HYBRID_SRRF_BETA = 10.0
_DEFAULT_MAX_RESULTS_PER_DOC = 2
_DEFAULT_MAX_RESULTS_PER_SOURCE = 2
_DEFAULT_VECTOR_CANDIDATE_LIMIT = 1000
_BM25_K1 = 1.5
_BM25_B = 0.75
_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_CHUNK_ENV_VAR = "RAG_CHUNK_DATA_DIR"
_DB_SEARCH_STOPWORDS = {
    "알려줘",
    "알려주",
    "뭐가",
    "무엇",
    "어떻게",
    "싶어",
    "필요해",
}
_DB_BOOST_STOPWORDS = {
    "운영",
    "시간",
    "기간",
    "신청",
    "방법",
    "일정",
    "안내",
    "공지",
    "학사",
    "정보",
}
_HYBRID_GENERIC_TERMS = _DB_SEARCH_STOPWORDS | _DB_BOOST_STOPWORDS | {"정보", "안내", "학교", "동의대", "동의대학교"}
_STATIC_SOURCE_TYPES = {"static", "index", "menu"}
_NOISY_SOURCE_TYPES = {"bids", "council_notice", "external_notice"}
_EXPLICIT_NOTICE_TERMS = {"모집공고", "채용공고", "신청서", "회의자료", "첨부", "첨부파일", "서식", "입찰", "공고"}
_UI_NOISE_TERMS = ("본문 바로가기", "게시물 좌측으로 이동", "게시물 우측으로 이동", "사이트맵", "로그인", "회원가입", "more", "sns")
_FAMILY_SEARCH_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "campus_address": (
        "가야 캠퍼스",
        "찾아오시는 길",
        "캠퍼스안내",
        "동의대학교 주소",
    ),
    "building_location": (
        "캠퍼스맵",
        "찾아오시는 길",
        "가야 캠퍼스",
        "주소",
        "정보공학관",
        "복지문화시설",
        "지천관",
        "상영관",
        "학생회관",
        "콜라보라운지",
    ),
    "welfare_facility": ("복지문화시설", "편의·복지", "학생식당", "헌혈의 집", "편의점", "콜라보라운지"),
    "academic_schedule": ("학사일정", "학사정보", "보강", "보강일정", "지정보강일", "중간시험", "기말시험", "개강일", "종강", "하계방학", "동계방학", "학위수여식"),
    "course_registration": ("수강신청", "2026학년도 1학기 수강신청 안내", "학사공지"),
    "seasonal_course_registration": ("계절수업", "하계 계절수업", "하계계절수업", "계절학기 수강신청"),
    "department_curriculum": ("컴퓨터공학과", "이수표", "교육과정", "전공필수"),
    "scholarship": ("국가장학금", "장학금", "신청기간", "신청방법"),
    "specific_scholarship": ("성적우수장학금", "성적우수장학생", "장학금 선발안내", "선발기준"),
    "dormitory": ("효민생활관", "행복기숙사", "생활관", "기숙사비", "입사신청", "입사 신청"),
    "academic_admin": ("휴학", "전과", "학사정보", "신청 방법", "학사지원팀"),
    "certificate": ("제증명서 발급", "재학증명서", "성적증명서", "증명서 발급"),
    "institution_history": ("연도별 연혁", "대학현황", "DEU", "1960년대", "2020년대"),
    "person_title": ("역대총장", "총장", "7대"),
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkRecord: # 인덱싱된 문서 청크를 나타내는 데이터 클래스
    chunk_id: str
    doc_id: str
    title: str
    content: str
    source_type: str
    source_url: str
    published_at: str | None
    department: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class IndexedChunk: # BM25 검색을 위해 토큰화되고 통계가 계산된 문서 청크
    record: ChunkRecord
    tokens: tuple[str, ...]
    term_freqs: dict[str, int]
    length: int


@dataclass(frozen=True)
class BM25Index: # 전체 인덱스 구조를 나타내는 데이터 클래스
    chunks: tuple[IndexedChunk, ...]
    chunks: tuple[IndexedChunk, ...]
    document_frequencies: dict[str, int]
    average_document_length: float


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    doc_id: str
    document: RetrievedDoc
    lexical_score: float | None = None
    vector_score: float | None = None
    rrf_score: float = 0.0
    final_score: float = 0.0
    search_mode: str = "hybrid_rrf"

# 한국어 텍스트를 BM25 검색에 적합한 토큰으로 변환하는 클래스
class KoreanBM25Tokenizer: 
    def __init__(self) -> None:
        self._kiwi = Kiwi() if Kiwi is not None else None

    # 텍스트를 토큰 리스트로 변환하는 메서드
    def tokenize(self, text: str) -> list[str]: 
        if not text:
            return []
        if self._kiwi is not None:
            return self._tokenize_with_kiwi(text)
        return self._tokenize_with_regex(text)

    # Kiwi 형태소 분석기를 사용하여 텍스트를 토큰화하는 메서드
    def _tokenize_with_kiwi(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in _TOKEN_PATTERN.findall(text.lower()):
            if len(token) == 1 and not token.isdigit():
                continue
            if token not in tokens:
                tokens.append(token)
        for token in self._kiwi.tokenize(text):
            normalized = token.form.strip().lower()
            if not normalized:
                continue
            if token.tag.startswith(("J", "E", "S", "X")):
                continue
            if len(normalized) == 1 and not normalized.isdigit():
                continue
            if normalized not in tokens:
                tokens.append(normalized)
        return tokens

    # 정규 표현식을 사용하여 텍스트를 토큰화하는 메서드 (Kiwi가 없는 경우)
    def _tokenize_with_regex(self, text: str) -> list[str]:
        tokens = []
        for token in _TOKEN_PATTERN.findall(text.lower()):
            if len(token) == 1 and not token.isdigit():
                continue
            normalized = re.sub(r"(은|는|이|가|을|를|에|의|로|으로|에서|부터|까지|도)$", "", token)
            if normalized:
                tokens.append(normalized)
        return tokens


_TOKENIZER = KoreanBM25Tokenizer()

# TODO - 향후 BM25 외에도 벡터 검색, 의미 검색 등 다양한 검색 전략이 추가될 수 있도록 구조 개선 필요
def retrieve_documents(
    query: str | None = None,
    keywords: list[str] | None = None,
    request: RetrievalRequest | None = None,
) -> list[RetrievedDoc]:
    if request is None:
        request = RetrievalRequest(
            query=query or "",
            query_variants=[query] if query else [],
            keywords=keywords or [],
        )

    if "empty_query" in request.fallback_triggers:
        return []

    if _use_database_retriever():
        try:
            retrieval_mode = _resolve_retrieval_mode(request)
            if retrieval_mode == "vector":
                documents = _retrieve_documents_from_database_vector(request)
                if not documents:
                    documents = _retrieve_relaxed_database_results(request, retrieval_mode)
                canonical_documents = _retrieve_canonical_documents_from_database_v4(request)
                if canonical_documents:
                    documents = _prepend_unique_docs(canonical_documents, documents)
                policy_documents = _retrieve_graduation_policy_documents_from_database(request)
                if policy_documents:
                    documents = _prepend_unique_docs(policy_documents, documents)
                return _postprocess_retrieved_docs(documents, request)

            if retrieval_mode == "hybrid":
                documents = _retrieve_documents_from_database_hybrid(request)
                if not documents:
                    documents = _retrieve_relaxed_database_results(request, retrieval_mode)
                if documents:
                    policy_documents = _retrieve_graduation_policy_documents_from_database(request)
                    if policy_documents:
                        documents = _prepend_unique_docs(policy_documents, documents)
                    return _postprocess_retrieved_docs(documents, request)

            documents = _retrieve_documents_from_database(request)
            if documents:  # DB에서 검색 결과가 있으면 반환
                policy_documents = _retrieve_graduation_policy_documents_from_database(request)
                if policy_documents:
                    documents = _prepend_unique_docs(policy_documents, documents)
                return _postprocess_retrieved_docs(documents, request)
            if request.filters:
                relaxed_request = request.model_copy(update={"filters": {}, "ranking_hints": {}, "category": None})
                documents = _retrieve_documents_from_database(relaxed_request)
                if documents:
                    for document in documents:
                        document.metadata["filters_relaxed"] = True
                        document.metadata["original_filters"] = request.filters
                    return _postprocess_retrieved_docs(documents, request)
        except Exception as exc:
            logger.exception(
                "database_retrieval_failed; falling back to file BM25 "
                "mode=%s strategy=%s query_vector_size=%s error=%s",
                _resolve_retrieval_mode(request),
                request.strategy,
                len(request.query_vector or []),
                exc,
            )

    # 파일 기반 BM25 검색 수행
    index = _load_bm25_index()
    if not index.chunks:
        return []

    query_tokens = _build_query_tokens(request)
    if not query_tokens:
        return []

    scored_docs = _score_documents(index=index, query_tokens=query_tokens, request=request)
    candidate_limit = max(request.top_k or _DEFAULT_TOP_K, (request.top_k or _DEFAULT_TOP_K) * 3)
    documents = _to_retrieved_docs(scored_docs[:candidate_limit], request)
    return _postprocess_retrieved_docs(documents, request)


# 테스트 코드에서 인덱스 캐시를 초기화할 수 있도록 lru_cache로 구현된 내부 함수들을 노출
def _build_query_tokens(request: RetrievalRequest) -> list[str]:
    candidate_texts = [
        request.query,
        *request.query_variants,
        *(request.keywords or []),
    ]
    tokens: list[str] = []
    for text in candidate_texts:
        for token in _TOKENIZER.tokenize(text):
            if token not in tokens:
                tokens.append(token)
    return tokens


def _use_database_retriever() -> bool:
    # RAG_USE_DB가 명시적으로 false로 설정된 경우만 DB 검색 비활성화
    if os.getenv(_DB_USE_ENV_VAR, "").strip().lower() in ("0", "false", "no"):
        return False
    # psycopg2가 없으면 DB 검색 불가
    if psycopg2 is None or DictCursor is None:
        return False
    # DATABASE_URL이 있거나 POSTGRES_* 환경 변수가 있으면 DB 검색 활성화
    if os.getenv(_DB_URL_ENV_VAR):
        return True
    if os.getenv("POSTGRES_HOST") or os.getenv("POSTGRES_DB") or os.getenv("POSTGRES_USER") or os.getenv("POSTGRES_PASSWORD"):
        return True
    # 환경 변수가 없어도 supabase 연결을 시도하도록 기본적으로 True 반환
    # (실제 연결 실패 시 파일 기반 검색으로 fallback)
    return True


def _retrieve_relaxed_database_results(request: RetrievalRequest, retrieval_mode: str) -> list[RetrievedDoc]:
    if not request.filters:
        return []
    relaxed_request = request.model_copy(update={"filters": {}, "ranking_hints": {}, "category": None})
    if retrieval_mode == "vector":
        documents = _retrieve_documents_from_database_vector(relaxed_request)
    elif retrieval_mode == "hybrid":
        documents = _retrieve_documents_from_database_hybrid(relaxed_request)
    else:
        documents = _retrieve_documents_from_database(relaxed_request)
    for document in documents:
        document.metadata["filters_relaxed"] = True
        document.metadata["original_filters"] = request.filters
    return documents


def _resolve_retrieval_mode(request: RetrievalRequest) -> str:
    configured_mode = os.getenv(_RETRIEVAL_MODE_ENV_VAR, "").strip().lower()
    if configured_mode in {"lexical", "vector", "hybrid"}:
        return configured_mode
    if request.strategy in {"dense", "vector"}:
        return "vector"
    if request.strategy == "hybrid":
        return "hybrid"
    return "hybrid"


def _normalize_database_url(database_url: str) -> str:
    normalized = database_url.strip()
    if normalized.startswith("postgresql+psycopg2://"):
        return normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    return normalized


def _open_db_connection():
    database_url = os.getenv(_DB_URL_ENV_VAR, "").strip()
    if database_url:
        database_url = _normalize_database_url(database_url)
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
    )


def _build_db_search_term(request: RetrievalRequest) -> str:
    candidate_texts = [
        request.query,
        *request.query_variants,
        *(request.keywords or []),
    ]
    terms = [text.strip() for text in candidate_texts if text and text.strip()]
    return " ".join(dict.fromkeys(terms))


def _build_db_search_terms(request: RetrievalRequest) -> list[str]:
    family = _request_query_family(request)
    request_text = " ".join([request.query, *(request.query_variants or []), *(request.keywords or [])])
    if family == "specific_scholarship" and "성적우수" in request_text:
        return ["성적우수장학금", "성적우수장학생", "성적우수", "선발안내", "선발", "기준", "장학금"]
    if family == "academic_admin":
        if "휴학" in request_text:
            return ["휴학", "휴학신청", "신청", "방법", "절차", "학사지원"]
        if "전과" in request_text:
            return ["전과", "전과 신청", "신청기간", "신청", "방법", "학사공지"]
    if family == "certificate":
        return ["제증명서", "증명서", "증명서 발급", "재학증명서", "성적증명서", "발급"]
    feature_terms = _request_feature_terms(request)
    family_expansions = _request_family_search_expansions(request)
    candidate_texts = [
        *family_expansions,
        *feature_terms,
        *(request.keywords or []),
        *(request.query_variants or []),
        request.query,
    ]
    terms: list[str] = []
    for text in candidate_texts:
        for token in _TOKENIZER.tokenize(text):
            if _is_weak_db_search_term(token):
                continue
            if token and token not in terms:
                terms.append(token)
    return terms[:20]


def _request_query_family(request: RetrievalRequest) -> str:
    query_features = request.log_fields.get("query_features") if isinstance(request.log_fields, dict) else None
    if isinstance(query_features, dict):
        return str(query_features.get("family") or "general")
    return extract_query_features(request.query, request.keywords).family


def _request_family_search_expansions(request: RetrievalRequest) -> list[str]:
    family = _request_query_family(request)
    query_features = request.log_fields.get("query_features") if isinstance(request.log_fields, dict) else None
    domain = str(query_features.get("domain") or "") if isinstance(query_features, dict) else ""
    if family == "general" and domain == "course":
        family = "course_registration"
    elif family == "general" and domain == "scholarship":
        family = "scholarship"
    expansions = list(_FAMILY_SEARCH_EXPANSIONS.get(family, ()))
    text = " ".join([request.query, *(request.query_variants or []), *(request.keywords or [])])
    if family in {"building_location", "campus_address"}:
        if "편의점" not in text:
            expansions = [term for term in expansions if term != "복지문화시설"]
        if "정보공학관" not in text and "23" not in text:
            expansions = [term for term in expansions if term != "정보공학관"]
    if family == "welfare_facility":
        if not any(term in text for term in ("학생식당", "학식", "식당")):
            expansions = [term for term in expansions if term != "학생식당"]
        if "헌혈" not in text:
            expansions = [term for term in expansions if term != "헌혈의 집"]
    if family == "specific_scholarship":
        if "성적우수" not in text:
            expansions = [term for term in expansions if not term.startswith("성적우수")]
    if family == "seasonal_course_registration":
        expansions = [*expansions, "2026-하계 계절수업 안내"]
    if family == "course_registration" and not any(term in text for term in ("계절", "타대학", "마이크로디그리")):
        expansions.extend(["일반 수강신청", "1학기 수강신청"])
    return expansions


def _request_feature_terms(request: RetrievalRequest) -> list[str]:
    query_features = request.log_fields.get("query_features") if isinstance(request.log_fields, dict) else None
    if isinstance(query_features, dict):
        terms = [
            *[str(value) for value in query_features.get("required_terms") or []],
            *[str(value) for value in query_features.get("strong_terms") or []],
            *[str(value) for value in query_features.get("protected_terms") or []],
        ]
        return [term for term in terms if term]
    return extract_query_features(request.query, request.keywords).strong_terms


def _build_exact_phrase_patterns(request: RetrievalRequest) -> list[str]:
    phrases: list[str] = []
    for text in [request.query, *(request.query_variants or [])]:
        phrase = " ".join((text or "").split())
        if len(phrase) < 2:
            continue
        if phrase not in phrases:
            phrases.append(phrase)
    return [f"%{phrase}%" for phrase in phrases[:4]] or ["__NO_EXACT_PHRASE_MATCH__"]


def _build_boost_patterns(search_terms: list[str]) -> tuple[list[str], bool]:
    boost_terms = [
        term
        for term in search_terms
        if term not in _DB_BOOST_STOPWORDS and not (len(term) == 1 and not term.isdigit())
    ]
    return [f"%{term}%" for term in boost_terms] or ["__NO_BOOST_TERM_MATCH__"], bool(boost_terms)


def _feature_log_fields(request: RetrievalRequest) -> dict[str, Any]:
    query_features = request.log_fields.get("query_features") if isinstance(request.log_fields, dict) else None
    if not isinstance(query_features, dict):
        query_features = extract_query_features(request.query, request.keywords).to_log_dict()
    ranking_hints = request.ranking_hints or {}
    return {
        "query_features": query_features,
        "ranking_hints": ranking_hints,
        "temporal_signals": ranking_hints.get("temporal_signals", {}) if isinstance(ranking_hints, dict) else {},
        "strong_terms": query_features.get("strong_terms", []),
        "required_terms": query_features.get("required_terms", []),
        "query_family": query_features.get("family"),
    }


def _is_weak_db_search_term(term: str) -> bool:
    if term in _DB_SEARCH_STOPWORDS:
        return True
    if re.fullmatch(r"[A-Za-z]+", term) and len(term) < 3:
        return True
    return False


def _build_tsquery_or_expression(terms: list[str]) -> str:
    safe_terms = [term for term in terms if re.fullmatch(r"[가-힣A-Za-z0-9]+", term)]
    return " | ".join(safe_terms)


def _build_db_filter_conditions(request: RetrievalRequest) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    parameters: list[Any] = []

    return " AND ".join(conditions), parameters


def _source_type_hint_values(request: RetrievalRequest) -> list[str]:
    filter_values: list[str] = []
    ranking_hints = request.ranking_hints or {}
    for field in ("document_category", "source_boosts", "category_values"):
        for value in _hint_values(ranking_hints.get(field)):
            if value not in filter_values:
                filter_values.append(str(value))
    category = ranking_hints.get("category")
    if category and str(category) not in filter_values:
        filter_values.append(str(category))

    # Backward compatibility for direct callers still passing source hints in filters.
    if not filter_values:
        for field in ("document_category", "category"):
            for value in request.filters.get(field, []) or []:
                if value not in filter_values:
                    filter_values.append(str(value))
    return allowed_source_types_for_values(filter_values)


def _hint_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _category_bonus_sql(request: RetrievalRequest, source_expression: str) -> tuple[str, list[Any]]:
    source_type_hints = _source_type_hint_values(request)
    if not source_type_hints:
        return "0", []
    return f"CASE WHEN {source_expression} = ANY(%s) THEN %s ELSE 0 END", [
        source_type_hints,
        _CATEGORY_SCORE_BONUS,
    ]


def _category_bonus_for_source(source_type: str, request: RetrievalRequest) -> float:
    if source_type in _source_type_hint_values(request):
        return _CATEGORY_SCORE_BONUS
    return 0.0


def _lexical_norm_score(score: float) -> float:
    score = max(float(score or 0.0), 0.0)
    return round(score / (score + 1.0), 6)


def _has_query_vector(request: RetrievalRequest) -> bool:
    return bool(request.query_vector)


def _to_pg_vector(vector: list[float]) -> str:
    values: list[str] = []
    for item in vector:
        value = float(item)
        if not math.isfinite(value):
            raise ValueError("query_vector contains a non-finite value")
        values.append(str(value))
    return "[" + ",".join(values) + "]"


def _retrieve_documents_from_database_vector(request: RetrievalRequest) -> list[RetrievedDoc]:
    if not _has_query_vector(request):
        logger.warning(
            "vector_retrieval_skipped_missing_query_vector strategy=%s query=%r",
            request.strategy,
            request.query,
        )
        return []

    category_bonus_sql, category_bonus_params = _category_bonus_sql(request, "documents.source_type")
    result_limit = max(request.top_k or _DEFAULT_TOP_K, (request.top_k or _DEFAULT_TOP_K) * 3)
    candidate_limit = _vector_candidate_limit(result_limit)
    sql = """
    WITH nearest_embeddings AS MATERIALIZED (
        SELECT
            chunk_id,
            embedding <=> %s::vector AS vector_distance
        FROM chunk_embeddings
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    ),
    latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        GROUP BY doc_id
    ),
    latest_attachment_presence AS (
        SELECT chunks.doc_id, bool_or(chunks.section_type = 'attachment') AS has_latest_attachment
        FROM chunks
        JOIN document_versions
          ON document_versions.id = chunks.document_version_id
        JOIN latest_document_versions
          ON latest_document_versions.doc_id = chunks.doc_id
         AND latest_document_versions.latest_version = document_versions.version
        GROUP BY chunks.doc_id
    ),
    latest_attachment_versions AS (
        SELECT chunks.doc_id, max(document_versions.version) AS latest_attachment_version
        FROM chunks
        JOIN document_versions
          ON document_versions.id = chunks.document_version_id
        WHERE chunks.section_type = 'attachment'
        GROUP BY chunks.doc_id
    )
    SELECT
        chunks.chunk_id,
        chunks.doc_id,
        chunks.chunk_index,
        chunks.section_index,
        chunks.section_type,
        chunks.section_title,
        chunks.content,
        chunks.content_length,
        chunks.content_hash,
        document_versions.version,
        chunks.document_version_id,
        chunks.metadata AS chunk_metadata,
        documents.title,
        documents.source_url,
        documents.source_type,
        documents.department,
        documents.published_at,
        documents.metadata AS document_metadata,
        1 - nearest_embeddings.vector_distance + {category_bonus_sql} AS vector_score
    FROM nearest_embeddings
    JOIN chunks ON chunks.chunk_id = nearest_embeddings.chunk_id
    JOIN documents ON documents.doc_id = chunks.doc_id
    LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
    LEFT JOIN latest_document_versions
      ON latest_document_versions.doc_id = chunks.doc_id
    LEFT JOIN latest_attachment_presence
      ON latest_attachment_presence.doc_id = chunks.doc_id
    LEFT JOIN latest_attachment_versions
      ON latest_attachment_versions.doc_id = chunks.doc_id
    WHERE (
        chunks.document_version_id IS NULL
        OR document_versions.version = latest_document_versions.latest_version
        OR (
            chunks.section_type = 'attachment'
            AND coalesce(latest_attachment_presence.has_latest_attachment, false) = false
            AND document_versions.version = latest_attachment_versions.latest_attachment_version
        )
    )
    """.format(category_bonus_sql=category_bonus_sql)

    filter_clause, filter_params = _build_db_filter_conditions(request)
    if filter_clause:
        sql += "\n      AND " + filter_clause

    sql += """
    ORDER BY nearest_embeddings.vector_distance ASC,
             documents.published_at DESC NULLS LAST,
             chunks.chunk_id ASC
    LIMIT %s
    """

    try:
        pg_vector = _to_pg_vector(request.query_vector)
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    sql,
                    (
                        pg_vector,
                        pg_vector,
                        candidate_limit,
                        *category_bonus_params,
                        *filter_params,
                        result_limit,
                    ),
                )
                rows = cur.fetchall()
    except (psycopg2.Error, ValueError) as exc:
        logger.warning(
            "vector_retrieval_failed query_vector_size=%s filters=%s error=%s",
            len(request.query_vector or []),
            request.filters,
            exc,
        )
        return []

    retrieved_docs: list[RetrievedDoc] = []
    logger.info(
        "vector_retrieval_completed query=%r query_vector_size=%s result_count=%s top_k=%s",
        request.query,
        len(request.query_vector or []),
        len(rows),
        request.top_k,
    )
    for row in rows:
        vector_score = float(row["vector_score"] or 0.0)
        document_metadata = _dict_or_empty(row["document_metadata"])
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        retrieved_docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=vector_score,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": _resolve_retrieval_mode(request),
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "search_mode": "vector_cosine",
                    "lexical_score": None,
                    "vector_score": vector_score,
                    "rrf_score": None,
                    "final_score": vector_score,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return retrieved_docs


def _vector_candidate_limit(result_limit: int) -> int:
    configured = _int_env(_VECTOR_CANDIDATE_LIMIT_ENV_VAR, _DEFAULT_VECTOR_CANDIDATE_LIMIT)
    return max(result_limit, configured)


def _retrieve_documents_from_database_hybrid(request: RetrievalRequest) -> list[RetrievedDoc]:
    if not _has_query_vector(request):
        logger.warning(
            "hybrid_retrieval_missing_query_vector; lexical branch only query=%r strategy=%s",
            request.query,
            request.strategy,
        )
    started_at = time.perf_counter()
    lexical_started_at = time.perf_counter()
    lexical_docs = _retrieve_documents_from_database(request)
    lexical_ms = (time.perf_counter() - lexical_started_at) * 1000
    vector_started_at = time.perf_counter()
    vector_docs = _retrieve_documents_from_database_vector(request)
    vector_ms = (time.perf_counter() - vector_started_at) * 1000
    merge_started_at = time.perf_counter()
    candidates = merge_retrieval_candidates(lexical_docs, vector_docs)
    docs = _candidates_to_retrieved_docs(candidates, request)
    merge_ms = (time.perf_counter() - merge_started_at) * 1000
    for doc in docs:
        doc.metadata["hybrid_lexical_candidate_count"] = len(lexical_docs)
        doc.metadata["hybrid_vector_candidate_count"] = len(vector_docs)
        doc.metadata["hybrid_vector_missing"] = not _has_query_vector(request)
        doc.metadata["hybrid_lexical_ms"] = round(lexical_ms, 3)
        doc.metadata["hybrid_vector_ms"] = round(vector_ms, 3)
        doc.metadata["hybrid_merge_ms"] = round(merge_ms, 3)
    logger.info(
        "hybrid_retrieval_completed query=%r lexical_count=%s vector_count=%s merged_count=%s query_vector_size=%s lexical_ms=%.1f vector_ms=%.1f merge_ms=%.1f total_ms=%.1f",
        request.query,
        len(lexical_docs),
        len(vector_docs),
        len(docs),
        len(request.query_vector or []),
        lexical_ms,
        vector_ms,
        merge_ms,
        (time.perf_counter() - started_at) * 1000,
    )
    return docs


def _retrieve_canonical_documents_from_database_v2(request: RetrievalRequest) -> list[RetrievedDoc]:
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    if query_family not in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return []

    family_terms = {
        "academic_schedule": ["학사일정", "보강일정", "보강", "scheduleList"],
        "course_registration": ["수강신청"],
        "seasonal_course_registration": ["계절수업", "계절학기"],
    }.get(query_family, [])
    search_terms = [
        term.strip()
        for term in [*_build_db_search_terms(request), *family_terms]
        if len(term.strip()) >= 2 and term.strip() not in {"기간", "일정", "알려줘"}
    ][:6]
    if not search_terms and not family_terms:
        return []

    ilike_patterns = [f"%{term}%" for term in search_terms] or ["%%__never_match__%%"]
    family_patterns = [f"%{term}%" for term in family_terms] or ["%%__never_match__%%"]
    sql = """
    WITH latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        GROUP BY doc_id
    )
    SELECT
        chunks.chunk_id,
        chunks.doc_id,
        chunks.chunk_index,
        chunks.section_index,
        chunks.section_type,
        chunks.section_title,
        chunks.content,
        chunks.content_length,
        chunks.content_hash,
        document_versions.version,
        chunks.document_version_id,
        chunks.metadata AS chunk_metadata,
        documents.title,
        documents.source_url,
        documents.source_type,
        documents.department,
        documents.published_at,
        documents.metadata AS document_metadata
    FROM chunks
    JOIN documents ON documents.doc_id = chunks.doc_id
    LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
    LEFT JOIN latest_document_versions
      ON latest_document_versions.doc_id = chunks.doc_id
    WHERE (
        chunks.document_version_id IS NULL
        OR document_versions.version = latest_document_versions.latest_version
    )
      AND (
        coalesce((documents.metadata->>'canonical_notice_family'), '') = %s
        OR documents.title ILIKE ANY(%s)
        OR documents.source_url ILIKE ANY(%s)
      )
      AND (
        coalesce((documents.metadata->>'is_canonical_notice'), 'false') = 'true'
        OR documents.source_type IN ('institution', 'academic_notice', 'academic', 'academic_calendar', 'academic_support', 'notice')
        OR documents.source_url ILIKE '%%www.deu.ac.kr/www%%'
        OR documents.source_url ILIKE '%%dess.deu.ac.kr%%'
      )
    ORDER BY
      coalesce(nullif(documents.metadata->>'canonical_source_rank', '')::int, 99) ASC,
      CASE WHEN coalesce((documents.metadata->>'is_canonical_notice'), 'false') = 'true' THEN 0 ELSE 1 END,
      CASE WHEN documents.source_url ILIKE '%%dess.deu.ac.kr%%' THEN 0 ELSE 1 END,
      CASE WHEN documents.source_url ILIKE '%%www.deu.ac.kr/www%%' THEN 0 ELSE 1 END,
      documents.published_at DESC NULLS LAST,
      chunks.chunk_index ASC
    LIMIT 5
    """
    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (query_family, ilike_patterns, family_patterns))
                rows = cur.fetchall()
    except psycopg2.Error as exc:
        logger.exception("canonical_supplement_v3_failed query=%r family=%s error=%s", request.query, query_family, exc)
        return []

    docs: list[RetrievedDoc] = []
    for row in rows:
        document_metadata = _dict_or_empty(row["document_metadata"])
        canonical_metadata = canonical_notice_metadata(
            {
                "title": row["title"] or "",
                "source_url": row["source_url"] or "",
                "source_type": row["source_type"] or "",
                "content_hash": row["content_hash"] or "",
            }
        )
        document_metadata = {**canonical_metadata, **document_metadata}
        if document_metadata.get("canonical_notice_family") != query_family:
            continue
        if not document_metadata.get("is_canonical_notice"):
            continue
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=1.05,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "canonical_source_supplement",
                    "canonical_source_supplement": True,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return docs


def _retrieve_graduation_policy_documents_from_database(request: RetrievalRequest) -> list[RetrievedDoc]:
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    if query_family != "graduation" or re.search(r"[가-힣A-Za-z0-9]+(?:학과|전공|학부)", request.query or ""):
        return []

    title_patterns = [
        "%학사정보 종합안내%",
        "%졸업기준%",
        "%졸업요건%",
        "%졸업인증제도%",
        "%졸업학점%",
    ]
    detail_patterns = [
        "%졸업요건%",
        "%졸업기준%",
        "%졸업학점%",
        "%졸업인증%",
        "%이수학점%",
    ]
    sql = """
    WITH doc_candidates AS (
        SELECT doc_id, title, source_url, source_type, department, published_at, metadata AS document_metadata
        FROM documents
        WHERE source_type IN ('institution', 'academic_notice', 'academic_support', 'academic')
          AND (
            title ILIKE ANY(%s)
            OR source_url ILIKE '%%academicguide%%'
          )
        ORDER BY
          CASE WHEN source_type = 'institution' THEN 0 ELSE 1 END,
          CASE WHEN title ILIKE '%%학사정보 종합안내%%' THEN 0 ELSE 1 END,
          published_at DESC NULLS LAST,
          doc_id ASC
        LIMIT 8
    ),
    latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        WHERE doc_id IN (SELECT doc_id FROM doc_candidates)
        GROUP BY doc_id
    ),
    chunk_candidates AS (
        SELECT DISTINCT ON (chunks.doc_id)
            chunks.chunk_id,
            chunks.doc_id,
            chunks.chunk_index,
            chunks.section_index,
            chunks.section_type,
            chunks.section_title,
            chunks.content,
            chunks.content_length,
            chunks.content_hash,
            document_versions.version,
            chunks.document_version_id,
            chunks.metadata AS chunk_metadata,
            doc_candidates.title,
            doc_candidates.source_url,
            doc_candidates.source_type,
            doc_candidates.department,
            doc_candidates.published_at,
            doc_candidates.document_metadata
        FROM doc_candidates
        JOIN chunks ON chunks.doc_id = doc_candidates.doc_id
        LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
        LEFT JOIN latest_document_versions
          ON latest_document_versions.doc_id = chunks.doc_id
        WHERE (
            chunks.document_version_id IS NULL
            OR document_versions.version = latest_document_versions.latest_version
        )
        ORDER BY
            chunks.doc_id,
            CASE
                WHEN chunks.section_title ILIKE ANY(%s) THEN 0
                WHEN chunks.content ILIKE ANY(%s) THEN 0
                ELSE 1
            END,
            chunks.chunk_index ASC
    )
    SELECT *
    FROM chunk_candidates
    ORDER BY
      CASE WHEN source_type = 'institution' THEN 0 ELSE 1 END,
      published_at DESC NULLS LAST,
      chunk_id ASC
    LIMIT 5
    """
    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (title_patterns, detail_patterns, detail_patterns))
                rows = cur.fetchall()
    except psycopg2.Error as exc:
        logger.exception("graduation_policy_supplement_failed query=%r error=%s", request.query, exc)
        return []

    docs: list[RetrievedDoc] = []
    search_terms = [
        term
        for term in [*_build_db_search_terms(request), "학사정보 종합안내", "졸업기준", "졸업인증제도"]
        if len(term.strip()) >= 2
    ][:8]
    for row in rows:
        document_metadata = _dict_or_empty(row["document_metadata"])
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=1.18,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "graduation_policy_supplement",
                    "canonical_source_supplement": True,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return docs


def _retrieve_canonical_documents_from_database_v3(request: RetrievalRequest) -> list[RetrievedDoc]:
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    if query_family not in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return []

    family_terms = {
        "academic_schedule": ["학사일정", "보강일정", "보강", "scheduleList"],
        "course_registration": ["수강신청"],
        "seasonal_course_registration": ["계절수업", "계절학기"],
    }.get(query_family, [])
    search_terms = [
        term.strip()
        for term in [*_build_db_search_terms(request), *family_terms]
        if len(term.strip()) >= 2 and term.strip() not in {"기간", "일정", "알려줘"}
    ][:6]
    ilike_patterns = [f"%{term}%" for term in search_terms] or ["%%__never_match__%%"]
    family_patterns = [f"%{term}%" for term in family_terms] or ["%%__never_match__%%"]
    sql = """
    WITH doc_candidates AS (
        SELECT
            doc_id,
            title,
            source_url,
            source_type,
            department,
            published_at,
            metadata AS document_metadata,
            coalesce(nullif(metadata->>'canonical_source_rank', '')::int, 99) AS canonical_rank
        FROM documents
        WHERE (
            coalesce((metadata->>'canonical_notice_family'), '') = %s
            OR title ILIKE ANY(%s)
            OR source_url ILIKE ANY(%s)
        )
          AND (
            coalesce((metadata->>'is_canonical_notice'), 'false') = 'true'
            OR source_type IN ('institution', 'academic_notice', 'academic', 'academic_calendar', 'academic_support', 'notice')
            OR source_url ILIKE '%%www.deu.ac.kr/www%%'
            OR source_url ILIKE '%%dess.deu.ac.kr%%'
          )
        ORDER BY
            canonical_rank ASC,
            CASE WHEN coalesce((metadata->>'is_canonical_notice'), 'false') = 'true' THEN 0 ELSE 1 END,
            CASE WHEN source_url ILIKE '%%dess.deu.ac.kr%%' THEN 0 ELSE 1 END,
            CASE WHEN source_url ILIKE '%%www.deu.ac.kr/www%%' THEN 0 ELSE 1 END,
            published_at DESC NULLS LAST,
            doc_id ASC
        LIMIT 10
    ),
    latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        WHERE doc_id IN (SELECT doc_id FROM doc_candidates)
        GROUP BY doc_id
    ),
    chunk_candidates AS (
        SELECT DISTINCT ON (chunks.doc_id)
            chunks.chunk_id,
            chunks.doc_id,
            chunks.chunk_index,
            chunks.section_index,
            chunks.section_type,
            chunks.section_title,
            chunks.content,
            chunks.content_length,
            chunks.content_hash,
            document_versions.version,
            chunks.document_version_id,
            chunks.metadata AS chunk_metadata,
            doc_candidates.title,
            doc_candidates.source_url,
            doc_candidates.source_type,
            doc_candidates.department,
            doc_candidates.published_at,
            doc_candidates.document_metadata,
            doc_candidates.canonical_rank
        FROM doc_candidates
        JOIN chunks ON chunks.doc_id = doc_candidates.doc_id
        LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
        LEFT JOIN latest_document_versions
          ON latest_document_versions.doc_id = chunks.doc_id
        WHERE (
            chunks.document_version_id IS NULL
            OR document_versions.version = latest_document_versions.latest_version
        )
        ORDER BY
            chunks.doc_id,
            CASE
                WHEN chunks.section_title ILIKE ANY(%s) THEN 0
                WHEN chunks.content ILIKE ANY(%s) THEN 0
                ELSE 1
            END,
            chunks.chunk_index ASC
    )
    SELECT *
    FROM chunk_candidates
    ORDER BY canonical_rank ASC, published_at DESC NULLS LAST, chunk_id ASC
    LIMIT 5
    """
    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (query_family, ilike_patterns, family_patterns, ilike_patterns, ilike_patterns))
                rows = cur.fetchall()
    except psycopg2.Error as exc:
        logger.exception("canonical_supplement_v3_failed query=%r family=%s error=%s", request.query, query_family, exc)
        return []

    docs: list[RetrievedDoc] = []
    for row in rows:
        document_metadata = _dict_or_empty(row["document_metadata"])
        canonical_metadata = canonical_notice_metadata(
            {
                "title": row["title"] or "",
                "source_url": row["source_url"] or "",
                "source_type": row["source_type"] or "",
                "content_hash": row["content_hash"] or "",
            }
        )
        document_metadata = {**canonical_metadata, **document_metadata}
        if document_metadata.get("canonical_notice_family") != query_family:
            continue
        if not document_metadata.get("is_canonical_notice"):
            continue
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=1.1,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "canonical_source_supplement",
                    "canonical_source_supplement": True,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return docs


def _retrieve_canonical_documents_from_database_v4(request: RetrievalRequest) -> list[RetrievedDoc]:
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    if query_family not in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return []

    family_terms = {
        "academic_schedule": ["학사일정", "보강일정", "보강", "scheduleList", "개강일", "종강", "학위수여식"],
        "course_registration": ["수강신청"],
        "seasonal_course_registration": ["계절수업", "계절학기"],
    }.get(query_family, [])
    search_terms = [
        term.strip()
        for term in [*_build_db_search_terms(request), *family_terms]
        if len(term.strip()) >= 2 and term.strip() not in {"기간", "일정", "알려줘"}
    ][:6]
    title_patterns = [f"%{term}%" for term in [*search_terms, *family_terms]] or ["%%__never_match__%%"]
    primary_detail_patterns = [f"%{term}%" for term in _canonical_notice_primary_detail_terms(query_family)]
    detail_patterns = [f"%{term}%" for term in _canonical_notice_detail_terms(query_family)]
    semester_pattern = _canonical_notice_semester_pattern(request.query, query_family)

    docs_sql = """
    SELECT doc_id, title, source_url, source_type, department, published_at, content_hash, metadata
    FROM documents
    WHERE (
        coalesce((metadata->>'canonical_notice_family'), '') = %s
        OR title ILIKE ANY(%s)
        OR source_url ILIKE '%%scheduleList%%'
    )
      AND (
        coalesce((metadata->>'is_canonical_notice'), 'false') = 'true'
        OR source_type IN ('institution', 'academic_notice', 'academic', 'academic_calendar', 'academic_support', 'notice')
        OR source_url ILIKE '%%www.deu.ac.kr/www%%'
        OR source_url ILIKE '%%dess.deu.ac.kr%%'
      )
    ORDER BY
      coalesce(nullif(metadata->>'canonical_source_rank', '')::int, 99) ASC,
      CASE WHEN coalesce((metadata->>'is_canonical_notice'), 'false') = 'true' THEN 0 ELSE 1 END,
      published_at DESC NULLS LAST,
      doc_id ASC
    LIMIT 300
    """
    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(docs_sql, (query_family, title_patterns))
                doc_rows = cur.fetchall()
                ranked_doc_rows = _rank_canonical_doc_rows(doc_rows, query_family, request.query, search_terms)
                if not ranked_doc_rows:
                    return []
                doc_ids = [row["doc_id"] for _, row, _ in ranked_doc_rows[:5]]
                cur.execute(
                    """
                    WITH latest_document_versions AS (
                        SELECT doc_id, max(version) AS latest_version
                        FROM document_versions
                        WHERE doc_id = ANY(%s)
                        GROUP BY doc_id
                    )
                    SELECT
                        chunks.chunk_id,
                        chunks.doc_id,
                        chunks.chunk_index,
                        chunks.section_index,
                        chunks.section_type,
                        chunks.section_title,
                        chunks.content,
                        chunks.content_length,
                        chunks.content_hash,
                        document_versions.version,
                        chunks.document_version_id,
                        chunks.metadata AS chunk_metadata,
                        documents.title,
                        documents.source_url,
                        documents.source_type,
                        documents.department,
                        documents.published_at,
                        documents.metadata AS document_metadata
                    FROM chunks
                    JOIN documents ON documents.doc_id = chunks.doc_id
                    LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
                    LEFT JOIN latest_document_versions
                      ON latest_document_versions.doc_id = chunks.doc_id
                    WHERE chunks.doc_id = ANY(%s)
                      AND (
                        chunks.document_version_id IS NULL
                        OR document_versions.version = latest_document_versions.latest_version
                      )
                    ORDER BY
                        array_position(%s, chunks.doc_id),
                        CASE
                            WHEN %s <> '' AND chunks.content ILIKE %s AND chunks.content ILIKE ANY(%s) THEN 0
                            WHEN chunks.content ILIKE ANY(%s) THEN 1
                            WHEN chunks.section_title ILIKE ANY(%s) THEN 2
                            WHEN chunks.content ILIKE ANY(%s) THEN 2
                            WHEN chunks.section_type = 'attachment' AND chunks.content ILIKE ANY(%s) THEN 3
                            WHEN chunks.section_title ILIKE ANY(%s) THEN 3
                            WHEN chunks.content ILIKE ANY(%s) THEN 4
                            ELSE 5
                        END,
                        chunks.chunk_index ASC
                    LIMIT 20
                    """,
                    (
                        doc_ids,                  # WITH latest_document_versions WHERE doc_id = ANY(%s)
                        doc_ids,                  # WHERE chunks.doc_id = ANY(%s)
                        doc_ids,                  # array_position(%s, chunks.doc_id)
                        semester_pattern,         # CASE WHEN %s <> ''
                        semester_pattern,         # AND content ILIKE %s
                        primary_detail_patterns,  # AND content ILIKE ANY(%s) → CASE 0
                        primary_detail_patterns,  # WHEN content ILIKE ANY(%s) → CASE 1
                        detail_patterns,          # WHEN section_title ILIKE ANY(%s) → CASE 2
                        detail_patterns,          # WHEN content ILIKE ANY(%s) → CASE 2
                        title_patterns,           # WHEN attachment content ILIKE ANY(%s) → CASE 3
                        title_patterns,           # WHEN section_title ILIKE ANY(%s) → CASE 3
                        title_patterns,           # WHEN content ILIKE ANY(%s) → CASE 4
                    ),
                )
                chunk_rows = cur.fetchall()
    except psycopg2.Error as exc:
        logger.exception("canonical_supplement_v4_failed query=%r family=%s error=%s", request.query, query_family, exc)
        return []

    chunks_by_doc: dict[str, list[Any]] = {}
    for row in chunk_rows:
        chunks_by_doc.setdefault(row["doc_id"], []).append(row)

    docs: list[RetrievedDoc] = []
    metadata_by_doc = {row["doc_id"]: metadata for _, row, metadata in ranked_doc_rows}
    for doc_id in doc_ids:
        max_chunks = 4 if query_family == "academic_schedule" else 3
        for chunk_offset, row in enumerate(chunks_by_doc.get(doc_id, [])[:max_chunks]):
            document_metadata = {**metadata_by_doc.get(doc_id, {}), **_dict_or_empty(row["document_metadata"])}
            chunk_metadata = _dict_or_empty(row["chunk_metadata"])
            docs.append(
                RetrievedDoc(
                    doc_id=row["doc_id"],
                    chunk_id=row["chunk_id"],
                    content=row["content"],
                    score=1.15 - (chunk_offset * 0.01),
                    title=row["title"] or "",
                    source=row["source_url"] or row["source_type"] or "",
                    category=request.category or row["source_type"],
                    metadata={
                        **document_metadata,
                        **chunk_metadata,
                        **request.log_fields,
                        **_feature_log_fields(request),
                        "strategy": request.strategy,
                        "query": request.query,
                        "keywords": request.keywords,
                        "filters": request.filters,
                        "matched_terms": search_terms,
                        "search_mode": "canonical_source_supplement",
                        "canonical_source_supplement": True,
                        "canonical_chunk_pack": True,
                        "source_type": row["source_type"],
                        "department": row["department"],
                        "published_at": row["published_at"],
                        "chunk_index": row["chunk_index"],
                        "section_index": row["section_index"],
                        "section_type": row["section_type"],
                        "section_title": row["section_title"],
                        "content_length": row["content_length"],
                        "content_hash": row["content_hash"],
                        "version": row["version"],
                        "document_version_id": row["document_version_id"],
                    },
                )
            )
    return docs


def _canonical_notice_primary_detail_terms(query_family: str) -> list[str]:
    if query_family == "course_registration":
        return [
            "수강신청 일자:",
            "수강신청시작일자",
        ]
    if query_family == "seasonal_course_registration":
        return [
            "수강신청 일자:",
            "개설기간",
        ]
    if query_family == "academic_schedule":
        return [
            "보강일정",
            "지정보강일",
            "보강",
            "학기별 학사일정",
            "2026년 1학기",
            "2026년 2학기",
            # 졸업식/학위수여식 포함 chunk 우선 선택 (공백 포함 패턴)
            "학위 수여식",
            "전기 학위 수여식",
            "후기 학위 수여식",
        ]
    return ["일정"]


def _canonical_notice_semester_pattern(query: str, query_family: str) -> str:
    if query_family != "academic_schedule":
        return ""
    query_text = query or ""
    if "1학기" in query_text or "1 학기" in query_text:
        return "%2026년 1학기%" if "26" in query_text or "2026" in query_text else "%1학기%"
    if "2학기" in query_text or "2 학기" in query_text:
        return "%2026년 2학기%" if "26" in query_text or "2026" in query_text else "%2학기%"
    # 졸업식/학위수여식 쿼리: 전기 학위 수여식 chunk 우선 (2026학년도 전기 = 2027년 2월)
    if any(term in query_text for term in ("졸업식", "학위수여식", "학위 수여식")):
        return "%전기 학위 수여식%"
    return ""


def _canonical_notice_detail_terms(query_family: str) -> list[str]:
    if query_family == "course_registration":
        return [
            "수강신청 일자",
            "수강신청 일자:",
            "수강신청 및 수강정정 일정",
            "수강 신청 기간",
            "수강신청시작일자",
            "수강정정 일자",
            "수강정정",
        ]
    if query_family == "seasonal_course_registration":
        return [
            "계절수업",
            "수강신청 일자",
            "수강 신청 기간",
            "수강료",
            "개설기간",
        ]
    if query_family == "academic_schedule":
        return [
            "보강",
            "보강일정",
            "지정보강일",
            "학사일정",
            "수업일수",
            "중간시험",
            "기말시험",
            # 개강/종강/방학/졸업 관련 milestone (공백 포함 패턴)
            "개강일",
            "종강",
            "하계방학",
            "동계방학",
            "학위 수여식",
            "계절수업",
        ]
    return ["일정", "기간"]


def _rank_canonical_doc_rows(
    rows: list[Any],
    query_family: str,
    query: str,
    search_terms: list[str],
) -> list[tuple[float, Any, dict[str, Any]]]:
    ranked: list[tuple[float, Any, dict[str, Any]]] = []
    query_text = query or ""
    for row in rows:
        db_metadata = _dict_or_empty(row["metadata"])
        canonical_metadata = canonical_notice_metadata(
            {
                "title": row["title"] or "",
                "source_url": row["source_url"] or "",
                "source_type": row["source_type"] or "",
                "content_hash": row["content_hash"] or "",
            }
        )
        metadata = {**canonical_metadata, **db_metadata}
        if metadata.get("canonical_notice_family") != query_family:
            continue
        if not metadata.get("is_canonical_notice"):
            continue
        rank = _optional_float(metadata.get("canonical_source_rank")) or 99.0
        title = str(row["title"] or "")
        score = 100.0 - rank
        score += sum(6.0 for term in search_terms if term and term in title)
        if query_family == "course_registration":
            noise_terms = ("취소", "장바구니", "신입생", "편입생", "계절", "마이크로디그리")
            score -= sum(12.0 for term in noise_terms if term in title and term not in query_text)
            if re.search(r"2026학년도\s*1학기\s*수강신청\s*안내$", title):
                score += 20.0
        if query_family == "academic_schedule" and "학사일정" in title:
            score += 18.0
        ranked.append((score, row, metadata))
    ranked.sort(key=lambda item: (item[0], str(item[1]["published_at"] or "")), reverse=True)
    return ranked


def _retrieve_canonical_documents_from_database(request: RetrievalRequest) -> list[RetrievedDoc]:
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    if query_family not in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return []

    search_terms = [
        term
        for term in _build_db_search_terms(request)
        if len(term.strip()) >= 2 and term.strip() not in {"기간", "일정", "알려줘"}
    ][:4]
    if not search_terms:
        return []
    ilike_patterns = [f"%{term}%" for term in search_terms]
    source_patterns = ["%www.deu.ac.kr/www%", "%dess.deu.ac.kr%"]
    sql = """
    WITH latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        GROUP BY doc_id
    )
    SELECT
        chunks.chunk_id,
        chunks.doc_id,
        chunks.chunk_index,
        chunks.section_index,
        chunks.section_type,
        chunks.section_title,
        chunks.content,
        chunks.content_length,
        chunks.content_hash,
        document_versions.version,
        chunks.document_version_id,
        chunks.metadata AS chunk_metadata,
        documents.title,
        documents.source_url,
        documents.source_type,
        documents.department,
        documents.published_at,
        documents.metadata AS document_metadata
    FROM chunks
    JOIN documents ON documents.doc_id = chunks.doc_id
    LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
    LEFT JOIN latest_document_versions
      ON latest_document_versions.doc_id = chunks.doc_id
    WHERE (
        chunks.document_version_id IS NULL
        OR document_versions.version = latest_document_versions.latest_version
    )
      AND documents.source_type <> 'department'
      AND (
        documents.source_url ILIKE ANY(%s)
        OR documents.source_type IN ('institution', 'academic_notice', 'academic')
      )
      AND (
        documents.title ILIKE ANY(%s)
        OR chunks.section_title ILIKE ANY(%s)
        OR chunks.content ILIKE ANY(%s)
      )
    ORDER BY
      CASE WHEN documents.source_url ILIKE ANY(%s) THEN 0 ELSE 1 END,
      documents.published_at DESC NULLS LAST,
      chunks.chunk_index ASC
    LIMIT 5
    """
    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    sql,
                    (
                        source_patterns,
                        ilike_patterns,
                        ilike_patterns,
                        ilike_patterns,
                        source_patterns,
                    ),
                )
                rows = cur.fetchall()
    except psycopg2.Error:
        return []

    docs: list[RetrievedDoc] = []
    for row in rows:
        document_metadata = _dict_or_empty(row["document_metadata"])
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=0.95,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "canonical_source_supplement",
                    "canonical_source_supplement": True,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return docs


def _prepend_unique_docs(prefix_docs: list[RetrievedDoc], docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    seen: set[str] = set()
    merged: list[RetrievedDoc] = []
    for doc in [*prefix_docs, *docs]:
        key = doc.chunk_id or f"{doc.doc_id}:{doc.metadata.get('chunk_index')}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(doc)
    return merged


def merge_retrieval_candidates(
    lexical_docs: list[RetrievedDoc],
    vector_docs: list[RetrievedDoc],
) -> list[RetrievalCandidate]:
    """Merge lexical and vector candidates by chunk_id.

    Chunk-level dedupe happens here. Document-level dedupe stays in select_topk.
    """
    candidates: dict[str, RetrievalCandidate] = {}

    for rank, doc in enumerate(lexical_docs, start=1):
        rrf_score = _rrf_score(rank)
        lexical_score = _optional_float(doc.metadata.get("lexical_norm_score")) or doc.score
        candidates[doc.chunk_id] = RetrievalCandidate(
            chunk_id=doc.chunk_id,
            doc_id=doc.doc_id,
            document=doc,
            lexical_score=lexical_score,
            vector_score=_optional_float(doc.metadata.get("vector_score")),
            rrf_score=rrf_score,
            final_score=rrf_score,
        )

    for rank, doc in enumerate(vector_docs, start=1):
        previous = candidates.get(doc.chunk_id)
        vector_score = _optional_float(doc.metadata.get("vector_score")) or doc.score
        vector_rrf_score = _rrf_score(rank)
        if previous is None:
            candidates[doc.chunk_id] = RetrievalCandidate(
                chunk_id=doc.chunk_id,
                doc_id=doc.doc_id,
                document=doc,
                lexical_score=_optional_float(doc.metadata.get("lexical_norm_score"))
                or _optional_float(doc.metadata.get("lexical_score")),
                vector_score=vector_score,
                rrf_score=vector_rrf_score,
                final_score=vector_rrf_score,
            )
            continue

        rrf_score = previous.rrf_score + vector_rrf_score
        metadata = {
            **previous.document.metadata,
            "lexical_score": previous.lexical_score,
            "vector_score": vector_score,
            "rrf_score": rrf_score,
            "final_score": rrf_score,
            "search_mode": "hybrid_rrf",
        }
        candidates[doc.chunk_id] = RetrievalCandidate(
            chunk_id=previous.chunk_id,
            doc_id=previous.doc_id,
            document=previous.document.model_copy(update={"metadata": metadata}),
            lexical_score=previous.lexical_score,
            vector_score=vector_score,
            rrf_score=rrf_score,
            final_score=rrf_score,
        )

    scored_candidates = _apply_hybrid_final_scores(list(candidates.values()))
    return sorted(
        scored_candidates,
        key=lambda candidate: (candidate.final_score, candidate.rrf_score),
        reverse=True,
    )


def _apply_hybrid_final_scores(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    lexical_max = max((candidate.lexical_score or 0.0 for candidate in candidates), default=0.0)
    vector_max = max((candidate.vector_score or 0.0 for candidate in candidates), default=0.0)
    mode = _hybrid_score_mode()
    lexical_weight = _float_env(_HYBRID_LEXICAL_WEIGHT_ENV_VAR, _DEFAULT_HYBRID_LEXICAL_WEIGHT)
    vector_weight = _float_env(_HYBRID_VECTOR_WEIGHT_ENV_VAR, _DEFAULT_HYBRID_VECTOR_WEIGHT)
    srrf_scores = _srrf_scores(candidates) if mode == "srrf" else {}
    weight_sum = max(lexical_weight + vector_weight, 0.000001)
    lexical_weight = lexical_weight / weight_sum
    vector_weight = vector_weight / weight_sum

    scored: list[RetrievalCandidate] = []
    for candidate in candidates:
        lexical_norm = _normalized_score(candidate.lexical_score, lexical_max)
        vector_norm = _normalized_score(candidate.vector_score, vector_max)
        if mode == "max":
            final_score = max(lexical_norm, vector_norm)
        elif mode == "rrf":
            final_score = candidate.rrf_score
        elif mode == "srrf":
            final_score = srrf_scores.get(candidate.chunk_id, 0.0)
        else:
            # vector_score가 없는 lexical-only 문서는 유효 weight만으로 정규화
            if candidate.vector_score is None and candidate.lexical_score is not None:
                final_score = lexical_norm
            elif candidate.lexical_score is None and candidate.vector_score is not None:
                final_score = vector_norm
            else:
                final_score = lexical_norm * lexical_weight + vector_norm * vector_weight
        adjustment = _hybrid_relevance_adjustment(candidate)
        final_score = max(final_score + float(adjustment["bonus"]) - float(adjustment["penalty"]), 0.0)

        metadata = {
            **candidate.document.metadata,
            "lexical_score": candidate.lexical_score,
            "vector_score": candidate.vector_score,
            "hybrid_lexical_norm_score": lexical_norm,
            "hybrid_vector_norm_score": vector_norm,
            "rrf_score": candidate.rrf_score,
            "srrf_score": srrf_scores.get(candidate.chunk_id) if mode == "srrf" else None,
            "srrf_beta": _srrf_beta() if mode == "srrf" else None,
            "final_score": final_score,
            "hybrid_adjustment": adjustment,
            "hybrid_score_mode": mode,
            "hybrid_lexical_weight": lexical_weight,
            "hybrid_vector_weight": vector_weight,
            "search_mode": "hybrid",
        }
        scored.append(
            RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                doc_id=candidate.doc_id,
                document=candidate.document.model_copy(update={"metadata": metadata}),
                lexical_score=candidate.lexical_score,
                vector_score=candidate.vector_score,
                rrf_score=candidate.rrf_score,
                final_score=final_score,
                search_mode="hybrid",
            )
        )
    return scored


def _candidates_to_retrieved_docs(
    candidates: list[RetrievalCandidate],
    request: RetrievalRequest,
) -> list[RetrievedDoc]:
    limit = max(request.top_k or _DEFAULT_TOP_K, (request.top_k or _DEFAULT_TOP_K) * 3)
    docs: list[RetrievedDoc] = []
    for candidate in candidates[:limit]:
        metadata = {
            **candidate.document.metadata,
            "strategy": "hybrid",
            "search_mode": candidate.search_mode,
            "lexical_score": candidate.lexical_score,
            "vector_score": candidate.vector_score,
            "rrf_score": candidate.rrf_score,
            "srrf_score": candidate.document.metadata.get("srrf_score"),
            "srrf_beta": candidate.document.metadata.get("srrf_beta"),
            "final_score": candidate.final_score,
        }
        docs.append(
            candidate.document.model_copy(
                update={
                    "score": candidate.final_score,
                    "metadata": metadata,
                }
            )
        )
    return docs


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _srrf_scores(candidates: list[RetrievalCandidate], k: int = 60) -> dict[str, float]:
    beta = _srrf_beta()
    lexical_ranks = _soft_ranks(
        [(candidate.chunk_id, candidate.lexical_score) for candidate in candidates],
        beta,
    )
    vector_ranks = _soft_ranks(
        [(candidate.chunk_id, candidate.vector_score) for candidate in candidates],
        beta,
    )
    scores: dict[str, float] = {}
    for candidate in candidates:
        score = 0.0
        lexical_rank = lexical_ranks.get(candidate.chunk_id)
        vector_rank = vector_ranks.get(candidate.chunk_id)
        if lexical_rank is not None:
            score += 1.0 / (k + lexical_rank)
        if vector_rank is not None:
            score += 1.0 / (k + vector_rank)
        scores[candidate.chunk_id] = score
    return scores


def _soft_ranks(items: list[tuple[str, float | None]], beta: float) -> dict[str, float]:
    scored_items = [(chunk_id, score) for chunk_id, score in items if score is not None]
    ranks: dict[str, float] = {}
    for chunk_id, score in scored_items:
        rank = 0.5
        for _, other_score in scored_items:
            rank += _sigmoid(beta * (other_score - score))
        ranks[chunk_id] = rank
    return ranks


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_value = math.exp(-value) if value < 700 else 0.0
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value) if value > -700 else 0.0
    return exp_value / (1.0 + exp_value)


def _hybrid_score_mode() -> str:
    mode = os.getenv(_HYBRID_SCORE_MODE_ENV_VAR, "weighted").strip().lower()
    return mode if mode in {"weighted", "max", "rrf", "srrf"} else "weighted"


def _srrf_beta() -> float:
    return _float_env(_HYBRID_SRRF_BETA_ENV_VAR, _DEFAULT_HYBRID_SRRF_BETA)


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if math.isfinite(value) and value >= 0 else default


def _normalized_score(value: float | None, max_value: float) -> float:
    if value is None or max_value <= 0:
        return 0.0
    return max(min(value / max_value, 1.0), 0.0)


def _hybrid_relevance_adjustment(candidate: RetrievalCandidate) -> dict[str, float | list[str]]:
    doc = candidate.document
    metadata = doc.metadata or {}
    keywords = [str(value).lower() for value in metadata.get("keywords") or [] if value]
    strong_from_features = [str(value).lower() for value in metadata.get("strong_terms") or [] if value]
    required_terms = [str(value).lower() for value in metadata.get("required_terms") or [] if value]
    query_family = str(metadata.get("query_family") or "general")
    strong_terms = [
        term
        for term in [*strong_from_features, *keywords]
        if len(term) >= 2 and term not in _HYBRID_GENERIC_TERMS and not (len(term) == 1 and not term.isdigit())
    ]
    title = (doc.title or "").lower()
    content = (doc.content or "").lower()
    source = (doc.source or "").lower()
    query_text = str(metadata.get("query") or "").lower()
    source_type = str(metadata.get("source_type") or "").lower()
    section_type = str(metadata.get("section_type") or "").lower()
    content_length = _safe_int(metadata.get("content_length"), len(doc.content or ""))
    explicit_notice_query = _is_explicit_notice_query(keywords)

    title_hits = sum(1 for term in strong_terms if term in title)
    content_hits = sum(1 for term in strong_terms if term in content)
    required_match = required_entity_match_score(required_terms, f"{title}\n{content}\n{source}")
    bonus = min(title_hits * 0.10 + content_hits * 0.035, 0.30)
    if required_match > 0:
        bonus += min(required_match * 0.25, 0.25)
    if candidate.lexical_score and title_hits:
        bonus += 0.08
    if candidate.lexical_score and candidate.vector_score:
        bonus += 0.04
    title_content = f"{title} {content}"
    if query_family == "campus_address" and any(term in title_content for term in ("가야 캠퍼스", "찾아오시는 길", "캠퍼스안내")):
        bonus += 0.75
        if "가야 캠퍼스" in title and "campus" in source:
            bonus += 0.35
    if query_family == "building_location" and any(
        term in title_content
        for term in ("정보공학관", "건물", "건물번호", "캠퍼스맵", "층", "찾아오시는 길", "가야 캠퍼스", "복지문화시설")
    ):
        bonus += 0.28
        if any(term in title for term in ("캠퍼스맵", "찾아오시는 길", "가야 캠퍼스", "복지문화시설")):
            bonus += 0.35
    if query_family == "welfare_facility" and any(term in title_content for term in ("복지문화시설", "편의·복지", "학생식당", "헌혈의 집", "편의점")):
        bonus += 0.75
        if "복지문화시설" in title:
            bonus += 0.45
    if _is_info_engineering_cafeteria_hours_query(query_text, keywords) and _has_info_engineering_cafeteria(title_content):
        if "deu-dining-hall.do" in source:
            bonus += 1.05
        elif "운영시간" in title_content:
            bonus += 0.45
    if query_family == "department_curriculum" and any(term in f"{title} {content}" for term in ("컴퓨터공학", "이수표", "전공필수", "교육과정")):
        bonus += 0.30
        if "이수표" in title and "컴퓨터공학" in title:
            bonus += 0.40
    if query_family == "academic_schedule" and any(term in title_content for term in ("학사일정", "학사정보", "보강")):
        bonus += 0.45
        if "학사일정" in title:
            bonus += 0.45
    if query_family == "course_registration" and any(term in title_content for term in ("수강신청", "2026학년도 1학기 수강신청")):
        bonus += 0.40
        if "수강신청 안내" in title:
            bonus += 0.35
    if query_family == "seasonal_course_registration" and any(term in title_content for term in ("계절수업", "계절학기", "하계")):
        bonus += 0.70
        if "계절수업 안내" in title or "하계 계절수업" in title:
            bonus += 0.45
    if query_family == "scholarship" and "국가장학금" in title_content:
        bonus += 0.45
    if query_family == "specific_scholarship" and any(term in title_content for term in ("성적우수장학금", "성적우수장학생", "성적우수")):
        bonus += 0.85
    if query_family == "academic_admin" and any(term in title_content for term in ("휴학", "전과", "복학")):
        bonus += 0.70
    if query_family == "certificate" and any(term in title_content for term in ("제증명서", "증명서 발급", "재학증명서", "성적증명서")):
        bonus += 0.80
    if query_family == "institution_history" and any(term in title_content for term in ("연도별 연혁", "대학현황", "1960년대", "1970년대", "1980년대", "1990년대", "2000년대", "2010년대", "2020년대")):
        bonus += 0.85
    if query_family == "person_title" and any(term in title_content for term in ("역대총장", "총장")):
        bonus += 0.45

    penalty = 0.0
    reasons: list[str] = []
    relevant_static = (
        query_family in {
            "campus_address",
            "building_location",
            "welfare_facility",
            "academic_schedule",
            "department_curriculum",
            "academic_admin",
            "certificate",
            "institution_history",
            "person_title",
        }
        and any(
            term in title_content
            for term in (
                "캠퍼스맵",
                "찾아오시는 길",
                "가야 캠퍼스",
                "복지문화시설",
                "학사일정",
                "이수표",
                "제증명서",
                "휴학",
                "전과",
                "연혁",
                "역대총장",
            )
        )
    )
    if source_type in _STATIC_SOURCE_TYPES and not relevant_static:
        penalty += 0.10
        reasons.append("static_source_type")
    if any(marker in source for marker in ("index.do", "main.do", "/main", "sitemap")):
        penalty += 0.08
        reasons.append("index_or_main_url")
    if section_type == "attachment" and not explicit_notice_query and title_hits == 0:
        penalty += 0.12
        reasons.append("weak_attachment_match")
    if source_type in _NOISY_SOURCE_TYPES and not explicit_notice_query and title_hits == 0:
        penalty += 0.40
        reasons.append("noisy_source_type")
    if 0 < content_length < 120:
        penalty += 0.08
        reasons.append("short_chunk")
    ui_hits = sum(1 for term in _UI_NOISE_TERMS if term.lower() in content)
    if ui_hits >= 3:
        penalty += 0.12
        reasons.append("ui_noise")
    if required_terms and required_match == 0.0:
        penalty += 0.20
        reasons.append("missing_required_terms")
    if query_family == "building_location" and section_type == "attachment" and required_match == 0.0:
        penalty += 0.20
        reasons.append("building_query_weak_attachment")
    if query_family == "academic_schedule" and source_type in {"scholarship", "job", "external_notice", "bids"}:
        penalty += 0.35
        reasons.append("schedule_query_source_mismatch")
    if query_family in {"campus_address", "building_location", "welfare_facility"} and source_type in {"job", "scholarship", "external_notice", "bids"}:
        penalty += 0.35
        reasons.append("location_query_source_mismatch")
    if query_family == "building_location" and any(term in title for term in ("국제관광", "학과")) and not any(term in title for term in ("캠퍼스맵", "캠퍼스안내")):
        penalty += 0.35
        reasons.append("building_query_department_substring_mismatch")
    if query_family == "welfare_facility" and "캠퍼스맵" in title and "복지문화시설" not in title_content:
        penalty += 0.25
        reasons.append("welfare_query_campus_map_secondary")
    if _is_info_engineering_cafeteria_hours_query(query_text, keywords):
        if _has_info_engineering_cafeteria(title_content) and "운영시간" not in title_content and "deu-dining-hall.do" not in source:
            penalty += 0.35
            reasons.append("cafeteria_hours_missing_hours")
        if any(term in title_content for term in ("기숙사", "생활관", "dormitory")) and "정보공학관" not in title_content:
            penalty += 0.35
            reasons.append("cafeteria_hours_wrong_facility")
    if query_family == "seasonal_course_registration" and "1학기 수강신청" in title and "계절" not in title_content:
        penalty += 0.35
        reasons.append("seasonal_course_general_registration_mismatch")
    if query_family == "specific_scholarship" and "국가장학금" in title and "성적우수" not in title_content:
        penalty += 0.40
        reasons.append("specific_scholarship_wrong_scholarship_name")
    if query_family == "academic_admin" and source_type == "scholarship":
        penalty += 0.40
        reasons.append("academic_admin_scholarship_mismatch")
    if query_family == "certificate" and "이수표" in title:
        penalty += 0.35
        reasons.append("certificate_curriculum_mismatch")
    if query_family == "institution_history" and source_type in {"job", "scholarship", "external_notice", "bids", "department"}:
        penalty += 0.40
        reasons.append("institution_history_source_mismatch")
    if query_family == "department_curriculum" and any(term in title for term in ("실습실", "마이크로디그리")) and "이수표" not in title:
        penalty += 0.30
        reasons.append("curriculum_query_title_mismatch")

    return {
        "bonus": round(min(bonus, 0.50), 6),
        "penalty": round(min(penalty, 0.45), 6),
        "title_keyword_hits": float(title_hits),
        "content_keyword_hits": float(content_hits),
        "required_entity_match": round(required_match, 6),
        "reasons": reasons,
    }


def _is_info_engineering_cafeteria_hours_query(query_text: str, keywords: list[str]) -> bool:
    text = " ".join([query_text, *keywords])
    compact = re.sub(r"\s+", "", text)
    has_info_engineering = any(term in compact for term in ("정보공학관", "정보관", "23번건물", "23번"))
    has_cafeteria = any(term in compact for term in ("학생식당", "식당", "학식"))
    has_hours = any(term in compact for term in ("운영시간", "운영", "시간", "몇시", "몇시까지"))
    return has_info_engineering and has_cafeteria and has_hours


def _has_info_engineering_cafeteria(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return "정보공학관" in compact and any(term in compact for term in ("학생식당", "식당"))


def _is_explicit_notice_query(keywords: list[str]) -> bool:
    joined = " ".join(keywords)
    return any(term in joined for term in _EXPLICIT_NOTICE_TERMS)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _retrieve_documents_from_database(request: RetrievalRequest) -> list[RetrievedDoc]:
    search_terms = _build_db_search_terms(request)
    tsquery = _build_tsquery_or_expression(search_terms)
    if not search_terms:
        return []

    # TODO: Move search_text/search_vector to generated columns with a GIN index
    # in a separate migration. Keep this rollout read-only and behavior-preserving.
    ilike_patterns = [f"%{term}%" for term in search_terms]
    phrase_patterns = _build_exact_phrase_patterns(request)
    boost_patterns, has_boost_terms = _build_boost_patterns(search_terms)
    term_match_sql = " + ".join(
        ["CASE WHEN search_text ILIKE %s THEN 0.15 ELSE 0 END" for _ in ilike_patterns]
    ) or "0"
    title_match_sql = " + ".join(
        ["CASE WHEN title_text ILIKE %s THEN 0.35 ELSE 0 END" for _ in boost_patterns]
    ) or "0"
    section_match_sql = " + ".join(
        ["CASE WHEN section_text ILIKE %s THEN 0.25 ELSE 0 END" for _ in boost_patterns]
    ) or "0"
    category_bonus_sql, category_bonus_params = _category_bonus_sql(request, "source_type")

    sql = f"""
    WITH latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        GROUP BY doc_id
    ),
    latest_attachment_presence AS (
        SELECT chunks.doc_id, bool_or(chunks.section_type = 'attachment') AS has_latest_attachment
        FROM chunks
        JOIN document_versions
          ON document_versions.id = chunks.document_version_id
        JOIN latest_document_versions
          ON latest_document_versions.doc_id = chunks.doc_id
         AND latest_document_versions.latest_version = document_versions.version
        GROUP BY chunks.doc_id
    ),
    latest_attachment_versions AS (
        SELECT chunks.doc_id, max(document_versions.version) AS latest_attachment_version
        FROM chunks
        JOIN document_versions
          ON document_versions.id = chunks.document_version_id
        WHERE chunks.section_type = 'attachment'
        GROUP BY chunks.doc_id
    ),
    searchable AS (
        SELECT
            chunks.chunk_id,
            chunks.doc_id,
            chunks.chunk_index,
            chunks.section_index,
            chunks.section_type,
            chunks.section_title,
            chunks.content,
            chunks.content_length,
            chunks.content_hash,
            document_versions.version,
            chunks.document_version_id,
            chunks.metadata AS chunk_metadata,
            documents.title,
            documents.source_url,
            documents.source_type,
            documents.department,
            documents.published_at,
            documents.metadata AS document_metadata,
            coalesce(documents.title, '') AS title_text,
            coalesce(chunks.section_title, '') AS section_text,
            coalesce(chunks.content, '') AS content_text,
            coalesce(documents.title, '') || ' ' || coalesce(chunks.section_title, '') || ' ' || coalesce(chunks.content, '') AS search_text,
            to_tsvector('simple', coalesce(documents.title, '') || ' ' || coalesce(chunks.content, '')) AS search_vector
        FROM chunks
        JOIN documents ON documents.doc_id = chunks.doc_id
        LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
        LEFT JOIN latest_document_versions
          ON latest_document_versions.doc_id = chunks.doc_id
        LEFT JOIN latest_attachment_presence
          ON latest_attachment_presence.doc_id = chunks.doc_id
        LEFT JOIN latest_attachment_versions
          ON latest_attachment_versions.doc_id = chunks.doc_id
        WHERE (
            chunks.document_version_id IS NULL
            OR document_versions.version = latest_document_versions.latest_version
            OR (
                chunks.section_type = 'attachment'
                AND coalesce(latest_attachment_presence.has_latest_attachment, false) = false
                AND document_versions.version = latest_attachment_versions.latest_attachment_version
            )
        )
    """

    filter_clause, filter_params = _build_db_filter_conditions(request)
    if filter_clause:
        sql += "\n          AND " + filter_clause

    sql += f"""
          AND (
              (
                  %s <> ''
                  AND (
                      to_tsvector('simple', coalesce(documents.title, '')) @@ to_tsquery('simple', %s)
                      OR to_tsvector('simple', coalesce(chunks.section_title, '')) @@ to_tsquery('simple', %s)
                      OR to_tsvector('simple', coalesce(chunks.content, '')) @@ to_tsquery('simple', %s)
                  )
              )
              OR documents.title ILIKE ANY(%s)
              OR chunks.section_title ILIKE ANY(%s)
              OR chunks.content ILIKE ANY(%s)
          )
    ),
    score_components AS (
        SELECT
            *,
            CASE
                WHEN %s <> '' THEN ts_rank_cd(search_vector, to_tsquery('simple', %s))
                ELSE 0
            END AS ts_rank_score,
            CASE
                WHEN title_text ILIKE ANY(%s) THEN 0.8
                WHEN section_text ILIKE ANY(%s) THEN 0.6
                WHEN content_text ILIKE ANY(%s) THEN 0.35
                ELSE 0
            END AS exact_phrase_score,
            LEAST(({term_match_sql}), %s) AS term_match_score,
            LEAST(({title_match_sql}), %s) AS title_match_score,
            LEAST(({section_match_sql}), %s) AS section_match_score,
            {category_bonus_sql} AS category_bonus,
            LEAST(
                CASE WHEN search_text ~* %s THEN 1.10 ELSE 0 END
                + CASE WHEN search_text ~* %s THEN 0.55 ELSE 0 END
                + CASE WHEN title_text ~* %s THEN 0.80 ELSE 0 END
                + CASE WHEN search_text ~* %s THEN 0.35 ELSE 0 END
                + CASE WHEN search_text ~* %s THEN 0.30 ELSE 0 END
                + CASE WHEN %s AND NOT (search_text ILIKE ANY(%s)) THEN 0.45 ELSE 0 END
                + CASE WHEN char_length(content_text) < 80 THEN 0.20 ELSE 0 END,
                %s
            ) AS noise_penalty
        FROM searchable
    )
    SELECT
        chunk_id,
        doc_id,
        chunk_index,
        section_index,
        section_type,
        section_title,
        content,
        content_length,
        content_hash,
        version,
        document_version_id,
        chunk_metadata,
        title,
        source_url,
        source_type,
        department,
        published_at,
        document_metadata,
        ts_rank_score,
        exact_phrase_score,
        term_match_score,
        title_match_score,
        section_match_score,
        category_bonus,
        noise_penalty,
        (
            ts_rank_score
            + exact_phrase_score
            + term_match_score
            + title_match_score
            + section_match_score
            + category_bonus
        ) AS raw_lexical_score,
        GREATEST(
            ts_rank_score
            + exact_phrase_score
            + term_match_score
            + title_match_score
            + section_match_score
            + category_bonus
            - noise_penalty,
            0
        ) AS lexical_score,
        GREATEST(
            ts_rank_score
            + exact_phrase_score
            + term_match_score
            + title_match_score
            + section_match_score
            + category_bonus
            - noise_penalty,
            0
        ) / (
            GREATEST(
                ts_rank_score
                + exact_phrase_score
                + term_match_score
                + title_match_score
                + section_match_score
                + category_bonus
                - noise_penalty,
                0
            ) + 1
        ) AS lexical_norm_score
    FROM score_components
    """

    sql += (
        "\n    ORDER BY lexical_score DESC, published_at DESC NULLS LAST, chunk_id ASC"
        "\n    LIMIT %s"
    )

    parameters = [
        *filter_params,
        tsquery,
        tsquery,
        tsquery,
        tsquery,
        ilike_patterns,
        ilike_patterns,
        ilike_patterns,
        tsquery,
        tsquery,
        phrase_patterns,
        phrase_patterns,
        phrase_patterns,
        *ilike_patterns,
        _ILIKE_SCORE_CAP,
        *boost_patterns,
        _TITLE_MATCH_SCORE_CAP,
        *boost_patterns,
        _SECTION_MATCH_SCORE_CAP,
        *category_bonus_params,
        "\uc785\ucc30|\uad6c\ub9e4|\uc6a9\uc5ed|\uacf5\uace0\ubc88\ud638",
        "\uc804\ud654|\uc5f0\ub77d\ucc98|\ub2f4\ub2f9\ubd80\uc11c|\ub2f4\ub2f9\uc790",
        "\uc804\ud654|\uc5f0\ub77d\ucc98|\ub2f4\ub2f9\ubd80\uc11c|\ub2f4\ub2f9\uc790",
        "\ub300\ud45c \ud398\uc774\uc9c0|\ubcf8\ubb38\ubc14\ub85c\uac00\uae30|\uba54\ub274|\uc0ac\uc774\ud2b8\ub9f5|footer|navigation",
        "\uae30\uad00\uc18c\uac1c|\ubd80\uc11c\uc18c\uac1c|\uc18c\uac1c",
        has_boost_terms,
        boost_patterns,
        _NOISE_PENALTY_CAP,
        max(request.top_k or _DEFAULT_TOP_K, (request.top_k or _DEFAULT_TOP_K) * 3),
    ]

    try:
        with _open_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, tuple(parameters))
                rows = cur.fetchall()
    except psycopg2.Error:
        return []

    retrieved_docs: list[RetrievedDoc] = []
    for row in rows:
        raw_lexical_score = float(row["raw_lexical_score"] or 0.0)
        lexical_score = float(row["lexical_score"] or 0.0)
        lexical_norm_score = float(row["lexical_norm_score"] or 0.0)
        if lexical_score < _MIN_DB_SCORE:
            continue
        document_metadata = _dict_or_empty(row["document_metadata"])
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        retrieved_docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=lexical_norm_score,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "keyword_or_tsquery_ilike",
                    "ts_rank_score": float(row["ts_rank_score"] or 0.0),
                    "exact_phrase_score": float(row["exact_phrase_score"] or 0.0),
                    "term_match_score": float(row["term_match_score"] or 0.0),
                    "ilike_score": float(row["term_match_score"] or 0.0),
                    "title_match_score": float(row["title_match_score"] or 0.0),
                    "section_match_score": float(row["section_match_score"] or 0.0),
                    "category_bonus": float(row["category_bonus"] or 0.0),
                    "noise_penalty": float(row["noise_penalty"] or 0.0),
                    "raw_lexical_score": raw_lexical_score,
                    "lexical_score": lexical_score,
                    "lexical_norm_score": lexical_norm_score,
                    "vector_score": None,
                    "rrf_score": None,
                    "final_score": lexical_norm_score,
                    "source_type": row["source_type"],
                    "department": row["department"],
                    "published_at": row["published_at"],
                    "chunk_index": row["chunk_index"],
                    "section_index": row["section_index"],
                    "section_type": row["section_type"],
                    "section_title": row["section_title"],
                    "content_length": row["content_length"],
                    "content_hash": row["content_hash"],
                    "version": row["version"],
                    "document_version_id": row["document_version_id"],
                },
            )
        )
    return retrieved_docs

def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _postprocess_retrieved_docs(docs: list[RetrievedDoc], request: RetrievalRequest) -> list[RetrievedDoc]:
    docs = _filter_forbidden_source_types(docs, request)
    docs = _dedupe_retrieved_docs(docs) if _result_dedupe_enabled() else docs
    limit = request.top_k or _DEFAULT_TOP_K
    return docs[:limit]


def _filter_forbidden_source_types(docs: list[RetrievedDoc], request: RetrievalRequest) -> list[RetrievedDoc]:
    forbidden = forbidden_source_types_for_family(_request_query_family(request))
    if not forbidden:
        return docs
    filtered = [
        doc
        for doc in docs
        if str(doc.metadata.get("source_type") or "").strip().lower() not in forbidden
    ]
    return filtered if filtered else docs


def _dedupe_retrieved_docs(docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    max_per_doc = _int_env(_MAX_RESULTS_PER_DOC_ENV_VAR, _DEFAULT_MAX_RESULTS_PER_DOC)
    max_per_source = _int_env(_MAX_RESULTS_PER_SOURCE_ENV_VAR, _DEFAULT_MAX_RESULTS_PER_SOURCE)
    seen_hashes: set[str] = set()
    doc_counts: dict[str, int] = {}
    source_counts: dict[tuple[str, str], int] = {}
    canonical_group_counts: dict[str, int] = {}
    canonical_groups_with_primary = {
        str(doc.metadata.get("canonical_group") or "").strip()
        for doc in docs
        if str(doc.metadata.get("canonical_group") or "").strip()
        and (
            doc.metadata.get("is_canonical_notice")
            or doc.metadata.get("canonical_source_supplement")
            or str(doc.metadata.get("source_type") or "").strip().lower()
            in {"academic_notice", "academic", "academic_support", "institution", "notice"}
        )
    }
    deduped: list[RetrievedDoc] = []

    for doc in docs:
        content_hash = str(doc.metadata.get("content_hash") or "").strip()
        if content_hash and content_hash in seen_hashes:
            continue

        canonical_group = str(doc.metadata.get("canonical_group") or "").strip()
        source_type = str(doc.metadata.get("source_type") or "").strip().lower()
        if (
            canonical_group
            and canonical_group in canonical_groups_with_primary
            and source_type == "department"
            and not doc.metadata.get("is_canonical_notice")
            and not doc.metadata.get("canonical_source_supplement")
        ):
            continue
        # canonical supplement(학사일정 scheduleList 등)는 여러 chunk가 필요하므로 한도 완화
        is_canonical_supplement = bool(doc.metadata.get("canonical_source_supplement"))
        effective_max_per_doc = (max_per_doc * 2) if is_canonical_supplement else max_per_doc
        effective_max_per_source = (max_per_source * 2) if is_canonical_supplement else max_per_source

        if canonical_group and canonical_group_counts.get(canonical_group, 0) >= effective_max_per_source:
            continue

        doc_count = doc_counts.get(doc.doc_id, 0)
        if effective_max_per_doc > 0 and doc_count >= effective_max_per_doc:
            continue

        source_key = (_normalize_result_key(doc.title), _normalize_result_key(doc.source))
        source_count = source_counts.get(source_key, 0)
        if source_key != ("", "") and effective_max_per_source > 0 and source_count >= effective_max_per_source:
            continue

        if content_hash:
            seen_hashes.add(content_hash)
        doc_counts[doc.doc_id] = doc_count + 1
        source_counts[source_key] = source_count + 1
        if canonical_group:
            canonical_group_counts[canonical_group] = canonical_group_counts.get(canonical_group, 0) + 1
        metadata = {
            **doc.metadata,
            "result_dedupe_applied": True,
            "result_dedupe_max_per_doc": max_per_doc,
            "result_dedupe_max_per_source": max_per_source,
            "result_dedupe_canonical_group": canonical_group or None,
        }
        deduped.append(doc.model_copy(update={"metadata": metadata}))

    return deduped


def _normalize_result_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").casefold().strip()


def _result_dedupe_enabled() -> bool:
    return os.getenv(_RESULT_DEDUPE_ENV_VAR, "1").strip().lower() not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value >= 0 else default


# BM25 알고리즘을 사용하여 문서 청크에 점수를 매기는 함수
def _score_documents(
    *,
    index: BM25Index,
    query_tokens: list[str],
    request: RetrievalRequest,
) -> list[tuple[float, IndexedChunk, list[str]]]:
    scored_docs: list[tuple[float, IndexedChunk, list[str]]] = []

    for chunk in index.chunks:
        if not _matches_filters(chunk.record, request.filters):
            continue

        score = 0.0
        matched_tokens: list[str] = []
        for token in query_tokens:
            term_frequency = chunk.term_freqs.get(token, 0)
            if term_frequency == 0:
                continue
            matched_tokens.append(token)
            score += _bm25_score(
                term_frequency=term_frequency,
                document_length=chunk.length,
                average_document_length=index.average_document_length,
                document_frequency=index.document_frequencies.get(token, 0),
                total_documents=len(index.chunks),
            )

        if score > 0:
            score += _category_bonus_for_source(chunk.record.source_type, request)
            scored_docs.append((score, chunk, matched_tokens))

    scored_docs.sort(
        key=lambda item: (
            item[0],
            item[1].record.published_at or "",
            item[1].record.chunk_id,
        ),
        reverse=True,
    )
    return scored_docs

# BM25 점수 계산 함수
def _bm25_score(
    *,
    term_frequency: int,
    document_length: int,
    average_document_length: float,
    document_frequency: int,
    total_documents: int,
) -> float:
    idf = math.log(1 + ((total_documents - document_frequency + 0.5) / (document_frequency + 0.5)))
    numerator = term_frequency * (_BM25_K1 + 1)
    denominator = term_frequency + _BM25_K1 * (
        1 - _BM25_B + _BM25_B * (document_length / max(average_document_length, 1.0))
    )
    return idf * (numerator / denominator)


# BM25 점수 계산 함수 --- IGNORE ---
def _to_retrieved_docs(
    scored_docs: list[tuple[float, IndexedChunk, list[str]]],
    request: RetrievalRequest,
) -> list[RetrievedDoc]:
    retrieved_docs: list[RetrievedDoc] = []
    for score, chunk, matched_tokens in scored_docs:
        record = chunk.record
        lexical_score = round(score, 6)
        lexical_norm_score = _lexical_norm_score(lexical_score)
        category_bonus = _category_bonus_for_source(record.source_type, request)
        retrieved_docs.append(
            RetrievedDoc(
                doc_id=record.doc_id,
                chunk_id=record.chunk_id,
                content=record.content,
                score=lexical_norm_score,
                source=record.source_url or record.source_type,
                title=record.title,
                category=request.category or record.source_type,
                metadata={
                    **record.metadata,
                    **_feature_log_fields(request),
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_tokens": matched_tokens,
                    "search_mode": "file_bm25",
                    "ts_rank_score": 0.0,
                    "exact_phrase_score": 0.0,
                    "term_match_score": round(max(lexical_score - category_bonus, 0.0), 6),
                    "ilike_score": 0.0,
                    "title_match_score": 0.0,
                    "section_match_score": 0.0,
                    "category_bonus": category_bonus,
                    "noise_penalty": 0.0,
                    "raw_lexical_score": lexical_score,
                    "lexical_score": lexical_score,
                    "lexical_norm_score": lexical_norm_score,
                    "vector_score": None,
                    "rrf_score": None,
                    "final_score": lexical_norm_score,
                    "source_type": record.source_type,
                    "published_at": record.published_at,
                },
            )
        )
    return retrieved_docs

# 문서가 검색 요청의 필터 조건과 일치하는지 확인하는 함수
def _matches_filters(record: ChunkRecord, filters: dict[str, list[str]]) -> bool:
    if not filters:
        return True

    return True

# 필터의 특정 값과 실제 문서 필드 값이 일치하는지 또는 포함되는지 확인하는 함수
def _matches_any_value(actual: str | None, expected_values: list[str]) -> bool:
    if not actual:
        return False
    normalized_actual = actual.strip().lower()
    return any(
        expected.strip().lower() == normalized_actual or expected.strip().lower() in normalized_actual
        for expected in expected_values
        if expected and expected.strip()
    )

# @lru_cache를 통해 한 번만 실행되어 메모리에 저장됩니다
@lru_cache(maxsize=1)
# BM25 인덱스를 메모리에 로드하는 함수 (캐싱하여 반복 호출 시 성능 최적화)
def _load_bm25_index() -> BM25Index:
    chunk_records = _load_chunk_records()
    indexed_chunks: list[IndexedChunk] = []
    document_frequencies: dict[str, int] = {}

    for record in chunk_records:
        tokens = tuple(_TOKENIZER.tokenize(f"{record.title}\n{record.content}"))
        if not tokens:
            continue

        term_freqs: dict[str, int] = {}
        for token in tokens:
            term_freqs[token] = term_freqs.get(token, 0) + 1

        for token in term_freqs:
            document_frequencies[token] = document_frequencies.get(token, 0) + 1

        indexed_chunks.append(
            IndexedChunk(
                record=record,
                tokens=tokens,
                term_freqs=term_freqs,
                length=len(tokens),
            )
        )

    average_document_length = (
        sum(chunk.length for chunk in indexed_chunks) / len(indexed_chunks)
        if indexed_chunks
        else 0.0
    )

    return BM25Index(
        chunks=tuple(indexed_chunks),
        document_frequencies=document_frequencies,
        average_document_length=average_document_length,
    )


@lru_cache(maxsize=1)
# 청크 레코드를 디스크에서 로드하는 함수
def _load_chunk_records() -> tuple[ChunkRecord, ...]:
    base_dir = _resolve_chunk_data_dir()
    if not base_dir.exists():
        return ()

    records: list[ChunkRecord] = []
    for file_path in sorted(base_dir.rglob("*.json")):
        with file_path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            records.append(
                ChunkRecord(
                    chunk_id=str(item.get("chunk_id", "")),
                    doc_id=str(item.get("doc_id", "")),
                    title=str(item.get("title", "")),
                    content=str(item.get("content", "")),
                    source_type=str(item.get("source_type", "")),
                    source_url=str(item.get("source_url", "")),
                    published_at=item.get("published_at"),
                    department=item.get("department"),
                    metadata={
                        "chunk_index": item.get("chunk_index"),
                        "content_length": item.get("content_length"),
                        "content_hash": item.get("content_hash"),
                        "version": item.get("version"),
                    },
                )
            )

    return tuple(records)

# 청크 데이터 디렉토리를 환경 변수 또는 기본 경로에서 결정하는 함수
def _resolve_chunk_data_dir() -> Path:
    configured_path = os.getenv(_CHUNK_ENV_VAR)
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "crawler" / "crawler" / "data" / "rag_ready" / "chunks"
