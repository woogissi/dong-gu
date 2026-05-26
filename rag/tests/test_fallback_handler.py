import unittest

from rag.fallback.fallback_handler import handle_fallback
from rag.fallback.policy import NO_RETRIEVAL_RESULTS_MESSAGE


class FallbackHandlerTest(unittest.TestCase):
    def test_returns_specific_message_for_no_retrieval_results(self) -> None:
        answer = handle_fallback("수강신청 기간", NO_RETRIEVAL_RESULTS_MESSAGE)

        self.assertIn("관련 문서를 찾지 못했습니다", answer)
        self.assertIn("구체적으로", answer)

    def test_returns_general_message_for_other_errors(self) -> None:
        answer = handle_fallback("수강신청 기간", "provider timeout")

        self.assertIn("현재 답변을 생성하지 못했습니다", answer)
        self.assertIn("다시 시도", answer)


if __name__ == "__main__":
    unittest.main()
