import unittest

from rag.prompt.prompt_builder import build_prompt


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


if __name__ == "__main__":
    unittest.main()
