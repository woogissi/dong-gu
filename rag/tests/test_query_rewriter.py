import unittest

from rag.preprocess.query_rewriter import RewrittenQuery, rewrite_queries, rewrite_query
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState


class QueryRewriterTest(unittest.TestCase):
    def test_leave_period_does_not_add_return_process(self) -> None:
        # 반환 예시:
        # RewrittenQuery(
        #   original="휴학 언제야?",
        #   semantic_query="휴학 언제야? 기간",
        #   keyword_query="휴학 기간 일정 마감일",
        #   entity_query="휴학",
        #   intent="기간",
        #   entities=["휴학"],
        #   filters={"category": ["휴학"]},
        # )
        result = rewrite_query("휴학 언제야?", keywords=["휴학", "언제"])

        self.assertIsInstance(result, RewrittenQuery)
        self.assertEqual(result.intent, "기간")
        self.assertEqual(result.entities, ["휴학"])
        self.assertNotIn("복학절차", result.keyword_query)

    def test_leave_application_method_allows_narrow_method_terms(self) -> None:
        result = rewrite_query("휴학 신청 방법 알려줘", keywords=["휴학", "신청", "방법"])

        self.assertIn(result.intent, {"방법", "신청"})
        self.assertEqual(result.entities, ["휴학"])
        self.assertIn("절차", result.keyword_query)
        self.assertIn("제출처", result.keyword_query)
        self.assertIn("필요서류", result.keyword_query)
        self.assertNotIn("복학절차", result.keyword_query)

    def test_tuition_bill_check_does_not_force_payment_method(self) -> None:
        result = rewrite_query("등록금 고지서 확인", keywords=["등록금", "고지서", "확인"])

        self.assertEqual(result.intent, "확인")
        self.assertEqual(result.entities, ["등록금", "고지서"])
        self.assertIn("고지서", result.keyword_query)
        self.assertIn("납부금액", result.keyword_query)
        self.assertNotIn("납부방법", result.keyword_query)

    def test_scholarship_selection_result_check_expands_check_terms(self) -> None:
        result = rewrite_query("장학금 선발 결과 확인", keywords=["장학금", "선발", "결과", "확인"])

        self.assertEqual(result.intent, "확인")
        self.assertEqual(result.entities, ["장학금"])
        self.assertIn("조회", result.keyword_query)
        self.assertIn("선발결과", result.keyword_query)
        self.assertIn("지급일", result.keyword_query)

    def test_academic_notice_does_not_trigger_course_expansion_by_substring(self) -> None:
        result = rewrite_query("학사공지 어디서 봐?", keywords=["학사", "학사공지", "어디"])

        self.assertEqual(result.entities, ["학사공지"])
        self.assertNotIn("수강신청", result.keyword_query)
        self.assertNotIn("정정", result.keyword_query)
        self.assertNotIn("휴학", result.keyword_query)

    def test_rewrite_queries_starts_with_keyword_query_for_compatibility(self) -> None:
        result = rewrite_query("휴학 언제야?", keywords=["휴학", "언제"])
        variants = rewrite_queries("휴학 언제야?", keywords=["휴학", "언제"])

        self.assertEqual(variants[0], result.keyword_query)

    def test_preprocessor_stores_bundle_and_keyword_default(self) -> None:
        state = PipelineState.from_query("등록금 고지서 확인")

        QueryPreprocessor().run(state)

        self.assertEqual(state.query_bundle["intent"], "확인")
        self.assertEqual(state.rewritten_query, state.query_bundle["keyword_query"])
        self.assertNotIn("납부방법", state.rewritten_query)


if __name__ == "__main__":
    unittest.main()
