import os
import unittest

from rag.evaluation.regression_cases import (
    REGRESSION_CASES,
    selected_context_has_not_found_mismatch,
)
from rag.embedding.koe5_embedder import KoE5Embedder
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.retrieval import retriever
from rag.schemas.retrieval import RetrievalRequest
from rag.retrieval.source_policy import allowed_source_types_for_values, forbidden_source_types_for_family
from rag.schemas.retrieved_doc import RetrievedDoc


class RegressionCaseUtilityTest(unittest.TestCase):
    def test_detects_not_found_answer_despite_selected_context(self) -> None:
        result = {
            "answer": "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            "retrieval_log": {
                "retrieved_doc_count": 5,
                "selected_doc_count": 2,
            },
        }

        self.assertTrue(selected_context_has_not_found_mismatch(result))

    def test_source_policy_expands_academic_support_categories(self) -> None:
        self.assertIn("academic_support", allowed_source_types_for_values(["academic"]))
        self.assertIn("academic_support", allowed_source_types_for_values(["certificate"]))
        self.assertIn("academic_support", allowed_source_types_for_values(["휴학", "복학", "증명서"]))
        self.assertNotIn("certificate", allowed_source_types_for_values(["certificate"]))

    def test_source_policy_covers_common_service_domains(self) -> None:
        self.assertIn("library", allowed_source_types_for_values(["library"]))
        self.assertIn("institution", allowed_source_types_for_values(["shuttle"]))
        self.assertIn("academic_support", allowed_source_types_for_values(["tuition"]))
        self.assertIn("job", allowed_source_types_for_values(["career"]))
        self.assertIn("academic_support", allowed_source_types_for_values(["grade"]))
        self.assertIn("student_life", allowed_source_types_for_values(["club_activity"]))
        self.assertIn("facility", allowed_source_types_for_values(["cafeteria"]))
        self.assertIn("static", allowed_source_types_for_values(["facility"]))

    def test_source_policy_declares_hard_negative_source_types(self) -> None:
        self.assertIn("bids", forbidden_source_types_for_family("shuttle"))
        self.assertIn("scholarship", forbidden_source_types_for_family("tuition"))
        self.assertIn("external_notice", forbidden_source_types_for_family("course_registration"))
        self.assertIn("bids", forbidden_source_types_for_family("dormitory"))

    def test_keyword_quality_warning_does_not_block_otherwise_usable_results(self) -> None:
        doc = RetrievedDoc(
            doc_id="usable",
            chunk_id="usable_1",
            title="General Guide",
            content="This context is intentionally long enough to be usable. " * 5,
            source="https://example.com/usable",
            score=0.8,
            metadata={},
        )

        quality = ChatPipeline()._evaluate_retrieval_quality([doc], 1, query="unmatched query", keywords=[])

        self.assertTrue(quality["ok"])
        self.assertFalse(quality["blocking"])
        self.assertFalse(quality["diagnostic_ok"])
        self.assertEqual(quality["reason"], "")
        self.assertEqual(quality["diagnostic_reason"], "no_exact_or_strong_keyword_match")

    def test_retriever_postprocess_filters_hard_negative_sources(self) -> None:
        request = RetrievalRequest(
            query="통학버스 시간표 알려줘",
            log_fields={"query_features": {"family": "shuttle"}},
        )
        docs = [
            RetrievedDoc(
                doc_id="bid",
                chunk_id="bid_1",
                title="통학버스 운행 용역 입찰공고",
                content="입찰공고",
                score=0.9,
                metadata={"source_type": "bids"},
            ),
            RetrievedDoc(
                doc_id="notice",
                chunk_id="notice_1",
                title="시외통학버스 신청 안내",
                content="통학버스 시간표 안내",
                score=0.8,
                metadata={"source_type": "notice"},
            ),
        ]

        filtered = retriever._postprocess_retrieved_docs(docs, request)

        self.assertEqual([doc.doc_id for doc in filtered], ["notice"])

    def test_retriever_postprocess_prefers_canonical_over_department_copy(self) -> None:
        request = RetrievalRequest(
            query="수강신청 기간 알려줘",
            log_fields={"query_features": {"family": "course_registration"}},
        )
        docs = [
            RetrievedDoc(
                doc_id="central",
                chunk_id="central_1",
                title="2026학년도 1학기 수강신청 안내",
                content="수강신청 기간 안내",
                score=0.9,
                source="https://www.deu.ac.kr/www/deu-notice.do",
                metadata={
                    "source_type": "academic_notice",
                    "canonical_group": "course_registration:2026-1",
                    "is_canonical_notice": True,
                    "content_hash": "same",
                },
            ),
            RetrievedDoc(
                doc_id="dept",
                chunk_id="dept_1",
                title="2026학년도 1학기 수강신청 안내",
                content="수강신청 기간 안내",
                score=0.8,
                source="https://dept.deu.ac.kr/sub06.do",
                metadata={
                    "source_type": "department",
                    "canonical_group": "course_registration:2026-1",
                    "content_hash": "same",
                },
            ),
        ]

        filtered = retriever._postprocess_retrieved_docs(docs, request)

        self.assertEqual([doc.doc_id for doc in filtered], ["central"])

    def test_does_not_replace_negative_answer_with_context_extract(self) -> None:
        state = PipelineState.from_query("휴학 신청 방법 알려줘")
        state.keywords = ["휴학", "신청", "방법"]
        state.selected_docs = [
            RetrievedDoc(
                doc_id="leave",
                chunk_id="leave_1",
                title="휴학",
                content="가사, 군입대, 질병 휴학신청 방법\n휴학 신청은 DAP 시스템에서 신청합니다.",
                source="https://dess.deu.ac.kr/?mid=Page1",
                score=1.0,
                metadata={"source_type": "academic_support"},
            )
        ]

        repaired = ChatPipeline()._repair_negative_answer_with_context(
            "제공된 문서에서 관련 정보를 찾지 못했습니다.",
            state,
        )

        self.assertIn("찾지 못했습니다", repaired)
        self.assertNotIn("선택된 문서 기준", repaired)

    def test_person_title_list_answer_avoids_llm_not_found(self) -> None:
        state = PipelineState.from_query("동의대 역대 총장 목록")
        state.metadata["query_understanding"] = {"query_features": {"family": "person_title"}}
        state.selected_docs = [
            RetrievedDoc(
                doc_id="presidents",
                chunk_id="presidents_1",
                title="역대총장 | 총장 | DEU",
                content=(
                    "## 동의대학교 제12대 · 13대총장\n"
                    "## 한 수 환 ( 韓 洙 桓 )\n"
                    "- 2020. 8. ~ 2023. 8. 동의대학교 제12대 총장\n"
                    "- 2023. 8. ~ 동의대학교 제13대 총장"
                ),
                source="https://www.deu.ac.kr/www/former-university-presidents.do",
                score=1.0,
                metadata={"source_type": "institution"},
            )
        ]

        answer = ChatPipeline()._build_person_title_answer(state)

        self.assertIn("역대 총장", answer or "")
        self.assertIn("제12대·13대 총장", answer or "")
        self.assertIn("한수환", answer or "")
        self.assertIn("former-university-presidents", answer or "")


class LiveRegressionSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if retriever.psycopg2 is None:
            raise unittest.SkipTest("psycopg2 is not installed; live regression checks require DB access.")
        try:
            with retriever._open_db_connection() as conn:
                with conn.cursor(cursor_factory=retriever.DictCursor) as cur:
                    cur.execute("SELECT COUNT(*) AS count FROM chunks")
                    if int(cur.fetchone()["count"]) == 0:
                        raise unittest.SkipTest("RAG DB has no chunks.")
        except retriever.psycopg2.Error as exc:
            raise unittest.SkipTest(f"RAG DB connection is not available: {exc}") from exc
        cls.embedder = KoE5Embedder()

    def setUp(self) -> None:
        self.previous_rag_use_db = os.environ.get("RAG_USE_DB")
        os.environ["RAG_USE_DB"] = "1"

    def tearDown(self) -> None:
        if self.previous_rag_use_db is None:
            os.environ.pop("RAG_USE_DB", None)
        else:
            os.environ["RAG_USE_DB"] = self.previous_rag_use_db

    def test_representative_queries_select_allowed_source_types(self) -> None:
        preprocessor = QueryPreprocessor()
        pipeline = ChatPipeline()
        pipeline.embedder = self.embedder
        failures: list[str] = []

        for case in REGRESSION_CASES:
            with self.subTest(case=case["id"]):
                selected = self._selected_docs(pipeline, preprocessor, case["query"])
                self.assertGreaterEqual(len(selected), 1)

                top_source_types = {
                    str(doc.metadata.get("source_type") or "")
                    for doc in selected[:3]
                }
                titles = " ".join(doc.title or "" for doc in selected[:3])

                forbidden = top_source_types & case["forbidden_source_types"]
                if forbidden:
                    failures.append(f"{case['id']}: forbidden source types {sorted(forbidden)} in {sorted(top_source_types)}")
                if not top_source_types & case["expected_source_types"]:
                    failures.append(f"{case['id']}: expected one of {sorted(case['expected_source_types'])}, got {sorted(top_source_types)}")
                if not any(term in titles for term in case["expected_title_terms"]):
                    failures.append(f"{case['id']}: expected title terms {sorted(case['expected_title_terms'])}, got {titles[:160]}")

        if failures:
            self.fail("\n".join(failures))

    def _selected_docs(self, pipeline: ChatPipeline, preprocessor: QueryPreprocessor, query: str):
        state = PipelineState.from_query(query)
        preprocessor.run(state)
        pipeline._embed_query(state)
        pipeline._retrieve(state)
        pipeline._select_and_build_context(state)
        return state.selected_docs


if __name__ == "__main__":
    unittest.main()
