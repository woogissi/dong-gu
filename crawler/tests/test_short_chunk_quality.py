import unittest

from crawler.ingestion.chunker import DocumentChunker


class ShortChunkQualityTest(unittest.TestCase):
    def test_keeps_meaningful_short_contact_schedule_money_and_place_chunks(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        samples = [
            "\ubb38\uc758: \ud559\uc0dd\uc9c0\uc6d0\ud300 051-890-1234",
            "\uc2e0\uccad\uae30\uac04: 2026.03.01 ~ 2026.03.15",
            "\uc7a5\ud559\uae08 \uae08\uc561: 1,000,000\uc6d0",
            "\ud559\uacfc\uc0ac\ubb34\uc2e4 \uc704\uce58: \uacf5\ud559\uad00 315\ud638",
            "\uc6b4\uc601\uc2dc\uac04: \ud3c9\uc77c 09:00~18:00",
            "\uc774\uba54\uc77c: student@example.ac.kr",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                report = chunker.short_chunk_quality_score(sample)

                self.assertEqual(report["decision"], "keep")
                self.assertTrue(report["meaningful_signals"])
                self.assertFalse(chunker.is_stub_chunk(sample))

    def test_drops_short_navigation_board_shell_and_share_chunks(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        samples = [
            "HOME > \uac8c\uc2dc\ud310 > \uacf5\uc9c0\uc0ac\ud56d",
            "\ubc88\ud638 \uc81c\ubaa9 \uc791\uc131\uc790 \uc791\uc131\uc77c \uc870\ud68c\uc218",
            "\ub85c\uadf8\uc778 \ud68c\uc6d0\uac00\uc785 \uc0ac\uc774\ud2b8\ub9f5",
            "\ud398\uc774\uc2a4\ubd81 \ud2b8\uc704\ud130 \uacf5\uc720",
            "\uc774\uc804\uae00 \ub2e4\uc74c\uae00",
            "\uac80\uc0c9\uc5b4\ub97c \uc785\ub825\ud558\uc138\uc694",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                report = chunker.short_chunk_quality_score(sample)

                self.assertEqual(report["decision"], "drop")
                self.assertTrue(report["noise_signals"])
                self.assertTrue(chunker.is_stub_chunk(sample))

    def test_chunker_keeps_useful_short_sections_and_drops_shell_sections(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        doc = {
            "doc_id": "doc-short-quality",
            "version": 1,
            "source_type": "notice",
            "title": "\uc9e7\uc740 \uc815\ubcf4",
            "structured_sections": [
                {"section_type": "body", "section_title": "nav", "text": "HOME > \uac8c\uc2dc\ud310 > \uacf5\uc9c0\uc0ac\ud56d"},
                {"section_type": "body", "section_title": "contact", "text": "\ubb38\uc758: \ud559\uc0dd\uc9c0\uc6d0\ud300 051-890-1234"},
                {"section_type": "body", "section_title": "period", "text": "\uc2e0\uccad\uae30\uac04: 2026.03.01 ~ 2026.03.15"},
                {"section_type": "body", "section_title": "amount", "text": "\uc7a5\ud559\uae08 \uae08\uc561: 1,000,000\uc6d0"},
            ],
        }

        chunks = chunker.chunk_document(doc)
        content = "\n".join(chunk["content"] for chunk in chunks)

        self.assertNotIn("HOME > \uac8c\uc2dc\ud310", content)
        self.assertIn("051-890-1234", content)
        self.assertIn("2026.03.01", content)
        self.assertIn("1,000,000\uc6d0", content)

    def test_chunker_records_quality_skip_reasons(self) -> None:
        chunker = DocumentChunker(max_chars=120, skip_stub_chunks=False)
        doc = {
            "doc_id": "doc-quality-skip",
            "version": 1,
            "source_type": "notice",
            "title": "Quality skip",
            "structured_sections": [
                {
                    "section_type": "body",
                    "section_title": "binary",
                    "text": "%PDF-1.7\nstream\nendobj\nxref\n%%EOF",
                },
                {
                    "section_type": "body",
                    "section_title": "short",
                    "text": "general words only",
                },
            ],
            "metadata": {},
        }

        chunks = chunker.chunk_document(doc)
        statuses = {item["quality_status"] for item in doc["metadata"]["quality_skips"]}

        self.assertEqual(chunks, [])
        self.assertIn("binary_blocked", statuses)
        self.assertIn("short_chunk_blocked", statuses)


if __name__ == "__main__":
    unittest.main()
