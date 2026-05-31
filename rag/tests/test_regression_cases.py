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
from rag.retrieval.source_policy import (
    allowed_source_types_for_values,
    forbidden_source_types_for_family,
    DORMITORY_FOREIGN_QUERY_TERMS,
)
from rag.retrieval.retriever import (
    _filter_forbidden_source_types,
    _apply_section_priority_for_curriculum,
)
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
        # exchange가 dormitory 금지 목록에 추가됐는지 확인
        self.assertIn("exchange", forbidden_source_types_for_family("dormitory"))

    def _make_exchange_doc(self) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id="exchange_notice",
            chunk_id="exchange_notice_1",
            title="국제교류처 공지사항",
            content="기숙사 관련 국제교류처 안내",
            score=1.0,
            metadata={"source_type": "exchange"},
        )

    def _make_dorm_doc(self) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id="dorm_page",
            chunk_id="dorm_page_1",
            title="효민생활관 입사신청",
            content="기숙사 입사 신청방법 안내",
            score=0.8,
            metadata={"source_type": "dormitory"},
        )

    def _make_request(self, query: str, keywords: list[str], family: str) -> RetrievalRequest:
        return RetrievalRequest(
            query=query,
            keywords=keywords,
            log_fields={"query_features": {"family": family}},
        )

    def test_exchange_filtered_from_general_dormitory_retrieval(self) -> None:
        # 일반 기숙사 쿼리에서는 exchange 문서가 retrieval 단계에서 제거돼야 한다.
        docs = [self._make_exchange_doc(), self._make_dorm_doc()]
        request = self._make_request("기숙사 신청 어디서 해", ["기숙사", "신청"], "dormitory")

        result = _filter_forbidden_source_types(docs, request)

        doc_ids = [d.doc_id for d in result]
        self.assertNotIn("exchange_notice", doc_ids, "일반 기숙사 쿼리에서 exchange 문서는 필터돼야 한다")
        self.assertIn("dorm_page", doc_ids, "dormitory 문서는 남아 있어야 한다")

    def test_exchange_preserved_for_foreign_dormitory_query(self) -> None:
        # 외국인/유학생 기숙사 쿼리에서는 exchange 문서가 유지돼야 한다.
        docs = [self._make_exchange_doc(), self._make_dorm_doc()]
        request = self._make_request(
            "외국인 유학생 기숙사 신청", ["외국인", "유학생", "기숙사", "신청"], "dormitory"
        )

        result = _filter_forbidden_source_types(docs, request)

        doc_ids = [d.doc_id for d in result]
        self.assertIn("exchange_notice", doc_ids, "외국인 유학생 쿼리에서 exchange 문서는 유지돼야 한다")
        self.assertIn("dorm_page", doc_ids)

    def test_exchange_filter_only_applies_to_dormitory_family(self) -> None:
        # scholarship 쿼리에서는 exchange 문서가 필터되지 않는다.
        docs = [self._make_exchange_doc()]
        request = self._make_request("장학금 신청", ["장학금", "신청"], "scholarship")

        result = _filter_forbidden_source_types(docs, request)

        self.assertIn("exchange_notice", [d.doc_id for d in result],
                      "scholarship 쿼리에서 exchange 문서는 필터되지 않아야 한다")

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

    def _make_dept_doc(self, doc_id: str, url: str, score: float) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id=doc_id, chunk_id=f"{doc_id}_1",
            title=doc_id, content=doc_id,
            score=score, source=url,
            metadata={"source_type": "department"},
        )

    def test_section_priority_boosts_sub03_over_sub01_for_graduation(self) -> None:
        # graduation 쿼리에서 sub03(이수표) 문서가 sub01(학과소개)보다 rank1이어야 한다.
        # r018 회귀 방지: sub01_04가 raw score 높아도 sub03_01(이수표)이 rank1.
        docs = [
            self._make_dept_doc("sub01_04", "https://swcc.deu.ac.kr/computer/sub01_04.do", 0.763),
            self._make_dept_doc("sub05_04", "https://swcc.deu.ac.kr/computer/sub05_04.do", 0.748),
            self._make_dept_doc("sub01_03", "https://swcc.deu.ac.kr/computer/sub01_03.do", 0.730),
            self._make_dept_doc("sub03_01", "https://swcc.deu.ac.kr/computer/sub03_01.do", 0.710),
        ]
        request = self._make_request("컴퓨터공학과 졸업학점", ["컴퓨터공학과", "졸업학점"], "graduation")

        result = _apply_section_priority_for_curriculum(docs, request)

        self.assertEqual(result[0].doc_id, "sub03_01",
                         "sub03(이수표) 문서가 더 낮은 raw score에도 rank1이어야 한다")
        result_ids = [d.doc_id for d in result]
        self.assertGreater(result_ids.index("sub01_04"), result_ids.index("sub03_01"))
        self.assertGreater(result_ids.index("sub05_04"), result_ids.index("sub03_01"))

    def test_section_priority_applies_to_department_curriculum_family(self) -> None:
        # department_curriculum 패밀리에도 동일하게 적용돼야 한다.
        docs = [
            self._make_dept_doc("wrong_intro",  "https://dept.ac.kr/nursing/sub01_02.do", 0.750),
            self._make_dept_doc("correct_curr", "https://dept.ac.kr/nursing/sub03_01.do", 0.720),
        ]
        request = self._make_request("간호학과 전공필수", ["간호학과", "전공필수"], "department_curriculum")

        result = _apply_section_priority_for_curriculum(docs, request)

        self.assertEqual(result[0].doc_id, "correct_curr")

    def test_section_priority_inactive_for_other_families(self) -> None:
        # graduation/department_curriculum 외 패밀리에서는 원래 점수 순서를 유지한다.
        docs = [
            self._make_dept_doc("high_score", "https://dept.ac.kr/sub03_01.do", 0.800),
            self._make_dept_doc("low_score",  "https://dept.ac.kr/sub01_01.do", 0.600),
        ]
        request = self._make_request("장학금 신청", ["장학금", "신청"], "scholarship")

        result = _apply_section_priority_for_curriculum(docs, request)

        self.assertEqual(result[0].doc_id, "high_score",
                         "scholarship 패밀리에서는 원래 점수 순서를 유지해야 한다")

    def test_section_priority_preserves_non_dept_urls_unchanged(self) -> None:
        # 학과 URL 패턴 없는 문서(공식 공지)는 delta=0으로 원래 순서 유지.
        docs = [
            self._make_dept_doc("notice", "https://www.deu.ac.kr/www/deu-notice.do", 0.750),
            self._make_dept_doc("curr",   "https://swcc.deu.ac.kr/computer/sub03_01.do", 0.710),
        ]
        request = self._make_request("컴퓨터공학과 졸업학점", ["컴퓨터공학과", "졸업학점"], "graduation")

        result = _apply_section_priority_for_curriculum(docs, request)

        # sub03_01(0.710 + 0.07 = 0.780) > notice(0.750 delta=0)
        self.assertEqual(result[0].doc_id, "curr")


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
