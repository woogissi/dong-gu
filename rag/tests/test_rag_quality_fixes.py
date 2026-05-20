import unittest

from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.preprocess.query_features import extract_query_features, sanitize_filters
from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.context_builder import build_context
from rag.selection.reranker import rerank_documents
from rag.selection.topk_selector import select_topk_with_diagnostics


class RagQualityFixTest(unittest.TestCase):
    def test_preprocessor_preserves_building_and_curriculum_terms(self) -> None:
        state = PipelineState.from_query("컴퓨터공학과 2학년 전공필수 과목")

        QueryPreprocessor().run(state)

        features = state.metadata["query_understanding"]["query_features"]
        self.assertEqual(features["family"], "department_curriculum")
        self.assertIn("컴퓨터공학과", features["protected_terms"])
        self.assertIn("2학년", features["protected_terms"])
        self.assertIn("전공필수", state.rewritten_query)
        self.assertIn("컴퓨터공학과", " ".join(state.rewritten_queries))

    def test_query_features_classifies_building_location(self) -> None:
        features = extract_query_features("정보공학관 2층에 뭐 있어", [])

        self.assertEqual(features.family, "building_location")
        self.assertIn("정보공학관", features.protected_terms)
        self.assertIn("2층", features.protected_terms)
        self.assertIn("정보공학관", features.required_terms)

    def test_sanitize_filters_drops_invalid_department_facets(self) -> None:
        sanitized, dropped = sanitize_filters({"department": ["학과사무실", "컴퓨터공학과"]})

        self.assertEqual(sanitized, {"department": ["컴퓨터공학과"]})
        self.assertEqual(dropped[0]["reason"], "invalid_department_facet")

    def test_reranker_prefers_building_evidence_over_curriculum_attachment(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="curriculum",
                chunk_id="curriculum_1",
                title="2026학년도 교육과정",
                content="교양과정 전공 과목 학점 안내",
                score=10.0,
                metadata={"section_type": "attachment", "source_type": "academic_notice"},
            ),
            RetrievedDoc(
                doc_id="computer_office",
                chunk_id="computer_office_1",
                title="학과사무실 위치 및 연락처 | 컴퓨터공학과",
                content="컴퓨터공학과는 정보공학관(교내 건물 번호 23번) 8층에 있습니다.",
                score=4.0,
                metadata={"section_type": "body", "source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="정보공학관은 몇번 건물?",
            keywords=["정보공학관", "건물번호"],
        )

        self.assertEqual(reranked[0].doc_id, "computer_office")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["required_entity_match"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_topk_rejects_ui_noise_and_missing_required_terms(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="menu",
                chunk_id="menu_1",
                title="HOME",
                content="HOME 공유 SNS 메뉴 사이트맵 로그인 COPYRIGHT",
                score=9.0,
                metadata={
                    "required_terms": ["정보공학관"],
                    "rerank_signals": {"noise_score": 2.0, "required_entity_match": 0.0},
                },
            ),
            RetrievedDoc(
                doc_id="facility",
                chunk_id="facility_1",
                title="정보공학관 안내",
                content="정보공학관은 교내 건물 번호 23번입니다.",
                score=5.0,
                metadata={
                    "required_terms": ["정보공학관"],
                    "rerank_signals": {
                        "strong_term_match": 1.0,
                        "title_match": 0.8,
                        "required_entity_match": 1.0,
                    },
                },
            ),
        ]

        result = select_topk_with_diagnostics(docs, k=1)

        self.assertEqual(result["selected"][0].doc_id, "facility")
        self.assertIn("context_contamination", {item["reason"] for item in result["rejected_chunks"]})

    def test_context_includes_traceable_chunk_metadata(self) -> None:
        context = build_context(
            [
                RetrievedDoc(
                    doc_id="doc1",
                    chunk_id="chunk1",
                    title="정보공학관 안내",
                    source="https://example.test/doc1",
                    content="정보공학관은 23번 건물입니다.",
                    score=1.0,
                    metadata={"source_type": "department", "lexical_score": 0.8, "final_score": 0.9},
                )
            ]
        )

        self.assertIn("chunk_id: chunk1", context)
        self.assertIn("source_url: https://example.test/doc1", context)
        self.assertIn("lexical=0.8", context)


if __name__ == "__main__":
    unittest.main()
