import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from pprint import pprint
from unittest.mock import Mock, patch

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.retrieval import retriever
from rag.schemas.retrieved_doc import RetrievedDoc


class PipelineStageOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path.cwd() / ".test_tmp"
        temp_root.mkdir(exist_ok=True)
        self.chunk_dir = temp_root / f"chunks_{uuid.uuid4().hex}"
        self.chunk_dir.mkdir()
        os.environ["RAG_CHUNK_DATA_DIR"] = str(self.chunk_dir)
        os.environ["RAG_USE_DB"] = "0"
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()

        self._write_chunk_file(
            "academic_notice/sample.json",
            [
                {
                    "chunk_id": "notice_1_chunk_1",
                    "doc_id": "notice_1",
                    "title": "수강정정 안내",
                    "content": "수강정정 기간과 신청 방법을 안내합니다.",
                    "source_type": "academic_notice",
                    "source_url": "https://example.com/notice_1",
                    "published_at": "2026-04-10",
                    "department": "학사관리팀",
                },
                {
                    "chunk_id": "notice_2_chunk_1",
                    "doc_id": "notice_2",
                    "title": "기숙사 입사 안내",
                    "content": "기숙사 입사 일정과 준비물을 공지합니다.",
                    "source_type": "dormitory",
                    "source_url": "https://example.com/notice_2",
                    "published_at": "2026-04-11",
                    "department": "생활관",
                },
            ],
        )

    def tearDown(self) -> None:
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()
        os.environ.pop("RAG_CHUNK_DATA_DIR", None)
        os.environ.pop("RAG_USE_DB", None)
        shutil.rmtree(self.chunk_dir, ignore_errors=True)

    def test_pipeline_stage_outputs(self) -> None:
        fake_embedder = Mock()
        fake_embedder.embed_query.return_value = [0.11, 0.22, 0.33]
        pipeline = ChatPipeline()
        pipeline.embedder = fake_embedder
        state = PipelineState.from_query("수강정정 기간 알려줘")

        pipeline.preprocessor.run(state)
        self._debug_print("after_preprocessor", self._snapshot_after_preprocess(state))

        self.assertEqual(state.original_query, "수강정정 기간 알려줘")
        self.assertTrue(state.normalized_query)
        self.assertTrue(state.keywords)
        self.assertIsInstance(state.entities, dict)
        self.assertIsInstance(state.filters, dict)
        self.assertTrue(state.rewritten_query)
        self.assertIn("query_understanding", state.metadata)

        pipeline._embed_query(state)
        self._debug_print("after_embed_query", self._snapshot_after_embedding(state))

        self.assertEqual(state.query_vector, [0.11, 0.22, 0.33])
        pipeline.embedder.embed_query.assert_called_once_with(
            state.metadata["query_understanding"]["embedding_query"]
        )

        pipeline._retrieve(state)
        self._debug_print("after_retrieve", self._snapshot_after_retrieve(state))

        self.assertEqual(state.retrieval_strategy, "vector")
        self.assertEqual(state.retrieval_top_k, 20)
        self.assertIn("retrieval_request", state.metadata)
        self.assertIn("retrieval_strategy_log", state.metadata)
        self.assertEqual(state.metadata["retrieval_strategy_log"]["filters"], {})
        self.assertIn("ranking_hints", state.metadata["retrieval_strategy_log"])
        self.assertIn("temporal_signals", state.metadata["retrieval_strategy_log"])
        self.assertIn("source_boosts", state.metadata["retrieval_strategy_log"])
        self.assertEqual(
            state.metadata["retrieval_strategy_log"]["ranking_hints"],
            state.metadata["retrieval_request"]["ranking_hints"],
        )
        log_data = state.to_log_dict()
        self.assertEqual(log_data["filters"], {})
        self.assertEqual(log_data["ranking_hints"], state.metadata["retrieval_request"]["ranking_hints"])
        self.assertEqual(log_data["temporal_signals"], state.metadata["retrieval_strategy_log"]["temporal_signals"])
        self.assertGreaterEqual(len(state.retrieved_docs), 1)
        self.assertEqual(state.retrieved_docs[0].doc_id, "notice_1")
        self.assertEqual(state.retrieved_docs[0].metadata["strategy"], "vector")
        self.assertTrue(state.retrieved_docs[0].metadata["matched_tokens"])

        pipeline._select_and_build_context(state)
        self._debug_print("after_select_and_context", self._snapshot_after_select(state))

        self.assertGreaterEqual(len(state.reranked_docs), 1)
        self.assertGreaterEqual(len(state.selected_docs), 1)
        self.assertIn("rerank_score", state.reranked_docs[0].metadata)
        self.assertIn("rerank_signals", state.reranked_docs[0].metadata)
        self.assertIn("retrieved_candidate_trace", state.metadata)
        self.assertIn("reranked_candidate_trace", state.metadata)
        self.assertIn("selected_candidate_trace", state.metadata)
        self.assertIn("rejected_candidate_trace", state.metadata)
        self.assertIn("source_type", state.metadata["selected_candidate_trace"][0])
        self.assertTrue(state.context)

    def test_temporal_validation_injects_hint_when_selected_docs_do_not_match(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("2026년 1학기 수강신청")
        temporal_signals = {
            "years": ["2026"],
            "semesters": ["1학기"],
            "relative_dates": [],
            "recency_intent": False,
            "has_explicit_temporal": True,
        }
        state.metadata["retrieval_strategy_log"] = {
            "filters": {},
            "ranking_hints": {"temporal_signals": temporal_signals},
            "temporal_signals": temporal_signals,
        }
        state.metadata["retrieval_quality"] = {"ok": True, "blocking": False, "reason": "", "diagnostic_reason": ""}
        state.selected_docs = [
            RetrievedDoc(
                doc_id="course_2025",
                chunk_id="course_2025_1",
                title="2025년 2학기 수강신청 안내",
                content="2025년 2학기 수강신청 기간",
                score=1.0,
                metadata={"published_at": "2025-08-01"},
            )
        ]
        state.context = "2025년 2학기 수강신청 기간"

        validation = pipeline._validate_selected_temporal_evidence(state)

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM answer with temporal hint"
            pipeline._generate(state)

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["reason"], "missing_temporal_evidence")
        self.assertFalse(state.metadata["retrieval_quality"]["ok"])
        self.assertEqual(state.metadata["retrieval_quality"]["diagnostic_reason"], "missing_temporal_evidence")
        self.assertFalse(state.metadata.get("temporal_answer_blocked", False))
        self.assertTrue(state.metadata.get("temporal_mismatch_hint_injected"))
        mocked_generate.assert_called_once()
        self.assertIn("temporal_mismatch", state.prompt)

    def test_select_passes_hard_filters_not_raw_state_filters_to_reranker(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("장학금 신청")
        state.normalized_query = "장학금 신청"
        state.rewritten_query = "장학금 신청"
        state.keywords = ["장학금", "신청"]
        state.category = "scholarship"
        state.filters = {"category": ["장학"], "department": ["장학지원팀"]}
        state.metadata["retrieval_strategy_log"] = {
            "filters": {},
            "ranking_hints": {"document_category": ["scholarship"], "category_values": ["장학"]},
        }
        state.metadata["retrieval_quality"] = {"ok": True, "blocking": False, "reason": "", "diagnostic_reason": ""}
        state.retrieved_docs = [
            RetrievedDoc(
                doc_id="scholarship",
                chunk_id="scholarship_1",
                title="Scholarship notice",
                content="Scholarship application details.",
                score=1.0,
                metadata={"source_type": "scholarship"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.rerank_documents", wraps=__import__("rag.selection.reranker", fromlist=["rerank_documents"]).rerank_documents) as mocked:
            pipeline._select_and_build_context(state)

        self.assertEqual(mocked.call_args.kwargs["filters"], {})
        self.assertEqual(mocked.call_args.kwargs["ranking_hints"]["document_category"], ["scholarship"])
        self.assertEqual(
            state.reranked_docs[0].metadata["rerank_signals"]["category_match"],
            0.7,
        )

    def test_selection_quality_flags_single_heading_mismatch(self) -> None:
        pipeline = ChatPipeline()
        quality = pipeline._evaluate_selection_quality(
            [
                RetrievedDoc(
                    doc_id="noise_doc",
                    chunk_id="noise_doc_1",
                    title="모집 공고",
                    content="채용 안내",
                    score=1.0,
                    metadata={
                        "source_type": "department",
                        "rerank_signals": {
                            "title_match": 0.0,
                            "section_title_match": 0.0,
                            "noise_score": 1.6,
                        },
                    },
                )
            ]
        )

        self.assertFalse(quality["top_heading_query_match"])
        self.assertTrue(quality["single_selected_heading_mismatch"])
        self.assertTrue(quality["selected_context_contamination"])

    def _write_chunk_file(self, relative_path: str, payload: list[dict]) -> None:
        file_path = self.chunk_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot_after_preprocess(self, state: PipelineState) -> dict[str, object]:
        return {
            "original_query": state.original_query,
            "normalized_query": state.normalized_query,
            "keywords": state.keywords,
            "entities": state.entities,
            "filters": state.filters,
            "category": state.category,
            "rewritten_queries": state.rewritten_queries,
            "rewritten_query": state.rewritten_query,
            "metadata": state.metadata.get("query_understanding"),
        }

    def _snapshot_after_embedding(self, state: PipelineState) -> dict[str, object]:
        return {
            "query_for_embedding": state.rewritten_query or state.normalized_query or state.original_query,
            "embedding_query": state.metadata.get("query_understanding", {}).get("embedding_query"),
            "query_vector": state.query_vector,
            "vector_size": len(state.query_vector),
        }

    def _snapshot_after_retrieve(self, state: PipelineState) -> dict[str, object]:
        return {
            "retrieval_strategy": state.retrieval_strategy,
            "retrieval_top_k": state.retrieval_top_k,
            "retrieval_request": state.metadata.get("retrieval_request"),
            "retrieval_strategy_log": state.metadata.get("retrieval_strategy_log"),
            "retrieved_docs": [
                {
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "title": doc.title,
                    "score": doc.score,
                    "category": doc.category,
                    "metadata": doc.metadata,
                }
                for doc in state.retrieved_docs
            ],
        }

    def _snapshot_after_select(self, state: PipelineState) -> dict[str, object]:
        return {
            "reranked_docs": [
                {
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "score": doc.score,
                    "rerank_signals": doc.metadata.get("rerank_signals"),
                }
                for doc in state.reranked_docs
            ],
            "selected_docs": [doc.doc_id for doc in state.selected_docs],
            "context": state.context,
        }

    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
