"""Console trace for the query preprocessing flow.

Run directly when you want to inspect how a query changes:

    python -m unittest rag.tests.test_preprocessing_trace
"""

from __future__ import annotations

import os
import unittest

from rag.pipeline.preprocessor import (
    QueryPreprocessor,
    _apply_synonym_filter,
    _extract_aho_keywords,
)
from rag.pipeline.state import PipelineState
from rag.preprocess.entity_extractor import build_filters, extract_entities
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.query_rewriter import rewrite_queries


TRACE_QUERIES = (
    "장학금 신청 방법 알려줘",
    "등록금 고지서 확인",
    "수강정정 기간 알려줘",
)


def _trace_queries() -> tuple[str, ...]:
    if os.getenv("RAG_TRACE_QUERY"):
        return (os.environ["RAG_TRACE_QUERY"],)
    return TRACE_QUERIES


class PreprocessingTraceTest(unittest.TestCase):
    def test_print_preprocessing_flow(self) -> None:
        for query in _trace_queries():
            with self.subTest(query=query):
                state = PipelineState.from_query(query)
                normalized_query = normalize_query(query)
                lexical_query = _apply_synonym_filter(normalized_query)
                aho_keywords = _extract_aho_keywords(lexical_query)
                lexical_keywords = extract_keywords(lexical_query)
                keywords = list(dict.fromkeys([*aho_keywords, *lexical_keywords]))[:12]
                entities = extract_entities(query=lexical_query, keywords=keywords)
                filters = build_filters(entities)
                rewritten_queries = rewrite_queries(
                    query=lexical_query,
                    keywords=keywords,
                    entities=entities,
                )

                QueryPreprocessor().run(state)

                understanding = state.metadata["query_understanding"]

                print("\n" + "=" * 80)
                print(f"original_query     : {state.original_query}")
                print(f"normalize_query    : {normalized_query}")
                print(f"lexical_query      : {lexical_query}")
                print(f"aho_keywords       : {aho_keywords}")
                print(f"lexical_keywords   : {lexical_keywords}")
                print(f"merged_keywords    : {keywords}")
                print(f"entities           : {entities}")
                print(f"filters            : {filters}")
                print(f"rewritten_queries  : {rewritten_queries}")
                print(f"final rewritten    : {state.rewritten_query}")
                print(f"state.metadata     : {understanding}")

                self.assertEqual(state.original_query, query)
                self.assertEqual(state.normalized_query, lexical_query)
                self.assertTrue(state.rewritten_query)


if __name__ == "__main__":
    unittest.main(verbosity=2)
