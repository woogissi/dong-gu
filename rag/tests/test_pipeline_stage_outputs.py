import json
import os
import tempfile
import unittest
from pathlib import Path
from pprint import pprint
from unittest.mock import Mock, patch

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.retrieval import retriever


class PipelineStageOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chunk_dir = Path(self.temp_dir.name)
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
                    "category_lv1": "학사",
                    "category_lv2": "수강",
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
                    "category_lv1": "기숙사",
                    "category_lv2": "입사",
                },
            ],
        )

    def tearDown(self) -> None:
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()
        os.environ.pop("RAG_CHUNK_DATA_DIR", None)
        os.environ.pop("RAG_USE_DB", None)
        self.temp_dir.cleanup()

    def test_pipeline_stage_outputs(self) -> None:
        fake_embedder = Mock()
        fake_embedder.embed_query.return_value = [0.11, 0.22, 0.33]
        with patch("rag.pipeline.chat_pipeline.KoE5Embedder", return_value=fake_embedder):
            pipeline = ChatPipeline()
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
        pipeline.embedder.embed_query.assert_called_once_with(state.rewritten_query)

        pipeline._retrieve(state)
        self._debug_print("after_retrieve", self._snapshot_after_retrieve(state))

        self.assertEqual(state.retrieval_strategy, "lexical")
        self.assertEqual(state.retrieval_top_k, 10)
        self.assertIn("retrieval_request", state.metadata)
        self.assertIn("retrieval_strategy_log", state.metadata)
        self.assertGreaterEqual(len(state.retrieved_docs), 1)
        self.assertEqual(state.retrieved_docs[0].doc_id, "notice_1")
        self.assertEqual(state.retrieved_docs[0].metadata["strategy"], "lexical")
        self.assertTrue(state.retrieved_docs[0].metadata["matched_tokens"])

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

    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
