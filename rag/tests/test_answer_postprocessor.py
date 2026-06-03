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

    def test_repairs_negative_answer_with_keyword_synonyms_on_vocabulary_mismatch(self) -> None:
        # 질의 어휘("심리상담")가 문서 어휘("학생상담센터/심리검사")와 겹치지 않아도
        # 동의어 확장 키워드를 매칭에 활용해 정답 문장을 고른다.
        metadata: dict[str, object] = {}
        selected_docs = [
            RetrievedDoc(
                doc_id="counsel-1",
                chunk_id="counsel-1-chunk-1",
                title="학생상담센터 안내",
                content=(
                    "학생상담센터는 학생회관 3층에 있습니다.\n"
                    "심리검사와 개인상담은 학생상담센터에서 신청 후 받을 수 있습니다."
                ),
                source="https://example.com/counsel",
            )
        ]

        repaired = repair_negative_answer_with_context(
            "심리상담 장소에 대한 관련 정보를 찾지 못했습니다.",
            metadata,
            context=(
                "[문서 1]\n"
                "title: 학생상담센터 안내\n"
                "content:\n"
                "학생상담센터는 학생회관 3층에 있습니다. 심리검사와 개인상담은 학생상담센터에서 신청 후 받을 수 있습니다."
            ),
            selected_docs=selected_docs,
            query="심리상담 어디서 받아?",
            keywords=["학생상담센터", "심리검사", "개인상담"],
        )

        self.assertNotIn("찾지 못했습니다", repaired)
        self.assertIn("학생상담센터", repaired)
        self.assertEqual(metadata["negative_answer_repair"], "selected_context_extract")

    def test_repair_snippet_strips_attachment_markup(self) -> None:
        # 첨부/이수표 청크가 repair 스니펫으로 노출될 때 [TITLE]/[ATTACHMENT]/Download
        # 같은 원본 마크업이 답변에 새지 않아야 한다(G046).
        metadata: dict[str, object] = {}
        selected_docs = [
            RetrievedDoc(
                doc_id="cur-1",
                chunk_id="cur-1-chunk-1",
                title="이수표 | 교육과정 | 컴퓨터공학과",
                content=(
                    "[TITLE] 이수표 | 교육과정 | 컴퓨터공학과 [ATTACHMENT] 원본파일 Download "
                    "컴퓨터공학과 1학년 1학기 전공필수 과목은 프로그래밍기초입니다."
                ),
                source="https://swcc.deu.ac.kr/computer/sub03_01.do",
            )
        ]

        repaired = repair_negative_answer_with_context(
            "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            metadata,
            context="[문서 1]\ncontent:\n컴퓨터공학과 전공필수 과목 안내 본문입니다. 충분히 깁니다.",
            selected_docs=selected_docs,
            query="컴퓨터공학과 전공필수",
        )

        self.assertNotIn("[TITLE]", repaired)
        self.assertNotIn("[ATTACHMENT]", repaired)
        self.assertNotIn("Download", repaired)
        self.assertEqual(metadata["negative_answer_repair"], "selected_context_extract")

    def test_irrelevant_doc_does_not_replace_negative_answer(self) -> None:
        # 학교명 등 변별력 없는 토큰만 겹친 무관 문서(예: "설립 연도" 질의에 매칭된 채용공고)는
        # "확인된 내용"으로 출력하지 않고 원본 거절문을 유지해야 한다(q022 회귀).
        metadata: dict[str, object] = {}
        selected_docs = [
            RetrievedDoc(
                doc_id="job-1",
                chunk_id="job-1-chunk-1",
                title="동의대학교 융합부품소재 핵심연구지원센터 직원 채용 공고",
                content=(
                    "[TITLE] 동의대학교 융합부품소재 핵심연구지원센터 직원 채용 공고 [BODY] "
                    "동의대학교 융합부품소재 핵심연구지원센터는 계약직 직원을 모집합니다. "
                    "입사지원서 양식을 제출해 주시기 바랍니다."
                ),
                source="https://example.com/job-posting",
            )
        ]

        repaired = repair_negative_answer_with_context(
            "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            metadata,
            context=(
                "[문서 1]\n"
                "title: 동의대학교 융합부품소재 핵심연구지원센터 직원 채용 공고\n"
                "content:\n"
                "동의대학교 융합부품소재 핵심연구지원센터는 계약직 직원을 모집합니다."
            ),
            selected_docs=selected_docs,
            query="동의대 설립 연도 알려줘",
        )

        self.assertIn("찾지 못했습니다", repaired)
        self.assertNotIn("선택된 문서 기준", repaired)
        self.assertNotIn("채용 공고", repaired)
        self.assertNotIn("negative_answer_repair", metadata)

    def test_strips_markdown_formatting(self) -> None:
        cleaned = strip_markdown_formatting("**중요**\n# 제목\n`코드`")

        self.assertNotIn("**", cleaned)
        self.assertNotIn("#", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertIn("중요", cleaned)


if __name__ == "__main__":
    unittest.main()
