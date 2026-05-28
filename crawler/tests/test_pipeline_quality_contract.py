import unittest

from crawler.ingestion.chunker import DocumentChunker
from crawler.run.run_full_pipeline import (
    build_curated_document,
    dedupe_downloaded_attachments,
    merge_attachment_texts,
)
from crawler.utils.text_quality import document_quality_report


class PipelineQualityContractTest(unittest.TestCase):
    def test_raw_to_curated_preserves_attachment_text_and_metadata_for_rag(self) -> None:
        raw_doc = {
            "doc_id": "deu_notice_123",
            "source_type": "notice",
            "page_kind": "board_detail",
            "department": "Academic Office",
            "title": "Scholarship application notice",
            "source_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            "published_at": "2026-05-14",
            "updated_at": None,
            "raw_text": "Apply during the posted period. Submit the required documents.",
            "table_text": "Item | Value\nPeriod | 2026-05-20 to 2026-05-31",
            "structured_sections": [],
            "version": 1,
            "collected_at": "2026-05-20T12:00:00+09:00",
            "content_hash": "body-only",
            "metadata": {"author": "Academic Office"},
            "downloaded_attachments": [
                {
                    "attachment_index": 1,
                    "file_name": "guide.pdf",
                    "file_url": "https://www.deu.ac.kr/file.pdf",
                    "file_ext": ".pdf",
                    "file_size": 2048,
                    "file_hash_sha256": "abc123",
                    "content_type": "application/pdf",
                    "parser_type": "pdf",
                    "attachment_text": "Attachment explains eligibility, dates, and contact numbers.",
                    "page_count": 2,
                    "attachment_tables": [{"rows": 3}],
                }
            ],
        }

        curated = build_curated_document(raw_doc, version=1)

        self.assertIn("[ATTACHMENT: guide.pdf]", curated["attachment_text"])
        self.assertIn("eligibility", curated["attachment_text"])
        self.assertIn("Period | 2026-05-20", curated["table_text"])
        self.assertEqual(curated["metadata"]["attachments"][0]["file_hash_sha256"], "abc123")
        self.assertEqual(curated["metadata"]["attachments"][0]["parser_type"], "pdf")
        self.assertEqual(curated["metadata"]["attachments"][0]["table_count"], 1)
        self.assertFalse(document_quality_report(curated)["is_binary_like"])

    def test_curated_to_chunks_keeps_body_and_attachment_as_separate_rag_units(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        curated_doc = {
            "doc_id": "deu_notice_123",
            "version": 1,
            "source_type": "notice",
            "title": "Scholarship application notice",
            "source_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            "published_at": "2026-05-14",
            "department": "Academic Office",
            "normalize": "Apply during the posted period. Submit the required documents.",
            "attachment_text": (
                "[ATTACHMENT: guide.pdf]\n"
                "Attachment explains eligibility, dates, and contact numbers for applicants."
            ),
            "metadata": {
                "attachments": [
                    {
                        "file_name": "guide.pdf",
                        "file_url": "https://www.deu.ac.kr/file.pdf",
                        "file_hash_sha256": "abc123",
                    }
                ]
            },
        }

        chunks = chunker.chunk_document(curated_doc)

        self.assertEqual([chunk["section_type"] for chunk in chunks], ["body", "attachment"])
        self.assertIn("Scholarship application notice", chunks[0]["content"])
        self.assertIn("required documents", chunks[0]["content"])
        self.assertEqual(chunks[1]["section_title"], "guide.pdf")
        self.assertEqual(
            chunks[1]["metadata"]["source_section_metadata"]["file_hash_sha256"],
            "abc123",
        )

    def test_downloaded_attachments_are_deduped_by_hash_before_curated_merge(self) -> None:
        attachments = [
            {"file_name": "guide.pdf", "file_hash_sha256": "same", "file_url": "https://a.test/1.pdf"},
            {"file_name": "guide-copy.pdf", "file_hash_sha256": "same", "file_url": "https://a.test/2.pdf"},
            {"file_name": "form.hwp", "file_hash_sha256": "other", "file_url": "https://a.test/3.hwp"},
        ]

        deduped = dedupe_downloaded_attachments(attachments)

        self.assertEqual([item["file_name"] for item in deduped], ["guide.pdf", "form.hwp"])

    def test_binary_like_attachment_is_not_merged_into_curated_text(self) -> None:
        attachments = [
            {
                "file_name": "bad.pdf",
                "attachment_text": "%PDF-1.7\nstream\nendobj\nxref\n%%EOF",
            },
            {
                "file_name": "good.pdf",
                "attachment_text": "Application schedule and eligibility details.",
            },
        ]

        merged = merge_attachment_texts(attachments)

        self.assertNotIn("%PDF", merged)
        self.assertIn("good.pdf", merged)
        self.assertIsNone(attachments[0]["attachment_text"])
        self.assertEqual(attachments[0]["quality_status"], "parse_failed")

    def test_empty_attachment_text_is_not_chunked(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        curated_doc = {
            "doc_id": "deu_notice_empty_attachment",
            "version": 1,
            "source_type": "notice",
            "title": "Attachment parse failed",
            "normalize": "Normal body text with enough words for retrieval chunk creation.",
            "attachment_text": None,
            "metadata": {
                "attachments": [
                    {
                        "file_name": "missing.pdf",
                        "parse_status": "parser_empty_text",
                        "needs_reprocess": True,
                    }
                ]
            },
        }

        chunks = chunker.chunk_document(curated_doc)

        self.assertEqual([chunk["section_type"] for chunk in chunks], ["body"])


if __name__ == "__main__":
    unittest.main()
