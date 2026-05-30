"""검색 전략 테스트
- 검색 전략이 다양한 입력 시나리오에 대해 올바른 검색 요청을 생성하는지 검증
- 검색 요청에는 전략 유형, 카테고리, 필터, fallback 트리거 등이 포함되어야 함
- 테스트 케이스 예시:
  - 카테고리 필터가 있는 쿼리에 대해 lexical 전략이 선택되고, 적절한 필터가 적용되는지
  - 쿼리가 비어있거나 키워드/필터가 없는 경우 fallback 트리거가 추가되는지
  - 다양한 쿼리 변형과 키워드 조합에 대해 일관된 검색 요청이 생성되는지
  """

import unittest
from pprint import pprint

from rag.pipeline.state import PipelineState
from rag.retrieval.search_strategy import build_retrieval_request


class SearchStrategyTest(unittest.TestCase):
    def test_builds_lexical_request_with_ranking_hints(self) -> None:
        state = PipelineState.from_query("수강신청 언제까지야?")
        state.normalized_query = "수강신청 언제까지야?"
        state.rewritten_queries = ["수강신청 언제까지야?", "수강신청 기간"]
        state.rewritten_query = "수강신청 기간"
        state.keywords = ["수강신청", "기간"]
        state.filters = {"category": ["수강"], "time": ["기간"]}
        state.category = "수강"

        self._debug_print(
            "lexical_request input_state",
            {
                "original_query": state.original_query,
                "normalized_query": state.normalized_query,
                "rewritten_query": state.rewritten_query,
                "rewritten_queries": state.rewritten_queries,
                "keywords": state.keywords,
                "filters": state.filters,
                "category": state.category,
            },
        )
        request = build_retrieval_request(state)
        self._debug_print("lexical_request output", request.model_dump())

        self.assertEqual(request.strategy, "lexical")
        self.assertEqual(request.category, "수강")
        self.assertEqual(request.filters, {})
        self.assertEqual(request.ranking_hints["category"], "수강")
        self.assertEqual(request.ranking_hints["category_values"], ["수강"])
        self.assertEqual(
            request.ranking_hints["document_category"],
            ["academic_notice", "academic_support", "department", "institution"],
        )
        self.assertEqual(request.log_fields["filters"], {})
        self.assertEqual(request.log_fields["ranking_hints"], request.ranking_hints)
        self.assertEqual(request.fallback_triggers, [])
        self.assertEqual(request.log_fields["filter_rules_applied"], [])

    def test_moves_time_filters_to_temporal_ranking_hints(self) -> None:
        state = PipelineState.from_query("2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad")
        state.normalized_query = "2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad"
        state.rewritten_query = "2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad"
        state.keywords = ["2026\ub144", "1\ud559\uae30", "\uc218\uac15\uc2e0\uccad"]
        state.filters = {"time": ["2026\ub144"], "time_scope": ["1\ud559\uae30"], "category": ["\uc218\uac15"]}
        state.category = "\uc218\uac15"

        request = build_retrieval_request(state)

        self.assertEqual(request.filters, {})
        temporal_signals = request.ranking_hints["temporal_signals"]
        self.assertEqual(temporal_signals["years"], ["2026"])
        self.assertEqual(temporal_signals["semesters"], ["1\ud559\uae30"])
        self.assertEqual(request.log_fields["temporal_signals"], temporal_signals)
        self.assertEqual(request.ranking_hints["soft_filters"]["time"], ["2026\ub144"])
        self.assertEqual(request.ranking_hints["soft_filters"]["time_scope"], ["1\ud559\uae30"])

    def test_adds_fallback_trigger_for_empty_search_terms(self) -> None:
        state = PipelineState.from_query("")

        self._debug_print(
            "fallback_request input_state",
            {
                "original_query": state.original_query,
                "normalized_query": state.normalized_query,
                "rewritten_query": state.rewritten_query,
                "rewritten_queries": state.rewritten_queries,
                "keywords": state.keywords,
                "filters": state.filters,
                "category": state.category,
            },
        )
        request = build_retrieval_request(state)
        self._debug_print("fallback_request output", request.model_dump())

        self.assertIn("empty_query", request.fallback_triggers)
        self.assertIn("insufficient_search_terms", request.fallback_triggers)


    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
