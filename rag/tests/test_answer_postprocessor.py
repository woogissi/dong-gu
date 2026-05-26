import unittest

from rag.generation.answer_postprocessor import (
    repair_negative_answer_with_context,
    strip_markdown_formatting,
)
from rag.schemas.retrieved_doc import RetrievedDoc


class AnswerPostprocessorTest(unittest.TestCase):
    def test_negative_only_answer_is_not_replaced_with_context_extract(self) -> None:
        metadata: dict[str, object] = {}

        repaired = repair_negative_answer_with_context(
            "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            metadata,
        )

        self.assertIn("찾지 못했습니다", repaired)
        self.assertNotIn("선택된 문서 기준", repaired)
        self.assertNotIn("negative_answer_repair", metadata)

    def test_replaces_negative_answer_when_selected_context_exists(self) -> None:
        metadata: dict[str, object] = {}
        selected_docs = [
            RetrievedDoc(
                doc_id="notice-1",
                chunk_id="notice-1-chunk-1",
                title="수강신청 안내",
                content="2026학년도 1학기 수강신청 기간은 2026년 2월 17일부터 2월 20일까지입니다.",
                source="https://example.com/course-registration",
            )
        ]

        repaired = repair_negative_answer_with_context(
            "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            metadata,
            context=(
                "[문서 1]\n"
                "title: 수강신청 안내\n"
                "content:\n"
                "2026학년도 1학기 수강신청 기간은 2026년 2월 17일부터 2월 20일까지입니다."
            ),
            selected_docs=selected_docs,
            query="수강신청 기간",
        )

        self.assertIn("수강신청 안내", repaired)
        self.assertIn("2026년 2월 17일", repaired)
        self.assertIn("https://example.com/course-registration", repaired)
        self.assertEqual(metadata["negative_answer_repair"], "selected_context_extract")
        self.assertEqual(metadata["negative_answer_issue_stage"], "answer_generation")

    def test_strips_markdown_formatting(self) -> None:
        cleaned = strip_markdown_formatting("**중요**\n# 제목\n`코드`")

        self.assertNotIn("**", cleaned)
        self.assertNotIn("#", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertIn("중요", cleaned)


if __name__ == "__main__":
    unittest.main()
