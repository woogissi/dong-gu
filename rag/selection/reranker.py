"""Rule-based reranking for retrieved RAG documents."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from rag.schemas.retrieved_doc import RetrievedDoc

_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")


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
    max_base_score = max((doc.score for doc in docs), default=0.0)

    reranked: list[tuple[float, int, RetrievedDoc]] = []
    for index, doc in enumerate(docs):
        signals = _score_doc(
            doc=doc,
            query=query,
            query_tokens=query_tokens,
            keyword_tokens=keyword_tokens,
            category=category,
            filters=filters,
            max_base_score=max_base_score,
        )
        rerank_score = round(sum(signals.values()), 6)
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
    category: str | None,
    filters: dict[str, list[str]],
    max_base_score: float,
) -> dict[str, float]:
    title = doc.title or ""
    content = doc.content or ""
    title_tokens = set(_tokenize(title))
    content_tokens = set(_tokenize(content))
    full_text = f"{title}\n{content}".lower()

    base_score = _normalized_base_score(doc.score, max_base_score)
    title_match = _coverage_score(keyword_tokens, title_tokens) * 1.8
    content_match = _coverage_score(keyword_tokens, content_tokens) * 1.0
    exact_query_match = 0.8 if query.strip() and query.strip().lower() in full_text else 0.0
    category_match = _category_match_score(doc, category, filters)
    recency = _recency_score(doc.metadata.get("published_at"))

    return {
        "base_score": round(base_score, 6),
        "title_match": round(title_match, 6),
        "content_match": round(content_match, 6),
        "exact_query_match": round(exact_query_match, 6),
        "category_match": round(category_match, 6),
        "recency": round(recency, 6),
    }


def _normalized_base_score(score: float, max_base_score: float) -> float:
    if max_base_score <= 0:
        return 0.0
    return min(score / max_base_score, 1.0) * 3.0


def _coverage_score(expected_tokens: list[str], actual_tokens: set[str]) -> float:
    if not expected_tokens or not actual_tokens:
        return 0.0
    matched = sum(1 for token in expected_tokens if token in actual_tokens)
    return matched / len(expected_tokens)


def _category_match_score(
    doc: RetrievedDoc,
    category: str | None,
    filters: dict[str, list[str]],
) -> float:
    candidates = {
        _normalize_value(doc.category),
        _normalize_value(doc.metadata.get("source_type")),
        _normalize_value(doc.metadata.get("category_lv1")),
        _normalize_value(doc.metadata.get("category_lv2")),
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
    return _dedupe_tokens(_TOKEN_PATTERN.findall(text.lower()))


def _dedupe_tokens(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))


def _normalize_value(value: Any) -> str:
    return str(value or "").strip().lower()
