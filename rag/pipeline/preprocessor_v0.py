"""질문 전처리 모듈"""

from __future__ import annotations

from rag.pipeline.state import PipelineState
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.entity_extractor import build_filters, extract_entities, primary_category
from rag.preprocess.query_rewriter import rewrite_queries_from_bundle, rewrite_query


class QueryPreprocessor:
    def run(self, state: PipelineState) -> None:
        normalized_query = normalize_query(state.original_query)
        keywords = extract_keywords(normalized_query)
        entities = extract_entities(
            query=normalized_query,
            keywords=keywords,
        )
        query_bundle = rewrite_query(
            query=normalized_query,
            keywords=keywords,
            entities=entities,
        )
        rewritten_queries = rewrite_queries_from_bundle(query_bundle, query=normalized_query)

        state.normalized_query = normalized_query
        state.keywords = keywords
        state.entities = entities
        state.filters = build_filters(entities)
        state.category = primary_category(entities)
        state.query_bundle = query_bundle.to_dict()
        state.rewritten_queries = rewritten_queries
        state.rewritten_query = query_bundle.keyword_query or normalized_query
        state.metadata["query_understanding"] = {
            "normalized_query": normalized_query,
            "query_bundle": state.query_bundle,
            "keywords": keywords,
            "entities": entities,
            "filters": state.filters,
            "primary_category": state.category,
            "rewritten_queries": rewritten_queries,
        }
