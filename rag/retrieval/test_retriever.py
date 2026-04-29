import json
import os
import tempfile
import unittest
from pathlib import Path

from rag.retrieval import retriever
from rag.schemas.retrieval import RetrievalRequest


class RetrieverBM25Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chunk_dir = Path(self.temp_dir.name)
        os.environ["RAG_CHUNK_DATA_DIR"] = str(self.chunk_dir)
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()

        self._write_chunk_file(
            "academic_notice/sample.json",
            [
                {
                    "chunk_id": "notice_1_chunk_1",
                    "doc_id": "notice_1",
                    "title": "수강신청 변경 안내",
                    "content": "수강신청 정정 기간과 신청 방법을 안내합니다.",
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
        self.temp_dir.cleanup()

    def test_retrieve_documents_returns_bm25_ranked_results(self) -> None:
        request = RetrievalRequest(
            query="수강신청 정정 기간 알려줘",
            query_variants=["수강신청 변경 기간"],
            keywords=["수강신청", "정정", "기간"],
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].doc_id, "notice_1")
        self.assertGreater(documents[0].score, 0)
        self.assertIn("수강신청", documents[0].metadata["matched_tokens"])

    def test_retrieve_documents_applies_document_category_filter(self) -> None:
        request = RetrievalRequest(
            query="안내",
            keywords=["안내"],
            filters={"document_category": ["academic_notice"]},
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["source_type"], "academic_notice")

    def _write_chunk_file(self, relative_path: str, payload: list[dict]) -> None:
        file_path = self.chunk_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
