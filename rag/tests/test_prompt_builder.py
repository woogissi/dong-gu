import unittest

from rag.prompt.prompt_builder import build_prompt


class PromptBuilderTest(unittest.TestCase):
    def test_build_prompt_omits_structured_evidence_when_empty(self) -> None:
        prompt = build_prompt(
            query="When is registration?",
            context="Registration is open from March 4 to March 6, 2026.",
        )

        self.assertNotIn("[구조화 근거]", prompt)
        self.assertIn("[문서]", prompt)
        self.assertIn("Registration is open", prompt)

    def test_build_prompt_adds_structured_evidence_section_and_rules(self) -> None:
        prompt = build_prompt(
            query="정보공학관 학생식당 운영시간",
            context="정보공학관 2층 학생식당 위치 안내",
            structured_evidence=(
                "- rule=cafeteria_answer; confidence=0.55; "
                "source_doc_id=welfare; missing_terms=operating_hours\n"
                "  evidence: content: 정보공학관 2층 학생식당"
            ),
        )

        self.assertIn("[구조화 근거]", prompt)
        self.assertIn("rule=cafeteria_answer", prompt)
        self.assertIn("missing_terms=operating_hours", prompt)
        self.assertIn("[문서] 본문과 충돌하면 [문서] 본문을 우선", prompt)
        self.assertIn("missing_terms에 표시된 항목은 단정하지 마세요", prompt)
        self.assertIn("규칙이 만든 부정문을 그대로 복사하지 마세요", prompt)
        self.assertIn("[문서]\n정보공학관 2층 학생식당 위치 안내", prompt)


if __name__ == "__main__":
    unittest.main()
