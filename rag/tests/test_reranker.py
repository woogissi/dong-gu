import unittest

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.reranker import rerank_documents


class RerankerTest(unittest.TestCase):
    def test_reranks_by_title_and_keyword_relevance(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="general_notice",
                chunk_id="general_notice_1",
                title="General campus notice",
                content="Registration office hours and campus announcements.",
                score=10.0,
                category="notice",
                metadata={"source_type": "notice", "published_at": "2026-01-01"},
            ),
            RetrievedDoc(
                doc_id="scholarship_notice",
                chunk_id="scholarship_notice_1",
                title="Scholarship application period",
                content="Scholarship application documents and deadline information.",
                score=5.0,
                category="academic_notice",
                metadata={"source_type": "academic_notice", "published_at": "2026-04-01"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="scholarship application period",
            keywords=["scholarship", "application", "period"],
            category="academic_notice",
            filters={"document_category": ["academic_notice"]},
        )

        self.assertEqual(reranked[0].doc_id, "scholarship_notice")
        self.assertGreater(reranked[0].score, docs[1].score)
        self.assertEqual(reranked[0].metadata["original_score"], 5.0)
        self.assertIn("rerank_signals", reranked[0].metadata)

    def test_preserves_retrieval_order_when_scores_tie(self) -> None:
        docs = [
            RetrievedDoc(doc_id="a", chunk_id="a_1", content="same", score=1.0),
            RetrievedDoc(doc_id="b", chunk_id="b_1", content="same", score=1.0),
        ]

        reranked = rerank_documents(docs, query="", keywords=[])

        self.assertEqual([doc.doc_id for doc in reranked], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
