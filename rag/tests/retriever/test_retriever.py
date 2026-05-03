import json
import os
import tempfile
import unittest
from pprint import pprint
from pathlib import Path

from rag.retrieval import retriever
from rag.schemas.retrieval import RetrievalRequest


class RetrieverBM25Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chunk_dir = Path(self.temp_dir.name)
        os.environ["RAG_CHUNK_DATA_DIR"] = str(self.chunk_dir)
        os.environ["RAG_USE_DB"] = "0"  # DB 검색 비활성화로 파일 기반 검색만 테스트
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
                {
                    "chunk_id": "notice_3_chunk_1",
                    "doc_id": "notice_3",
                    "title": "장학금 신청 안내",
                    "content": "장학금 신청 기간과 제출 서류를 안내합니다.",
                    "source_type": "notice",
                    "source_url": "https://example.com/notice_3",
                    "published_at": "2026-04-12",
                    "department": "학생지원팀",
                    "category_lv1": "장학",
                    "category_lv2": "신청",
                },
                {
                    "chunk_id": "notice_4_chunk_1",
                    "doc_id": "notice_4",
                    "title": "등록금 납부 안내",
                    "content": "등록금 납부 기한과 납부 방법을 안내합니다.",
                    "source_type": "notice",
                    "source_url": "https://example.com/notice_4",
                    "published_at": "2026-04-13",
                    "department": "재무팀",
                    "category_lv1": "등록",
                    "category_lv2": "납부",
                },
            ],
        )

    def tearDown(self) -> None:
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()
        os.environ.pop("RAG_CHUNK_DATA_DIR", None)
        os.environ.pop("RAG_USE_DB", None)
        self.temp_dir.cleanup()

    def test_retrieve_documents_returns_bm25_ranked_results(self) -> None:
        request = RetrievalRequest(
            query="수강신청 정정 기간 알려줘",
            query_variants=["수강신청 변경 기간"],
            keywords=["수강신청", "정정", "기간"],
            top_k=5,
        )

        self._debug_print("retrieve_documents request", request.model_dump())
        documents = retriever.retrieve_documents(request=request)
        self._debug_print(
            "retrieve_documents result",
            [
                {
                    "doc_id": document.doc_id,
                    "chunk_id": document.chunk_id,
                    "score": document.score,
                    "title": document.title,
                    "matched_tokens": document.metadata.get("matched_tokens"),
                    "source_type": document.metadata.get("source_type"),
                }
                for document in documents
            ],
        )

        # 수정: 결과가 1개 이상 나왔는지 확인하고, 1위 결과가 notice_1인지 검증 (랭킹 검증)
        self.assertGreaterEqual(len(documents), 1)
        self.assertEqual(documents[0].doc_id, "notice_1")
        self.assertGreater(documents[0].score, 0)

        # notice_1의 매칭 토큰 중 하나라도 쿼리 키워드와 연관이 있는지 확인
        matched = documents[0].metadata.get("matched_tokens", [])
        self.assertTrue(any(kw in matched for kw in ["수강신청", "수강", "신청", "정정", "기간"]))

    def test_retrieve_documents_applies_document_category_filter(self) -> None:
        request = RetrievalRequest(
            query="안내",
            keywords=["안내"],
            filters={"document_category": ["academic_notice"]},
            top_k=5,
        )

        self._debug_print("category_filter request", request.model_dump())
        documents = retriever.retrieve_documents(request=request)
        self._debug_print(
            "category_filter result",
            [
                {
                    "doc_id": document.doc_id,
                    "chunk_id": document.chunk_id,
                    "score": document.score,
                    "title": document.title,
                    "source_type": document.metadata.get("source_type"),
                }
                for document in documents
            ],
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["source_type"], "academic_notice")

    def test_bm25_scoring_accuracy(self) -> None:
        """BM25 점수 계산 정확도 검증"""
        request = RetrievalRequest(
            query="수강신청",
            keywords=["수강신청"],
            top_k=10,
        )

        documents = retriever.retrieve_documents(request=request)

        # 검색 결과가 있어야 함
        self.assertGreater(len(documents), 0)

        # 수정: 모든 문서가 형태소 분석된 토큰(수강, 신청 등) 중 최소 하나를 포함하는지 검증
        for doc in documents:
            self.assertGreater(doc.score, 0)
            matched = doc.metadata.get("matched_tokens", [])
            # "수강신청"이 통째로 있거나 "수강", "신청"으로 나뉘어 있을 수 있음을 허용
            self.assertTrue(
                any(token in matched for token in ["수강신청", "수강", "신청"]),
                f"Document {doc.doc_id} has unexpected matched_tokens: {matched}"
            )

        # 가장 높은 점수의 문서가 수강신청 관련 문서여야 함 (변함 없음)
        top_doc = documents[0]
        self.assertEqual(top_doc.doc_id, "notice_1")
        self.assertIn("수강신청", top_doc.content)

    def test_keyword_matching_multiple_terms(self) -> None:
        """여러 키워드 매칭 테스트"""
        request = RetrievalRequest(
            query="장학금 신청 안내",
            keywords=["장학금", "신청", "안내"],
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        # 장학금 관련 문서가 가장 높은 점수로 반환되어야 함
        self.assertGreater(len(documents), 0)
        top_doc = documents[0]
        self.assertEqual(top_doc.doc_id, "notice_3")
        self.assertIn("장학금", top_doc.content)

        # 매칭된 토큰에 여러 키워드가 포함되어야 함
        matched_tokens = set(top_doc.metadata["matched_tokens"])
        expected_tokens = {"장학금", "신청", "안내"}
        self.assertTrue(expected_tokens.issubset(matched_tokens))

    def test_search_result_ranking(self) -> None:
        """검색 결과 순위 테스트"""
        request = RetrievalRequest(
            query="안내",
            keywords=["안내"],
            top_k=10,
        )

        documents = retriever.retrieve_documents(request=request)

        # 결과가 점수 내림차순으로 정렬되어야 함
        for i in range(len(documents) - 1):
            self.assertGreaterEqual(documents[i].score, documents[i + 1].score)

        # 모든 문서의 title 또는 content에 "안내" 키워드가 포함되어야 함
        for doc in documents:
            has_keyword = "안내" in doc.title or "안내" in doc.content
            self.assertTrue(has_keyword, f"Document {doc.doc_id} does not contain '안내' in title or content")
            self.assertIn("안내", doc.metadata["matched_tokens"])

    def test_filters_department_and_category(self) -> None:
        """부서 및 카테고리 필터 테스트"""
        # 학사관리팀 필터 테스트
        request_dept = RetrievalRequest(
            query="안내",
            keywords=["안내"],
            filters={"department": ["학사관리팀"]},
            top_k=5,
        )

        documents_dept = retriever.retrieve_documents(request=request_dept)

        # 학사관리팀 문서만 반환되어야 함
        self.assertEqual(len(documents_dept), 1)
        self.assertEqual(documents_dept[0].doc_id, "notice_1")
        self.assertEqual(documents_dept[0].metadata["source_type"], "academic_notice")

        # 장학 카테고리 필터 테스트
        request_cat = RetrievalRequest(
            query="안내",
            keywords=["안내"],
            filters={"category": ["장학"]},
            top_k=5,
        )

        documents_cat = retriever.retrieve_documents(request=request_cat)

        # 장학 카테고리 문서만 반환되어야 함
        self.assertEqual(len(documents_cat), 1)
        self.assertEqual(documents_cat[0].doc_id, "notice_3")
        self.assertEqual(documents_cat[0].metadata["source_type"], "notice")

    def test_empty_search_results(self) -> None:
        """빈 검색 결과 테스트"""
        request = RetrievalRequest(
            query="존재하지 않는 키워드",
            keywords=["존재하지않는키워드"],
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        # 검색 결과가 없어야 함
        self.assertEqual(len(documents), 0)

    def test_query_variants_scoring(self) -> None:
        """쿼리 변형 검색 테스트"""
        request = RetrievalRequest(
            query="수강신청 변경",
            query_variants=["수강신청 정정", "수강 변경"],
            keywords=["수강신청", "변경", "정정"],
            top_k=5,
        )

        documents = retriever.retrieve_documents(request=request)

        # 수강신청 관련 문서가 반환되어야 함
        self.assertGreater(len(documents), 0)
        top_doc = documents[0]
        self.assertEqual(top_doc.doc_id, "notice_1")

        # 매칭된 토큰에 쿼리 변형의 키워드가 포함되어야 함
        matched_tokens = set(top_doc.metadata["matched_tokens"])
        self.assertTrue({"수강신청", "정정"}.issubset(matched_tokens) or
                       {"수강신청", "변경"}.issubset(matched_tokens))

    def _write_chunk_file(self, relative_path: str, payload: list[dict]) -> None:
        file_path = self.chunk_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
