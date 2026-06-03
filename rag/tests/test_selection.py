import unittest

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.topk_selector import select_topk, select_topk_with_diagnostics


class TopKSelectorTest(unittest.TestCase):
    def test_select_topk_deduplicates_by_doc_id(self) -> None:
        docs = [
            RetrievedDoc(doc_id="a", chunk_id="a_1", content="first", score=3.0),
            RetrievedDoc(doc_id="a", chunk_id="a_2", content="second", score=2.0),
            RetrievedDoc(doc_id="b", chunk_id="b_1", content="third", score=1.0),
        ]

        selected = select_topk(docs, k=2)

        self.assertEqual([doc.chunk_id for doc in selected], ["a_1", "b_1"])

    def test_select_topk_preserves_strong_match_before_static_noise(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="static",
                chunk_id="static_1",
                title="HOME",
                content="본문 바로가기 사이트맵 로그인 회원가입 more sns",
                score=5.0,
                metadata={
                    "source_type": "static",
                    "rerank_signals": {"noise_score": 0.0},
                },
            ),
            RetrievedDoc(
                doc_id="facility",
                chunk_id="facility_1",
                title="정보공학관 위치",
                content="정보공학관 위치와 연락처 안내",
                score=4.0,
                metadata={
                    "source_type": "facility",
                    "rerank_signals": {"strong_term_match": 0.8, "title_match": 0.6},
                },
            ),
        ]

        selected = select_topk(docs, k=1)

        self.assertEqual(selected[0].doc_id, "facility")

    def test_select_topk_limits_source_type_monopoly_when_alternative_exists(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="notice_a",
                chunk_id="notice_a_1",
                title="기숙사 모집 안내 A",
                content="기숙사 신청기간 안내",
                score=10.0,
                metadata={"source_type": "dormitory", "rerank_signals": {"title_match": 0.8}},
            ),
            RetrievedDoc(
                doc_id="notice_b",
                chunk_id="notice_b_1",
                title="기숙사 모집 안내 B",
                content="기숙사 신청기간 안내",
                score=9.0,
                metadata={"source_type": "dormitory", "rerank_signals": {"title_match": 0.8}},
            ),
            RetrievedDoc(
                doc_id="notice_c",
                chunk_id="notice_c_1",
                title="기숙사 모집 안내 C",
                content="기숙사 신청기간 안내",
                score=8.0,
                metadata={"source_type": "dormitory", "rerank_signals": {"title_match": 0.8}},
            ),
            RetrievedDoc(
                doc_id="academic",
                chunk_id="academic_1",
                title="학사 공지 기숙사 신청",
                content="기숙사 신청 일정 안내",
                score=7.0,
                metadata={"source_type": "academic_notice", "rerank_signals": {"title_match": 0.7}},
            ),
        ]

        result = select_topk_with_diagnostics(docs, k=3)

        self.assertEqual([doc.doc_id for doc in result["selected"]], ["notice_a", "notice_b", "academic"])
        self.assertTrue(any(item["reason"] == "source_type_diversity" for item in result["rejected_chunks"]))

    def test_content_match_rescues_high_family_boost_doc(self) -> None:
        """제목 매칭이 없어도 본문 매칭(content_match>=0.3)이 있으면 contamination에서 구제(G034).

        '학생식당 위치' ↔ 제목 '교내식당'으로 title_match=0이지만 본문에 답이 담긴 경우.
        """
        gold = RetrievedDoc(
            doc_id="dining",
            chunk_id="dining_1",
            title="교내식당 | 편의·복지 | 대학생활",
            content="학생식당 위치와 운영시간 안내. 정보공학관 2층.",
            score=8.0,
            metadata={
                "source_type": "static",
                "rerank_signals": {
                    "title_match": 0.0,
                    "section_title_match": 0.0,
                    "strong_term_match": 0.1,
                    "exact_query_match": 0.0,
                    "query_family_boost": 2.9,
                    "content_match": 0.4,
                    "noise_score": 1.2,
                },
            },
        )
        other = RetrievedDoc(
            doc_id="other",
            chunk_id="other_1",
            title="복지문화시설",
            content="복지문화시설 안내",
            score=6.0,
            metadata={"source_type": "static", "rerank_signals": {"content_match": 0.2, "strong_term_match": 0.1}},
        )

        result = select_topk_with_diagnostics([gold, other], k=3)

        self.assertIn("dining", [doc.doc_id for doc in result["selected"]], "본문 매칭 정답 페이지가 선택돼야 한다")
        self.assertFalse(
            any(item["doc_id"] == "dining" and item["reason"] == "context_contamination" for item in result["rejected_chunks"]),
            "content_match가 있는 정답은 contamination으로 탈락하면 안 된다",
        )


if __name__ == "__main__":
    unittest.main()
