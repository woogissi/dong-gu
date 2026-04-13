"""Keyword retrieval strategy planning for Week 3.

This module does not execute database search yet. It converts query
understanding output into a stable retrieval contract and log payload.
"""

from __future__ import annotations

from typing import Any

from rag.pipeline.state import PipelineState
from rag.schemas.retrieval import RetrievalRequest

DEFAULT_TOP_K = 10
SUPPORTED_FILTER_FIELDS = ("category", "target", "department", "time", "time_scope")
KEYWORD_STRATEGY = "lexical"

_CATEGORY_DOCUMENT_HINTS: dict[str, list[str]] = {
    "학사": ["academic_notice"],
    "수강": ["academic_notice"],
    "장학": ["notice"],
    "등록": ["notice", "academic_notice"],
    "졸업": ["academic_notice"],
    "휴학": ["academic_notice"],
    "복학": ["academic_notice"],
    "기숙사": ["dormitory"],
    "비교과": ["notice"],
    "국제": ["notice"],
}


def build_retrieval_request(state: PipelineState) -> RetrievalRequest:
    query_variants = _dedupe(
        [
            *state.rewritten_queries,
            state.rewritten_query,
            state.normalized_query,
            state.original_query,
        ]
    )
    query = query_variants[0] if query_variants else state.original_query
    filters = _normalize_filters(state.filters)
    category = state.category or _first_value(filters.get("category", []))
    top_k = state.retrieval_top_k or DEFAULT_TOP_K
    fallback_triggers = _fallback_triggers(
        query=query,
        keywords=state.keywords,
        filters=filters,
    )
    log_fields = build_strategy_log_fields(
        query=query,
        query_variants=query_variants,
        keywords=state.keywords,
        filters=filters,
        category=category,
        top_k=top_k,
        fallback_triggers=fallback_triggers,
    )

    return RetrievalRequest(
        query=query,
        query_variants=query_variants,
        keywords=_dedupe(state.keywords),
        filters=filters,
        category=category,
        strategy=KEYWORD_STRATEGY,
        top_k=top_k,
        fallback_triggers=fallback_triggers,
        log_fields=log_fields,
    )


def build_strategy_log_fields(
    *,
    query: str,
    query_variants: list[str],
    keywords: list[str],
    filters: dict[str, list[str]],
    category: str | None,
    top_k: int,
    fallback_triggers: list[str],
) -> dict[str, Any]:
    return {
        "strategy": KEYWORD_STRATEGY,
        "query": query,
        "query_variant_count": len(query_variants),
        "keywords": _dedupe(keywords),
        "filters": filters,
        "category": category,
        "document_category_hints": _CATEGORY_DOCUMENT_HINTS.get(category or "", []),
        "top_k": top_k,
        "fallback_triggers": fallback_triggers,
        "filter_rules_applied": _filter_rules_applied(filters),
    }


def _normalize_filters(filters: dict[str, list[str]]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for field in SUPPORTED_FILTER_FIELDS:
        values = filters.get(field, [])
        if values:
            normalized[field] = _dedupe(values)

    category = _first_value(normalized.get("category", []))
    if category and category in _CATEGORY_DOCUMENT_HINTS:
        normalized["document_category"] = _CATEGORY_DOCUMENT_HINTS[category]

    return normalized


def _fallback_triggers(
    *,
    query: str,
    keywords: list[str],
    filters: dict[str, list[str]],
) -> list[str]:
    triggers: list[str] = []
    if not query.strip():
        triggers.append("empty_query")
    if not keywords and not filters:
        triggers.append("insufficient_search_terms")
    if filters and not keywords:
        triggers.append("filter_only_query")
    return triggers


def _filter_rules_applied(filters: dict[str, list[str]]) -> list[str]:
    rules: list[str] = []
    for field in SUPPORTED_FILTER_FIELDS:
        if filters.get(field):
            rules.append(f"{field}_filter")
    if filters.get("document_category"):
        rules.append("category_to_document_category_hint")
    return rules


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _first_value(values: list[str]) -> str | None:
    return values[0] if values else None
