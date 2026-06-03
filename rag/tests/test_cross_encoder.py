"""Cross-encoder 가산 신호 블렌딩 테스트.

실모델을 로드하지 않도록 `rag.selection.reranker`가 import한 CE 심볼을 monkeypatch한다
(도커 테스트 규칙 준수 + 무거운 모델 다운로드 회피).
"""

import unittest
from unittest import mock

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection import reranker


def _docs() -> list[RetrievedDoc]:
    # 규칙신호상 doc_a가 doc_b보다 약간 우세하도록 키워드 일치를 차등 배치한다.
    return [
        RetrievedDoc(
            doc_id="doc_a",
            chunk_id="doc_a_1",
            title="전과 안내 공지",
            content="전과 신청 일정과 모집 공지입니다.",
            score=10.0,
            metadata={"source_type": "notice"},
        ),
        RetrievedDoc(
            doc_id="doc_b",
            chunk_id="doc_b_1",
            title="학칙 전과 규정",
            content="전과 시 이전 학과 취득학점 인정 기준은 다음과 같다.",
            score=9.0,
            metadata={"source_type": "academic"},
        ),
    ]


class CrossEncoderBlendingTest(unittest.TestCase):
    def test_disabled_flag_is_noop_and_preserves_signals(self) -> None:
        """플래그 off면 CE 경로를 타지 않고 cross_encoder_score가 없어야 한다."""
        with mock.patch.object(reranker, "cross_encoder_enabled", return_value=False), \
                mock.patch.object(reranker, "score_pairs") as score_pairs:
            reranked = reranker.rerank_documents(
                _docs(), query="전과하면 이전 학점 인정되나요", keywords=["전과", "학점", "인정"]
            )
        score_pairs.assert_not_called()
        for doc in reranked:
            self.assertNotIn("cross_encoder_score", doc.metadata["rerank_signals"])

    def test_disabled_order_matches_baseline(self) -> None:
        """플래그 off 순서 == CE 코드 도입 전 규칙신호만의 순서(결정적 보존)."""
        with mock.patch.object(reranker, "cross_encoder_enabled", return_value=False):
            order = [
                d.doc_id
                for d in reranker.rerank_documents(
                    _docs(), query="전과 학점 인정", keywords=["전과", "학점", "인정"]
                )
            ]
        # 규칙신호상 본문 키워드 일치가 강한 doc_b(규정 페이지)가 상위인 베이스라인을 고정.
        self.assertEqual(order[0], "doc_b")

    def test_enabled_blends_and_reorders(self) -> None:
        """CE가 규칙 하위 후보(doc_a)에 높은 점수를 주면 최종 순위가 역전돼야 한다."""
        def fake_score_pairs(query, texts):
            # 규칙상 하위인 doc_a(공지)에 강한 의미점수를 부여해 역전을 유도.
            return [0.95 if "모집 공지" in text else 0.05 for text in texts]

        with mock.patch.object(reranker, "cross_encoder_enabled", return_value=True), \
                mock.patch.object(reranker, "cross_encoder_top_n", return_value=20), \
                mock.patch.object(reranker, "cross_encoder_weight", return_value=10.0), \
                mock.patch.object(reranker, "score_pairs", side_effect=fake_score_pairs):
            reranked = reranker.rerank_documents(
                _docs(), query="전과하면 이전 학점 인정되나요", keywords=["전과", "학점", "인정"]
            )

        self.assertEqual(reranked[0].doc_id, "doc_a")
        winner_signals = reranked[0].metadata["rerank_signals"]
        self.assertIn("cross_encoder_score", winner_signals)
        # 0.95 * weight 10.0 = 9.5
        self.assertAlmostEqual(winner_signals["cross_encoder_score"], 9.5, places=3)

    def test_top_n_limits_ce_application(self) -> None:
        """top_n=1이면 규칙 1위만 CE를 받고, 나머지는 cross_encoder_score가 없어야 한다."""
        with mock.patch.object(reranker, "cross_encoder_enabled", return_value=True), \
                mock.patch.object(reranker, "cross_encoder_top_n", return_value=1), \
                mock.patch.object(reranker, "cross_encoder_weight", return_value=1.0), \
                mock.patch.object(reranker, "score_pairs", return_value=[0.5]):
            reranked = reranker.rerank_documents(
                _docs(), query="전과 학점 인정", keywords=["전과", "학점", "인정"]
            )
        with_ce = [d for d in reranked if "cross_encoder_score" in d.metadata["rerank_signals"]]
        self.assertEqual(len(with_ce), 1)

    def test_empty_ce_scores_is_graceful_noop(self) -> None:
        """모델 로드 실패 등으로 score_pairs가 []를 반환하면 무영향이어야 한다."""
        with mock.patch.object(reranker, "cross_encoder_enabled", return_value=True), \
                mock.patch.object(reranker, "score_pairs", return_value=[]):
            reranked = reranker.rerank_documents(
                _docs(), query="전과 학점 인정", keywords=["전과", "학점", "인정"]
            )
        for doc in reranked:
            self.assertNotIn("cross_encoder_score", doc.metadata["rerank_signals"])


class CrossEncoderModuleTest(unittest.TestCase):
    def test_enabled_flag_parsing(self) -> None:
        from rag.selection import cross_encoder

        with mock.patch.dict("os.environ", {"RAG_CROSS_ENCODER_ENABLED": "1"}):
            self.assertTrue(cross_encoder.cross_encoder_enabled())
        with mock.patch.dict("os.environ", {"RAG_CROSS_ENCODER_ENABLED": "0"}):
            self.assertFalse(cross_encoder.cross_encoder_enabled())
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(cross_encoder.cross_encoder_enabled())

    def test_score_pairs_empty_inputs(self) -> None:
        from rag.selection import cross_encoder

        self.assertEqual(cross_encoder.score_pairs("", ["a"]), [])
        self.assertEqual(cross_encoder.score_pairs("q", []), [])

    def test_score_pairs_none_model_is_graceful(self) -> None:
        from rag.selection import cross_encoder

        with mock.patch.object(cross_encoder, "get_cross_encoder", return_value=None):
            self.assertEqual(cross_encoder.score_pairs("q", ["a", "b"]), [])

    def test_score_pairs_sigmoid_normalization(self) -> None:
        from rag.selection import cross_encoder

        fake_model = mock.Mock()
        fake_model.predict.return_value = [0.0, 10.0, -10.0]
        with mock.patch.object(cross_encoder, "get_cross_encoder", return_value=fake_model):
            scores = cross_encoder.score_pairs("q", ["a", "b", "c"])
        self.assertEqual(len(scores), 3)
        self.assertAlmostEqual(scores[0], 0.5, places=3)
        self.assertGreater(scores[1], 0.99)
        self.assertLess(scores[2], 0.01)


if __name__ == "__main__":
    unittest.main()
