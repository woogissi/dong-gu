import unittest
from unittest import mock

from rag.pipeline import chat_pipeline as chat_pipeline_module
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.retrieval.multi_query import (
    generate_query_variants,
    reciprocal_rank_fusion,
)
from rag.schemas.retrieval import RetrievalRequest
from rag.schemas.retrieved_doc import RetrievedDoc


def _doc(chunk_id: str, *, doc_id: str | None = None, score: float = 1.0) -> RetrievedDoc:
    return RetrievedDoc(
        doc_id=doc_id or chunk_id.split("_")[0],
        chunk_id=chunk_id,
        content=f"content-{chunk_id}",
        score=score,
    )


class GenerateQueryVariantsTest(unittest.TestCase):
    def test_parses_json_array(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            return '["수강신청 기간 언제", "수강 정정 일정 안내"]'

        variants = generate_query_variants("수강신청 언제야", num=3, generate=fake_generate)
        self.assertEqual(variants, ["수강신청 기간 언제", "수강 정정 일정 안내"])

    def test_parses_numbered_and_bulleted_lines(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            return "1. 장학금 신청 방법\n- 장학 지원 절차\n* 장학금 신청 안내"

        variants = generate_query_variants("장학금 어떻게 신청해", num=5, generate=fake_generate)
        self.assertEqual(
            variants,
            ["장학금 신청 방법", "장학 지원 절차", "장학금 신청 안내"],
        )

    def test_strips_code_fence(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            return '```json\n["도서관 운영 시간", "도서관 이용 시간"]\n```'

        variants = generate_query_variants("도서관 몇시까지", num=3, generate=fake_generate)
        self.assertEqual(variants, ["도서관 운영 시간", "도서관 이용 시간"])

    def test_dedupes_against_original_and_each_other(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            # 원질의와 동일(공백/대소문자만 다름) + 상호 중복
            return "기숙사 비용\n기숙사  비용\n기숙사비 얼마"

        variants = generate_query_variants("기숙사비 얼마", num=5, generate=fake_generate)
        self.assertEqual(variants, ["기숙사 비용"])

    def test_caps_to_num(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            return "a\nb\nc\nd\ne"

        variants = generate_query_variants("질문", num=2, generate=fake_generate)
        self.assertEqual(variants, ["a", "b"])

    def test_returns_empty_on_llm_exception(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            raise RuntimeError("LLM down")

        variants = generate_query_variants("질문", num=3, generate=fake_generate)
        self.assertEqual(variants, [])

    def test_returns_empty_on_blank_response(self) -> None:
        def fake_generate(prompt, *, system_prompt=None):
            return "   \n  "

        variants = generate_query_variants("질문", num=3, generate=fake_generate)
        self.assertEqual(variants, [])

    def test_returns_empty_for_blank_query(self) -> None:
        variants = generate_query_variants("   ", num=3)
        self.assertEqual(variants, [])


class ReciprocalRankFusionTest(unittest.TestCase):
    def test_fuses_scores_and_orders_by_rrf(self) -> None:
        list_a = [_doc("a_1"), _doc("b_1"), _doc("c_1")]
        list_b = [_doc("b_1"), _doc("a_1"), _doc("d_1")]

        fused = reciprocal_rank_fusion([list_a, list_b], rrf_k=60)

        # a_1: 1/60 + 1/61, b_1: 1/61 + 1/60 → 동일. c_1: 1/62, d_1: 1/62
        # a_1, b_1이 상위 둘. 동률(a vs b)은 등장 순서로 a 먼저.
        self.assertEqual([d.chunk_id for d in fused[:2]], ["a_1", "b_1"])
        self.assertEqual(set(d.chunk_id for d in fused), {"a_1", "b_1", "c_1", "d_1"})

    def test_dedupes_same_chunk_id(self) -> None:
        list_a = [_doc("a_1"), _doc("a_1")]
        fused = reciprocal_rank_fusion([list_a], rrf_k=60)
        self.assertEqual(len(fused), 1)

    def test_truncates_to_top_k(self) -> None:
        docs = [_doc(f"x_{i}") for i in range(10)]
        fused = reciprocal_rank_fusion([docs], rrf_k=60, top_k=3)
        self.assertEqual(len(fused), 3)

    def test_single_list_preserves_order(self) -> None:
        docs = [_doc("a_1"), _doc("b_1"), _doc("c_1")]
        fused = reciprocal_rank_fusion([docs], rrf_k=60)
        self.assertEqual([d.chunk_id for d in fused], ["a_1", "b_1", "c_1"])

    def test_empty_input(self) -> None:
        self.assertEqual(reciprocal_rank_fusion([], rrf_k=60), [])
        self.assertEqual(reciprocal_rank_fusion([[]], rrf_k=60), [])

    def test_writes_rrf_score_metadata(self) -> None:
        fused = reciprocal_rank_fusion([[_doc("a_1")]], rrf_k=60)
        self.assertIn("rrf_score", fused[0].metadata)
        self.assertAlmostEqual(fused[0].score, 1.0 / 60)

    def test_preserves_quality_score_separately(self) -> None:
        # doc.score는 정렬용 RRF, metadata['quality_score']는 입력 원점수(Layer-1) 최댓값.
        list_a = [_doc("shared", score=0.8), _doc("a_only", score=0.4)]
        list_b = [_doc("shared", score=0.6)]
        fused = reciprocal_rank_fusion([list_a, list_b], rrf_k=60)
        by_id = {d.chunk_id: d for d in fused}
        # RRF 점수(작은 스케일)와 quality_score(원점수 0~1) 분리 확인
        self.assertLess(by_id["shared"].score, 0.1)
        self.assertAlmostEqual(by_id["shared"].metadata["quality_score"], 0.8)
        self.assertAlmostEqual(by_id["a_only"].metadata["quality_score"], 0.4)


class _FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class MultiQueryRetrieveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = ChatPipeline()
        self.pipeline.embedder = _FakeEmbedder()
        self.base_request = RetrievalRequest(query="원질의", top_k=5)
        self.state = PipelineState.from_query("원질의")

    def _patch_retrieve(self, calls_recorder):
        def fake_retrieve(*, request):
            calls_recorder.append(request)
            return [_doc(f"{request.query}_1")]

        return mock.patch.object(chat_pipeline_module, "retrieve_documents", fake_retrieve)

    def test_multiquery_off_uses_single_query_rewrite(self) -> None:
        # 멀티쿼리 OFF(기본) → LLM 단일 rewrite 1회 + 단일 검색(fan-out 아님).
        calls: list = []
        with mock.patch.dict(
            "os.environ",
            {"RAG_MULTI_QUERY_ENABLED": "0", "RAG_SINGLE_QUERY_REWRITE_ENABLED": "1"},
        ), self._patch_retrieve(calls), mock.patch.object(
            chat_pipeline_module, "generate_query_variants", return_value=["재작성"]
        ) as gen:
            self.pipeline._multi_query_retrieve(self.base_request, self.state)

        self.assertEqual(len(calls), 1)  # 검색은 단 1회
        gen.assert_called_once_with("원질의", num=1)
        # 벡터는 원질의 임베딩 유지 → rewrite 재임베딩 호출 없음(검색 벡터 비결정성 제거)
        self.assertEqual(self.pipeline.embedder.calls, [])
        applied = calls[0].query_variants  # rewrite는 어휘 검색 variants로만 주입
        self.assertIn("재작성", applied)
        meta = self.state.metadata["single_query_rewrite"]
        self.assertTrue(meta["applied"])
        self.assertFalse(meta["revectorized"])
        self.assertEqual(meta["generated"], ["재작성"])

    def test_rewrite_off_runs_plain_single_search(self) -> None:
        # 멀티쿼리 OFF + rewrite OFF → 원질의 그대로 단일 검색, LLM 호출 없음.
        calls: list = []
        with mock.patch.dict(
            "os.environ",
            {"RAG_MULTI_QUERY_ENABLED": "0", "RAG_SINGLE_QUERY_REWRITE_ENABLED": "0"},
        ), self._patch_retrieve(calls), mock.patch.object(
            chat_pipeline_module, "generate_query_variants"
        ) as gen:
            self.pipeline._multi_query_retrieve(self.base_request, self.state)

        self.assertEqual(len(calls), 1)
        gen.assert_not_called()

    def test_rewrite_empty_falls_back_to_single(self) -> None:
        # rewrite 빈 결과 → 원질의 단일 검색(무회귀).
        calls: list = []
        with mock.patch.dict(
            "os.environ",
            {"RAG_MULTI_QUERY_ENABLED": "0", "RAG_SINGLE_QUERY_REWRITE_ENABLED": "1"},
        ), self._patch_retrieve(calls), mock.patch.object(
            chat_pipeline_module, "generate_query_variants", return_value=[]
        ):
            self.pipeline._multi_query_retrieve(self.base_request, self.state)

        self.assertEqual(len(calls), 1)
        self.assertFalse(self.state.metadata["single_query_rewrite"]["applied"])

    def test_enabled_fans_out_per_query(self) -> None:
        calls: list = []
        with mock.patch.dict("os.environ", {"RAG_MULTI_QUERY_ENABLED": "1", "RAG_MULTI_QUERY_NUM": "2"}), \
                self._patch_retrieve(calls), \
                mock.patch.object(
                    chat_pipeline_module,
                    "generate_query_variants",
                    return_value=["변형1", "변형2"],
                ):
            fused = self.pipeline._multi_query_retrieve(self.base_request, self.state)

        # 원질의 + 변형 2개 = 3회 검색, 변형 2개에 대해서만 임베딩
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.pipeline.embedder.calls, ["변형1", "변형2"])
        self.assertTrue(fused)
        meta = self.state.metadata["multi_query"]
        self.assertEqual(meta["generated"], ["변형1", "변형2"])
        self.assertEqual(meta["query_count"], 3)
        self.assertFalse(meta["fell_back_to_single"])

    def test_empty_variants_fall_back_to_single(self) -> None:
        calls: list = []
        with mock.patch.dict("os.environ", {"RAG_MULTI_QUERY_ENABLED": "1"}), \
                self._patch_retrieve(calls), \
                mock.patch.object(
                    chat_pipeline_module, "generate_query_variants", return_value=[]
                ):
            self.pipeline._multi_query_retrieve(self.base_request, self.state)

        self.assertEqual(len(calls), 1)
        self.assertTrue(self.state.metadata["multi_query"]["fell_back_to_single"])

    def test_no_embedder_falls_back_to_single(self) -> None:
        calls: list = []
        self.pipeline.embedder = None
        with mock.patch.dict("os.environ", {"RAG_MULTI_QUERY_ENABLED": "1"}), \
                self._patch_retrieve(calls), \
                mock.patch.object(chat_pipeline_module, "generate_query_variants") as gen:
            self.pipeline._multi_query_retrieve(self.base_request, self.state)

        self.assertEqual(len(calls), 1)
        gen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
