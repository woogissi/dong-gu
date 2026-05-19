import unittest

from crawler.ingestion.pgvector_loader import PGVectorLoader
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

    def test_pgvector_loader_maps_body_and_table_chunks_to_content_ids(self) -> None:
        loader = object.__new__(PGVectorLoader)

        self.assertEqual(
            loader._content_id_for_chunk({"section_type": "body"}, {"clean": 10, "table": 20}),
            10,
        )
        self.assertEqual(
            loader._content_id_for_chunk({"section_type": "table"}, {"clean": 10, "table": 20}),
            20,
        )
        self.assertIsNone(
            loader._content_id_for_chunk({"section_type": "attachment"}, {"clean": 10, "table": 20})
        )


if __name__ == "__main__":
    unittest.main()
