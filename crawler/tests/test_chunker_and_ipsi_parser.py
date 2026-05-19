import unittest

from bs4 import BeautifulSoup

from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.ingestion.chunker import DocumentChunker


class ChunkerAndIpsiParserTest(unittest.TestCase):
    def test_ipsi_parser_prefers_title_hint(self) -> None:
        parser = IpsiNoticeParser()
        soup = BeautifulSoup("<html><title>fallback</title></html>", "html.parser")

        self.assertEqual(parser.find_title(soup, title_hint="입학 공지"), "입학 공지")

    def test_chunker_splits_attachment_sections(self) -> None:
        chunker = DocumentChunker(max_chars=120, overlap_chars=20)
        doc = {
            "doc_id": "doc1",
            "version": 1,
            "source_type": "notice",
            "title": "공지",
            "source_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=1",
            "attachment_text": (
                "[ATTACHMENT: a.pdf]\n"
                "첫 번째 첨부 본문입니다. 장학 신청 일정과 제출 서류 안내가 포함되어 있습니다.\n\n"
                "[ATTACHMENT: b.pdf]\n"
                "두 번째 첨부 본문입니다. 수강 신청 절차와 유의사항 안내가 포함되어 있습니다."
            ),
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual([chunk["section_title"] for chunk in chunks], ["a.pdf", "b.pdf"])
        self.assertTrue(all(chunk["section_type"] == "attachment" for chunk in chunks))

    def test_chunk_hash_uses_normalized_text(self) -> None:
        chunker = DocumentChunker()

        first_hash = chunker.make_chunk_hash("PDF   다운로드\n\nNOTICE |||")
        second_hash = chunker.make_chunk_hash("pdf 다운로드 NOTICE |")

        self.assertEqual(first_hash, second_hash)

    def test_chunker_skips_short_stub_chunks(self) -> None:
        chunker = DocumentChunker()
        doc = {
            "doc_id": "doc-stub",
            "version": 1,
            "source_type": "static_page",
            "title": "센터 메인",
            "normalize": "PDF 다운로드",
        }

        self.assertEqual(chunker.chunk_document(doc), [])

    def test_chunker_keeps_meaningful_short_chunks(self) -> None:
        chunker = DocumentChunker()
        doc = {
            "doc_id": "doc-contact",
            "version": 1,
            "source_type": "notice",
            "title": "문의처",
            "normalize": "문의: 장학지원팀 051-890-1234",
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual(len(chunks), 1)
        self.assertIn("051-890-1234", chunks[0]["content"])

    def test_chunker_adds_paragraph_overlap_when_enabled(self) -> None:
        chunker = DocumentChunker(max_chars=60, paragraph_overlap_chars=15)
        first = "첫 번째 문단입니다. 장학 신청 일정과 제출 서류 안내가 포함되어 있습니다."
        second = "두 번째 문단입니다. 접수 기간과 담당 부서 연락처를 안내합니다."

        chunks = chunker.split_section_into_chunks(f"{first}\n\n{second}")

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[1].startswith(chunker.build_paragraph_overlap(first)))
