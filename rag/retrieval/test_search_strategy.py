"""검색 전략 테스트
- 검색 전략이 다양한 입력 시나리오에 대해 올바른 검색 요청을 생성하는지 검증
- 검색 요청에는 전략 유형, 카테고리, 필터, fallback 트리거 등이 포함되어야 함
- 테스트 케이스 예시:
  - 카테고리 필터가 있는 쿼리에 대해 lexical 전략이 선택되고, 적절한 필터가 적용되는지
  - 쿼리가 비어있거나 키워드/필터가 없는 경우 fallback 트리거가 추가되는지
  - 다양한 쿼리 변형과 키워드 조합에 대해 일관된 검색 요청이 생성되는지
  """

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
