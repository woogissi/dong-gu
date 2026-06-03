import unittest

from rag.prompt.prompt_builder import build_prompt, build_system_prompt


class PromptBuilderTest(unittest.TestCase):
    def test_build_prompt_contains_query_and_context(self) -> None:
        prompt = build_prompt(
            query="수강신청은 언제인가요?",
            context="수강신청은 3월 4일부터 6일까지입니다.",
        )

        self.assertNotIn("[구조화 근거]", prompt)
        self.assertIn("[질문]", prompt)
        self.assertIn("[문서]", prompt)
        self.assertIn("수강신청은 3월 4일부터", prompt)

    def test_system_prompt_prefers_partial_answer_over_refusal(self) -> None:
        # 거절을 적극 유도하던 문구를 약화하고, 부분 정보라도 우선 답하도록 지시해야 한다.
        system_prompt = build_system_prompt()

        self.assertIn("일부라도", system_prompt)
        self.assertIn("완전히 무관", system_prompt)
        self.assertNotIn("답을 찾기 어려우면", system_prompt)

    def test_system_prompt_directs_concrete_value_extraction(self) -> None:
        # 날짜·시간 등 구체값이 문서에 있으면 그대로 인용하라고 지시하고, 거절을 마지막 수단으로 둔다.
        system_prompt = build_system_prompt()

        self.assertIn("그대로 인용", system_prompt)
        self.assertIn("마지막 수단", system_prompt)


if __name__ == "__main__":
    unittest.main()
