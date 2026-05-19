import unittest

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.topk_selector import select_topk


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


if __name__ == "__main__":
    unittest.main()
