"""문서 검색기 (Retriever).

- 현재는 BM25 기반 키워드 검색만 지원한다.
- 한국어 검색 성능을 위해 Kiwi 형태소 분석기를 우선 사용한다.
- 인덱스는 `crawler/crawler/data/rag_ready/chunks` 아래 JSON 청크 파일들로부터 구성된다.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rag.schemas.retrieval import RetrievalRequest
from rag.schemas.retrieved_doc import RetrievedDoc

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

_DEFAULT_TOP_K = 10
_MIN_DB_SCORE = 0.5
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
    document_frequencies: dict[str, int]
    average_document_length: float

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
            documents = _retrieve_documents_from_database(request)
            if documents:  # DB에서 검색 결과가 있으면 반환
                return documents
            if request.filters:
                relaxed_request = request.model_copy(update={"filters": {}, "category": None})
                documents = _retrieve_documents_from_database(relaxed_request)
                if documents:
                    for document in documents:
                        document.metadata["filters_relaxed"] = True
                        document.metadata["original_filters"] = request.filters
                    return documents
        except Exception:
            # DB 연결 실패 시 파일 기반 검색으로 fallback
            pass

    # 파일 기반 BM25 검색 수행
    index = _load_bm25_index()
    if not index.chunks:
        return []

    query_tokens = _build_query_tokens(request)
    if not query_tokens:
        return []

    scored_docs = _score_documents(index=index, query_tokens=query_tokens, request=request)
    return _to_retrieved_docs(scored_docs[: request.top_k or _DEFAULT_TOP_K], request)


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
    candidate_texts = [
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
    return terms[:12]


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

    document_categories = request.filters.get("document_category", [])
    if document_categories:
        conditions.append("documents.source_type = ANY(%s)")
        parameters.append(document_categories)

    departments = request.filters.get("department", [])
    if departments:
        conditions.append("documents.department = ANY(%s)")
        parameters.append(departments)

    return " AND ".join(conditions), parameters


def _retrieve_documents_from_database(request: RetrievalRequest) -> list[RetrievedDoc]:
    search_terms = _build_db_search_terms(request)
    tsquery = _build_tsquery_or_expression(search_terms)
    if not search_terms:
        return []

    ilike_patterns = [f"%{term}%" for term in search_terms]
    ilike_score_sql = " + ".join(
        ["CASE WHEN search_text ILIKE %s THEN 0.2 ELSE 0 END" for _ in ilike_patterns]
    ) or "0"

    sql = f"""
    WITH searchable AS (
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
            chunks.version,
            chunks.metadata AS chunk_metadata,
            documents.title,
            documents.source_url,
            documents.source_type,
            documents.department,
            documents.published_at,
            documents.metadata AS document_metadata,
            coalesce(documents.title, '') || ' ' || coalesce(chunks.content, '') AS search_text,
            to_tsvector('simple', coalesce(documents.title, '') || ' ' || coalesce(chunks.content, '')) AS search_vector
        FROM chunks
        JOIN documents ON documents.doc_id = chunks.doc_id
    """

    filter_clause, filter_params = _build_db_filter_conditions(request)
    if filter_clause:
        sql += "\n        WHERE " + filter_clause

    sql += f"""
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
        chunk_metadata,
        title,
        source_url,
        source_type,
        department,
        published_at,
        document_metadata,
        (
            CASE
                WHEN %s <> '' THEN ts_rank_cd(search_vector, to_tsquery('simple', %s))
                ELSE 0
            END
            + {ilike_score_sql}
        ) AS score
    FROM searchable
    WHERE (
        (%s <> '' AND search_vector @@ to_tsquery('simple', %s))
        OR search_text ILIKE ANY(%s)
    )
    """

    sql += (
        "\n    ORDER BY score DESC, published_at DESC NULLS LAST, chunk_id ASC"
        "\n    LIMIT %s"
    )

    parameters = [
        *filter_params,
        tsquery,
        tsquery,
        *ilike_patterns,
        tsquery,
        tsquery,
        ilike_patterns,
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
        score = float(row["score"] or 0.0)
        if score < _MIN_DB_SCORE:
            continue
        document_metadata = _dict_or_empty(row["document_metadata"])
        chunk_metadata = _dict_or_empty(row["chunk_metadata"])
        retrieved_docs.append(
            RetrievedDoc(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                content=row["content"],
                score=score,
                title=row["title"] or "",
                source=row["source_url"] or row["source_type"] or "",
                category=request.category or row["source_type"],
                metadata={
                    **document_metadata,
                    **chunk_metadata,
                    **request.log_fields,
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_terms": search_terms,
                    "search_mode": "keyword_or_tsquery_ilike",
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
                },
            )
        )
    return retrieved_docs

def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        retrieved_docs.append(
            RetrievedDoc(
                doc_id=record.doc_id,
                chunk_id=record.chunk_id,
                content=record.content,
                score=round(score, 6),
                source=record.source_url or record.source_type,
                title=record.title,
                category=request.category or record.source_type,
                metadata={
                    **record.metadata,
                    "strategy": request.strategy,
                    "query": request.query,
                    "keywords": request.keywords,
                    "filters": request.filters,
                    "matched_tokens": matched_tokens,
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

    document_categories = filters.get("document_category", [])
    if document_categories and record.source_type not in document_categories:
        return False

    departments = filters.get("department", [])
    if departments and not _matches_any_value(record.department, departments):
        return False

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
        with file_path.open("r", encoding="utf-8") as file:
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
