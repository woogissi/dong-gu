import unittest

from crawler.run.run_vector_ingestion import split_chunks_by_embedding_reuse


class VectorIngestionTest(unittest.TestCase):
    def test_split_chunks_by_embedding_reuse(self) -> None:
        chunks = [
            {"chunk_id": "c1", "content": "old"},
            {"chunk_id": "c2", "content": "new"},
            {"chunk_id": "c3", "content": "also old"},
        ]

        reusable, pending = split_chunks_by_embedding_reuse(chunks, {"c1", "c3"})

        self.assertEqual([chunk["chunk_id"] for chunk in reusable], ["c1", "c3"])
        self.assertEqual([chunk["chunk_id"] for chunk in pending], ["c2"])


if __name__ == "__main__":
    unittest.main()
