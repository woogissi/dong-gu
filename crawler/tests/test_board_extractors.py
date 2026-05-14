import unittest

from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.board_list_extractor import BoardListExtractor


class BoardExtractorsTest(unittest.TestCase):
    def test_board_list_extracts_article_rows(self) -> None:
        html = """
        <table>
          <tbody>
            <tr>
              <td>1</td>
              <td><a href="?mode=view&articleNo=123&article.offset=0">학사 공지</a></td>
              <td>2026-05-14</td>
            </tr>
            <tr>
              <td><a href="/www/other.do">외부 링크</a></td>
            </tr>
          </tbody>
        </table>
        """

        result = BoardListExtractor().parse_rows(
            html,
            "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["article_no"], "123")
        self.assertEqual(result[0]["title_hint"], "학사 공지")
        self.assertEqual(result[0]["published_at_hint"], "2026-05-14")
        self.assertIn("articleNo=123", result[0]["detail_url"])

    def test_board_detail_builds_raw_document_from_fixture(self) -> None:
        html = """
        <html>
          <head><title>학사 공지 | 동의대학교</title></head>
          <body>
            <main>
              <h2>학사 공지</h2>
              <div>작성일: 2026-05-14</div>
              <div>작성자: 학사지원팀</div>
              <div>조회수: 123</div>
              <div class="content">
                <p>본문 안내입니다.</p>
                <table><tr><th>항목</th><td>내용</td></tr></table>
                <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">첨부파일.hwp</a>
              </div>
            </main>
          </body>
        </html>
        """

        doc = BoardDetailExtractor().build_raw_document(
            source_type="notice",
            detail_url="https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            html=html,
            title_hint=None,
        )

        self.assertEqual(doc["doc_id"], "deu_notice_123")
        self.assertEqual(doc["page_kind"], "board_detail")
        self.assertEqual(doc["source_type"], "notice")
        self.assertIn("본문 안내입니다", doc["raw_text"])
        self.assertIn("항목 | 내용", doc["table_text"])
        self.assertEqual(doc["attachments"][0]["file_name"], "첨부파일.hwp")
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
