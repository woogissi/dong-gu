import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.attachment_downloader import AttachmentDownloader
from crawler.extractors.static_page_extractor import StaticPageExtractor


class FakeStreamResponse:
    url = "https://www.deu.ac.kr/file.pdf"
    status_code = 200
    headers = {
        "Content-Type": "application/pdf",
        "Content-Length": "11",
        "Content-Disposition": 'attachment; filename="guide.pdf"',
    }

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield b"hello "
        yield b"world"


class FailingOnceStreamResponse(FakeStreamResponse):
    attempts = 0

    def iter_content(self, chunk_size: int):
        type(self).attempts += 1
        if type(self).attempts == 1:
            yield b"partial "
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        yield b"hello "
        yield b"again"


class AttachmentAndStaticExtractorTest(unittest.TestCase):
    def test_attachment_downloader_uses_timeout_size_limit_and_saves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(
                base_save_dir=Path(tmpdir),
                max_file_size=1024,
                timeout=(1, 2),
            )
            downloader.session.get = Mock(return_value=FakeStreamResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "안내문",
                    "file_url": "https://www.deu.ac.kr/file.pdf",
                },
            )

            downloader.session.get.assert_called_once_with(
                "https://www.deu.ac.kr/file.pdf",
                timeout=(1, 2),
                stream=True,
            )
            self.assertEqual(downloaded["file_ext"], ".pdf")
            self.assertEqual(Path(downloaded["saved_path"]).read_bytes(), b"hello world")

    def test_attachment_downloader_retries_chunked_encoding_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            FailingOnceStreamResponse.attempts = 0
            downloader = AttachmentDownloader(
                base_save_dir=Path(tmpdir),
                max_file_size=1024,
                timeout=(1, 2),
                max_download_attempts=2,
                retry_backoff_factor=0,
            )
            downloader.session.get = Mock(return_value=FailingOnceStreamResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "guide",
                    "file_url": "https://www.deu.ac.kr/file.pdf",
                },
            )

            self.assertEqual(downloader.session.get.call_count, 2)
            self.assertEqual(Path(downloaded["saved_path"]).read_bytes(), b"hello again")
            self.assertFalse(Path(downloaded["saved_path"] + ".part").exists())

    def test_static_page_extractor_collects_attachment_links(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <p>정적 안내 본문</p>
              <a href="/files/guide.pdf">안내 PDF</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/info.do",
                    "final_url": "https://www.deu.ac.kr/www/info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("campus", "https://www.deu.ac.kr/www/info.do")

        self.assertEqual(doc["attachments"][0]["file_name"], "안내 PDF")
        self.assertEqual(doc["attachments"][0]["file_url"], "https://www.deu.ac.kr/files/guide.pdf")

    def test_static_page_extractor_skips_do_view_links_as_attachments(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="/pluscenter/file.do?mode=view&articleNo=84614">attachment-like page</a>
              <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">download</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/info.do",
                    "final_url": "https://www.deu.ac.kr/www/info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("campus", "https://www.deu.ac.kr/www/info.do")

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
        self.assertNotIn("mode=view", doc["attachments"][0]["file_url"])

    def test_static_page_extractor_collects_department_links_from_ipsi_detail(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="https://mse.deu.ac.kr">신소재공학부</a>
              <a href="https://example.com">external</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://ipsi.deu.ac.kr/universityDetail.do",
                    "final_url": "https://ipsi.deu.ac.kr/universityDetail.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("admission", "https://ipsi.deu.ac.kr/universityDetail.do")

        self.assertEqual(doc["outgoing_links"], ["https://mse.deu.ac.kr"])

    def test_static_page_extractor_keeps_verify_true_for_has_ssl_errors(self) -> None:
        extractor = StaticPageExtractor(allowed_hosts={"has.deu.ac.kr"})
        extractor.session.get = Mock(side_effect=requests.exceptions.SSLError("certificate expired"))

        with self.assertRaises(requests.exceptions.SSLError) as ctx:
            extractor.fetch_result("https://has.deu.ac.kr/")

        self.assertIn("keeping verify=True", str(ctx.exception))
        extractor.session.get.assert_called_once_with("https://has.deu.ac.kr/", timeout=extractor.timeout)


if __name__ == "__main__":
    unittest.main()
