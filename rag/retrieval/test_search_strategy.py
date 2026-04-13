import unittest

from rag.pipeline.state import PipelineState
from rag.retrieval.search_strategy import build_retrieval_request


class SearchStrategyTest(unittest.TestCase):
    def test_builds_lexical_request_with_category_filter(self) -> None:
        state = PipelineState.from_query("수강신청 언제까지야?")
        state.normalized_query = "수강신청 언제까지야?"
        state.rewritten_queries = ["수강신청 언제까지야?", "수강신청 기간"]
        state.rewritten_query = "수강신청 기간"
        state.keywords = ["수강신청", "기간"]
        state.filters = {"category": ["수강"], "time": ["기간"]}
        state.category = "수강"

        request = build_retrieval_request(state)

        self.assertEqual(request.strategy, "lexical")
        self.assertEqual(request.category, "수강")
        self.assertEqual(request.filters["document_category"], ["academic_notice"])
        self.assertEqual(request.fallback_triggers, [])
        self.assertIn("category_filter", request.log_fields["filter_rules_applied"])

    def test_adds_fallback_trigger_for_empty_search_terms(self) -> None:
        state = PipelineState.from_query("")

        request = build_retrieval_request(state)

        self.assertIn("empty_query", request.fallback_triggers)
        self.assertIn("insufficient_search_terms", request.fallback_triggers)


if __name__ == "__main__":
    unittest.main()
