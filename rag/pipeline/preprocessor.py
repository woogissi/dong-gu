"""Query preprocessing stage for the main RAG pipeline."""

from __future__ import annotations

from rag.pipeline.state import PipelineState
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.entity_extractor import build_filters, extract_entities, primary_category
from rag.preprocess.query_rewriter import rewrite_queries


class QueryPreprocessor:
    def run(self, state: PipelineState) -> None:
        normalized_query = normalize_query(state.original_query)
        keywords = extract_keywords(normalized_query)
        entities = extract_entities(
            query=normalized_query,
            keywords=keywords,
        )
        rewritten_queries = rewrite_queries(
            query=normalized_query,
            keywords=keywords,
            entities=entities,
        )

        state.normalized_query = normalized_query
        state.keywords = keywords
        state.entities = entities
        state.filters = build_filters(entities)
        state.category = primary_category(entities)
        state.rewritten_queries = rewritten_queries
        state.rewritten_query = rewritten_queries[-1] if rewritten_queries else normalized_query
        state.metadata["query_understanding"] = {
            "normalized_query": normalized_query,
            "keywords": keywords,
            "entities": entities,
            "filters": state.filters,
            "primary_category": state.category,
            "rewritten_queries": rewritten_queries,
        }
