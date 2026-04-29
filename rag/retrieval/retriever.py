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

_DEFAULT_TOP_K = 10
_BM25_K1 = 1.5
_BM25_B = 0.75
_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_CHUNK_ENV_VAR = "RAG_CHUNK_DATA_DIR"


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
    category_lv1: str | None
    category_lv2: str | None
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

    categories = filters.get("category", [])
    if categories:
        category_candidates = [record.category_lv1, record.category_lv2, record.source_type]
        if not any(_matches_any_value(candidate, categories) for candidate in category_candidates):
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
                    category_lv1=item.get("category_lv1"),
                    category_lv2=item.get("category_lv2"),
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
