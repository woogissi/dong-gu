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
