import unittest

from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.run.run_vector_ingestion import (
    split_chunks_by_embedding_quality,
    split_chunks_by_embedding_reuse,
)


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
        self.assertEqual(
            loader._content_id_for_chunk(
                {
                    "section_type": "attachment",
                    "section_title": "guide.pdf",
                    "metadata": {
                        "source_section_metadata": {
                            "file_url": "https://www.deu.ac.kr/file.pdf",
                            "file_hash_sha256": "abc123",
                        }
                    },
                },
                {
                    "clean": 10,
                    "table": 20,
                    "attachment": 30,
                    "attachment_name:guide.pdf": 31,
                    "attachment_url:https://www.deu.ac.kr/file.pdf": 32,
                    "attachment_hash:abc123": 33,
                },
            ),
            33,
        )

    def test_pgvector_loader_quality_gate_rejects_binary_content(self) -> None:
        loader = object.__new__(PGVectorLoader)

        allowed, metadata = loader._quality_gate_metadata(
            content="%PDF-1.7\nstream\nendobj\nxref\n%%EOF",
            content_type="attachment",
            source="asset",
            file_name="bad.pdf",
        )

        self.assertFalse(allowed)
        self.assertEqual(metadata["quality_status"], "binary_blocked")
        self.assertEqual(metadata["skip_reason"], "binary_marker_detected")
        self.assertIn("bad.pdf", metadata["note"])

    def test_pgvector_loader_quality_gate_allows_normal_pdf_text(self) -> None:
        loader = object.__new__(PGVectorLoader)

        allowed, metadata = loader._quality_gate_metadata(
            content="Application guide extracted from PDF. Submit documents by May 31.",
            content_type="attachment",
            source="asset",
            file_name="good.pdf",
        )

        self.assertTrue(allowed)
        self.assertEqual(metadata["quality_status"], "ok")

    def test_embedding_quality_filter_blocks_binary_and_marked_chunks(self) -> None:
        allowed, excluded = split_chunks_by_embedding_quality(
            [
                {
                    "chunk_id": "ok",
                    "content": "Normal scholarship application guide text.",
                    "metadata": {},
                },
                {
                    "chunk_id": "binary",
                    "content": "%PDF-1.7\nstream\nendobj\nxref\n%%EOF",
                    "metadata": {},
                },
                {
                    "chunk_id": "noise",
                    "content": "HOME > 게시판 > 공지사항",
                    "metadata": {"quality_status": "noise_blocked"},
                },
            ]
        )

        self.assertEqual([chunk["chunk_id"] for chunk in allowed], ["ok"])
        self.assertEqual([chunk["chunk_id"] for chunk in excluded], ["binary", "noise"])
        self.assertEqual(excluded[0]["metadata"]["quality_status"], "binary_blocked")
        self.assertEqual(excluded[1]["metadata"]["embedding_skip_reason"], "noise_blocked")


if __name__ == "__main__":
    unittest.main()
