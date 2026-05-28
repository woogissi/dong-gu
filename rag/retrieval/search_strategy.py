"""키워드 검색
- 쿼리와 키워드, 필터를 활용하여 검색 요청을 구성
- 검색 요청에는 쿼리 변형, 키워드, 필터, 카테고리, top_k, fallback 트리거 등이 포함됨
"""

from __future__ import annotations

from typing import Any

from rag.pipeline.state import PipelineState
from rag.preprocess.query_features import extract_query_features, sanitize_filters
from rag.schemas.retrieval import RetrievalRequest

DEFAULT_TOP_K = 20
SUPPORTED_FILTER_FIELDS = ("category", "target", "department", "time", "time_scope")
KEYWORD_STRATEGY = "lexical"

# TODO: Improve category/source hints for scholarship, shuttle bus, and library
# queries separately from the vector/hybrid retrieval rollout.

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
            *(state.rewritten_queries or []),
            state.rewritten_query,
            state.normalized_query,
            state.original_query,
        ]
    )

    query = query_variants[0] if query_variants else state.original_query
    filters = _normalize_filters(state.filters)
    filters, dropped_filters = sanitize_filters(filters)
    query_features = extract_query_features(query, state.keywords)
    category = query_features.category or state.category or _first_value(filters.get("category", []))
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
        query_features=query_features.to_log_dict(),
        dropped_filters=dropped_filters,
    )

    return RetrievalRequest(
        query=query,
        query_variants=query_variants,
        keywords=_dedupe(state.keywords),
        query_vector=list(state.query_vector or []),
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
    query_features: dict[str, object] | None = None,
    dropped_filters: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "strategy": KEYWORD_STRATEGY,
        "query": query,
        "query_variant_count": len(query_variants),
        "keywords": _dedupe(keywords),
        "filters": filters,
        "category": category,
        "document_category_hints": query_features.get("source_boosts") or _CATEGORY_DOCUMENT_HINTS.get(category or "", []),
        "top_k": top_k,
        "fallback_triggers": fallback_triggers,
        "filter_rules_applied": _filter_rules_applied(filters),
        "query_features": query_features or {},
        "strong_terms": (query_features or {}).get("strong_terms", []),
        "query_family": (query_features or {}).get("family"),
        "dropped_filters": dropped_filters or [],
        "applied_boosts": query_features.get("source_boosts") if query_features else [],
        "detected_domain": query_features.get("domain") if query_features else None,
        "detected_category": query_features.get("category") if query_features else category,
        "rule_hit_names": query_features.get("rule_hit_names") if query_features else [],
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


# - TODO - 검색어가 너무 짧거나 일반적인 경우, 추가 정보를 요청하는 메시지로 대응
# - TODO - 키워드 없이 필터만 있는 경우, "키워드 없이 필터만으로는 검색이 어려울 수 있습니다. 키워드를 추가해주세요" 등의 메시지로 대응
# - TODO - 쿼리가 비어있거나 공백만 있는 경우, "검색어를 입력해주세요" 등의 메시지로 대응
# - TODO - 기타 트리거에 대해서는, "입력하신 검색어로는 결과를 찾기 어려울 수 있습니다. 검색어를 더 구체적으로 입력하거나, 키워드와 필터를 추가해주세요" 등의 일반적인 메시지로 대응 
def _fallback_triggers(
    *,
    query: str,
    keywords: list[str],
    filters: dict[str, list[str]],
) -> list[str]:
    triggers: list[str] = []
    has_keywords = bool(keywords)
    has_filters = bool(filters)
    if not query.strip():
        triggers.append("empty_query")
    if not has_keywords and not has_filters:
        triggers.append("insufficient_search_terms")
    if has_filters and not has_keywords:
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

# - 유틸 함수
# - _dedupe: 리스트에서 None과 중복을 제거하면서 순서를 유지
# - _first_value: 리스트에서 첫 번째 값을 안전하게 추출 (없으면 None 반환)
def _dedupe(values: list[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _first_value(values: list[str]) -> str | None:
    return values[0] if values else None
