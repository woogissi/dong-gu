import os
import re
import unittest
from pathlib import Path
from pprint import pprint
from unittest.mock import patch

from rag.retrieval import retriever
from rag.schemas.retrieval import RetrievalRequest


class RetrieverSupabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if retriever.psycopg2 is None:
            raise unittest.SkipTest("psycopg2 is not installed; Supabase retriever tests require DB access.")

        try:
            with retriever._open_db_connection() as conn:
                with conn.cursor(cursor_factory=retriever.DictCursor) as cur:
                    cur.execute("SELECT COUNT(*) AS count FROM documents JOIN chunks ON chunks.doc_id = documents.doc_id")
                    if int(cur.fetchone()["count"]) == 0:
                        raise unittest.SkipTest("Supabase has no documents/chunks to search.")
        except retriever.psycopg2.Error as exc:
            raise unittest.SkipTest(f"Supabase connection is not available: {exc}") from exc

    def setUp(self) -> None:
        self._previous_rag_use_db = os.environ.get("RAG_USE_DB")
        self._previous_chunk_dir = os.environ.get("RAG_CHUNK_DATA_DIR")
        os.environ["RAG_USE_DB"] = "1"
        os.environ["RAG_CHUNK_DATA_DIR"] = str(Path(__file__).resolve().parent / "__no_local_chunks__")
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()

    def tearDown(self) -> None:
        self._restore_env("RAG_USE_DB", self._previous_rag_use_db)
        self._restore_env("RAG_CHUNK_DATA_DIR", self._previous_chunk_dir)
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()

    # Supabase에서 검색 결과가 제대로 반환되는지 확인하는 테스트 케이스
    # def test_retrieve_documents_returns_supabase_ranked_results(self) -> None:
    #     sample = self._fetch_searchable_sample()
    #     request = RetrievalRequest(
    #         query=sample["term"],
    #         query_variants=[sample["term"]],
    #         keywords=[sample["term"]],
    #         top_k=10,
    #     )

    #     self._debug_print("retrieve_documents request", request.model_dump())
    #     documents = self._retrieve_without_file_fallback(request)
    #     self._debug_print("retrieve_documents result", self._document_debug_rows(documents))

    #     self.assertGreaterEqual(len(documents), 1)
    #     self.assertIn(sample["doc_id"], {document.doc_id for document in documents})
    #     self.assertTrue(all(document.score > 0 for document in documents))
    #     self.assertTrue(all(document.metadata.get("matched_terms") for document in documents))

    def test_retrieve_documents_returns_supabase_ranked_results(self) -> None:
        my_query = "마이크로디그리 신청/변경 일정" 
        my_keywords = ["마이크로디그리", "신청", "변경", "일정"]

        request = RetrievalRequest(
            query=my_query,
            query_variants=[my_query],
            keywords=my_keywords,
            top_k=10,
        )

        self._debug_print("retrieve_documents request", request.model_dump())
        documents = self._retrieve_without_file_fallback(request)
        self._debug_print("retrieve_documents result", self._document_debug_rows(documents))

        self.assertGreaterEqual(len(documents), 1)

    # 검색어 필터가 제대로 적용되는지 확인하는 테스트 케이스들
    def test_retrieve_documents_applies_document_category_filter(self) -> None:
        sample = self._fetch_searchable_sample(where_sql="documents.source_type IS NOT NULL")
        request = RetrievalRequest(
            query=sample["term"],
            keywords=[sample["term"]],
            filters={"document_category": [sample["source_type"]]},
            top_k=10,
        )

        documents = self._retrieve_without_file_fallback(request)

        self.assertGreaterEqual(len(documents), 1)
        self.assertTrue(all(document.metadata["source_type"] == sample["source_type"] for document in documents))
        self.assertIn(sample["doc_id"], {document.doc_id for document in documents})

    # source_type 필터가 제대로 적용되는지 확인하는 테스트 케이스
    def test_retrieve_documents_applies_department_filter(self) -> None:
        sample = self._fetch_searchable_sample(where_sql="documents.department IS NOT NULL AND documents.department <> ''")
        request = RetrievalRequest(
            query=sample["term"],
            keywords=[sample["term"]],
            filters={"department": [sample["department"]]},
            top_k=10,
        )

        documents = self._retrieve_without_file_fallback(request)

        self.assertGreaterEqual(len(documents), 1)
        self.assertIn(sample["doc_id"], {document.doc_id for document in documents})

    # category_lv1 필터가 제대로 적용되는지 확인하는 테스트 케이스
    def test_retrieve_documents_applies_category_filter(self) -> None:
        sample = self._fetch_searchable_sample(where_sql="documents.source_type IS NOT NULL")
        request = RetrievalRequest(
            query=sample["term"],
            keywords=[sample["term"]],
            filters={"category": [sample["source_type"]]},
            top_k=10,
        )

        documents = self._retrieve_without_file_fallback(request)

        self.assertGreaterEqual(len(documents), 1)
        self.assertIn(sample["doc_id"], {document.doc_id for document in documents})

    # 검색 결과가 없을 때 빈 리스트를 반환하는지 확인하는 테스트 케이스
    def test_empty_search_results(self) -> None:
        request = RetrievalRequest(
            query="donggu-retriever-no-match-000000",
            keywords=["donggu-retriever-no-match-000000"],
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        self.assertEqual(len(documents), 0)

    # 테스트 케이스 추가: 검색어 변형(query_variants)이 Supabase 검색에 사용되는지 확인하는 테스트
    def test_query_variants_are_used_for_supabase_search(self) -> None:
        sample = self._fetch_searchable_sample()
        request = RetrievalRequest(
            query="",
            query_variants=[sample["term"]],
            keywords=[],
            top_k=10,
        )

        documents = self._retrieve_without_file_fallback(request)

        self.assertGreaterEqual(len(documents), 1)
        self.assertIn(sample["doc_id"], {document.doc_id for document in documents})

    def _retrieve_without_file_fallback(self, request: RetrievalRequest):
        with patch.object(retriever, "_load_bm25_index", side_effect=AssertionError("file fallback should not be used")):
            return retriever.retrieve_documents(request=request)

    def _fetch_searchable_sample(self, where_sql: str | None = None) -> dict:
        sql = """
        SELECT
            chunks.chunk_id,
            chunks.doc_id,
            chunks.content,
            documents.title,
            documents.source_type,
            documents.department,
            documents.category_lv1,
            documents.category_lv2
        FROM chunks
        JOIN documents ON documents.doc_id = chunks.doc_id
        WHERE chunks.content IS NOT NULL
        """
        if where_sql:
            sql += f"\n        AND ({where_sql})"
        sql += "\n        ORDER BY documents.published_at DESC NULLS LAST, chunks.chunk_id ASC LIMIT 200"

        with retriever._open_db_connection() as conn:
            with conn.cursor(cursor_factory=retriever.DictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()

                for row in rows:
                    for term in self._candidate_terms(row["title"], row["content"]):
                        cur.execute(
                            """
                            SELECT to_tsvector('simple', coalesce(%s, '') || ' ' || coalesce(%s, ''))
                                @@ plainto_tsquery('simple', %s) AS matched
                            """,
                            (row["title"], row["content"], term),
                        )
                        if cur.fetchone()["matched"]:
                            return {**dict(row), "term": term}

        self.skipTest("No searchable Supabase sample matched PostgreSQL full-text search.")

    def _candidate_terms(self, *texts: str | None) -> list[str]:
        terms: list[str] = []
        for text in texts:
            if not text:
                continue
            for term in re.findall(r"[가-힣A-Za-z0-9]{2,}", text):
                if term not in terms:
                    terms.append(term)
        return terms

    def _document_debug_rows(self, documents) -> list[dict]:
        return [
            {
                "doc_id": document.doc_id,
                "chunk_id": document.chunk_id,
                "score": document.score,
                "title": document.title,
                "matched_terms": document.metadata.get("matched_terms"),
                "source_type": document.metadata.get("source_type"),
            }
            for document in documents
        ]

    def _restore_env(self, key: str, previous_value: str | None) -> None:
        if previous_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous_value

    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
