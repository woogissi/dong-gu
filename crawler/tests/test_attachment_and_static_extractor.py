import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
