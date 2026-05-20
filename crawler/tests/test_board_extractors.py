import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.run.run_full_pipeline import fetch_board_detail_documents


class BoardExtractorsTest(unittest.TestCase):
    def assertSingleListParams(self, requested_url: str, params: dict) -> None:
        self.assertEqual(urlsplit(requested_url).query, "")
        self.assertEqual(params["mode"], "list")
        self.assertNotIn("mode", parse_qs(urlsplit(requested_url).query))
        for key in ("mode", "articleLimit", "article.offset"):
            self.assertEqual(list(params).count(key), 1)

    def test_extract_list_passes_base_url_when_list_url_has_no_query(self) -> None:
        extractor = BoardListExtractor()
        extractor.fetch = Mock(return_value="<table></table>")

        extractor.extract_list("https://www.deu.ac.kr/www/deu-bids.do", page_no=1, page_size=10)

        requested_url, params = extractor.fetch.call_args.args
        self.assertEqual(requested_url, "https://www.deu.ac.kr/www/deu-bids.do")
        self.assertEqual(params["article.offset"], 0)
        self.assertEqual(params["articleLimit"], 10)
        self.assertSingleListParams(requested_url, params)

    def test_extract_list_overwrites_existing_list_query_params(self) -> None:
        extractor = BoardListExtractor()
        extractor.fetch = Mock(return_value="<table></table>")

        result = extractor.extract_list(
            "https://www.deu.ac.kr/www/deu-education.do?mode=list&articleLimit=10&article.offset=70",
            page_no=3,
            page_size=10,
        )

        requested_url, params = extractor.fetch.call_args.args
        self.assertEqual(requested_url, "https://www.deu.ac.kr/www/deu-education.do")
        self.assertEqual(params["article.offset"], 20)
        self.assertEqual(params["articleLimit"], 10)
        self.assertEqual(params["mode"], "list")
        self.assertSingleListParams(requested_url, params)
        self.assertEqual(result["list_url"].count("article.offset="), 1)
        self.assertEqual(result["list_url"].count("articleLimit="), 1)
        self.assertEqual(result["list_url"].count("mode="), 1)

    def test_extract_list_collapses_duplicate_query_params(self) -> None:
        extractor = BoardListExtractor()
        extractor.fetch = Mock(return_value="<table></table>")

        extractor.extract_list(
            "https://www.deu.ac.kr/www/deu-today.do?mode=list&&articleLimit=10"
            "&article.offset=70&article.offset=0&articleLimit=20&mode=view",
            page_no=8,
            page_size=10,
        )

        requested_url, params = extractor.fetch.call_args.args
        self.assertEqual(requested_url, "https://www.deu.ac.kr/www/deu-today.do")
        self.assertEqual(params["article.offset"], 70)
        self.assertEqual(params["articleLimit"], 10)
        self.assertEqual(params["mode"], "list")
        self.assertSingleListParams(requested_url, params)

    def test_extract_list_overwrites_offset_per_page(self) -> None:
        extractor = BoardListExtractor()
        extractor.fetch = Mock(return_value="<table></table>")

        for page_no, expected_offset in [(1, 0), (2, 10), (7, 60)]:
            extractor.extract_list(
                "https://www.deu.ac.kr/www/deu-job.do?mode=list&articleLimit=10&article.offset=70",
                page_no=page_no,
                page_size=10,
            )
            self.assertEqual(extractor.fetch.call_args.args[1]["article.offset"], expected_offset)

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
        self.assertEqual(result[0]["extraction_strategy"], "articleNo")

    def test_board_list_extracts_non_article_no_patterns(self) -> None:
        html = """
        <table>
          <tr>
            <td><a href="/board/view.do?id=abc123">id 기반 공지</a></td>
            <td>2026-05-14</td>
          </tr>
          <tr>
            <td><a href="#" onclick="detail('987')">onclick 공지</a></td>
            <td>2026-05-13</td>
          </tr>
        </table>
        """

        result = BoardListExtractor().parse_rows(
            html,
            "https://www.deu.ac.kr/www/list.do?mode=list",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["article_no"], "abc123")
        self.assertEqual(result[0]["extraction_strategy"], "query_id")
        self.assertEqual(result[1]["article_no"], "987")
        self.assertEqual(result[1]["extraction_strategy"], "articleNo")

    def test_deu_board_adapter_normalizes_onclick_detail_url(self) -> None:
        html = """
        <table>
          <tr><td><a href="#" onclick="jf_view('menu', '456')">동의대 패턴</a></td></tr>
        </table>
        """

        result = BoardListExtractor().parse_rows(
            html,
            "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
        )

        self.assertEqual(result[0]["article_no"], "456")
        self.assertIn("articleNo=456", result[0]["detail_url"])

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

    def test_board_detail_skips_do_view_links_as_attachments(self) -> None:
        html = """
        <html><body><main>
          <h2>Notice</h2>
          <a href="/pluscenter/file.do?mode=view&articleNo=84614">attachment-like page</a>
          <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">guide</a>
        </main></body></html>
        """

        doc = BoardDetailExtractor().build_raw_document(
            source_type="notice",
            detail_url="https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            html=html,
            title_hint=None,
        )

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
        self.assertNotIn("mode=view", doc["attachments"][0]["file_url"])

    def test_board_detail_skips_social_profile_links_as_attachments(self) -> None:
        html = """
        <html><body><main>
          <h2>Notice</h2>
          <a href="https://m.facebook.com/profile.php?id=1579580098940911/">student council</a>
          <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">guide</a>
        </main></body></html>
        """

        doc = BoardDetailExtractor().build_raw_document(
            source_type="notice",
            detail_url="https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            html=html,
            title_hint=None,
        )

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
        self.assertNotIn("facebook", doc["attachments"][0]["file_url"].lower())

    def test_board_detail_dedupes_same_attachment_url_with_different_labels(self) -> None:
        html = """
        <html><body><main>
          <h2>Notice</h2>
          <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">원본파일 Download</a>
          <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1"></a>
        </main></body></html>
        """

        doc = BoardDetailExtractor().build_raw_document(
            source_type="notice",
            detail_url="https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=123",
            html=html,
            title_hint=None,
        )

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertEqual(doc["attachments"][0]["attachment_index"], 1)
        self.assertEqual(doc["attachments"][0]["file_name"], "원본파일 Download")

    def test_board_detail_doc_id_uses_non_article_no_query_key(self) -> None:
        doc = BoardDetailExtractor().build_raw_document(
            source_type="notice",
            detail_url="https://www.deu.ac.kr/board/view.do?post_id=post-77",
            html="<html><body><main><h2>공지</h2><p>본문</p></main></body></html>",
            title_hint="공지",
        )

        self.assertEqual(doc["doc_id"], "deu_notice_post-77")

    def test_parallel_detail_fetch_preserves_list_order_and_records_failures(self) -> None:
        items = [
            {"detail_url": "https://example.test/1", "article_no": "1"},
            {"detail_url": "https://example.test/2", "article_no": "2"},
            {"detail_url": "https://example.test/3", "article_no": "3"},
        ]

        def fake_extract(source_type: str, parser_type: str, item: dict) -> dict:
            if item["article_no"] == "2":
                raise ValueError("boom")
            return {"doc_id": f"doc-{item['article_no']}"}

        with (
            patch("crawler.run.run_full_pipeline.extract_board_detail_document", side_effect=fake_extract),
            patch("crawler.run.run_full_pipeline.record_board_detail_error") as record_error,
        ):
            docs = fetch_board_detail_documents(
                source_type="notice",
                parser_type="default",
                items=items,
                workers=3,
            )

        self.assertEqual([doc["doc_id"] for doc in docs], ["doc-1", "doc-3"])
        record_error.assert_called_once()
