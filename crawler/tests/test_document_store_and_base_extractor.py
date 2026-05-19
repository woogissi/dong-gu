import tempfile
import unittest
import gzip
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup

from crawler.extractors.base import BaseExtractor, GenericExtractor
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.storage.document_store import DocumentStore


class DocumentStoreAndBaseExtractorTest(unittest.TestCase):
    def test_document_store_preserves_raw_html_in_json_and_html_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = DocumentStore(
                raw_html_dir=base / "raw" / "html",
                raw_doc_dir=base / "raw" / "documents",
                curated_doc_dir=base / "curated" / "documents",
            )
            raw_doc = {
                "doc_id": "doc1",
                "source_type": "notice",
                "html": "<html><body>raw</body></html>",
                "title": "title",
            }

            saved, raw_path, html_path = store.save_raw_document(raw_doc)

            self.assertTrue(raw_path.exists())
            self.assertTrue(html_path.exists())
            self.assertEqual(saved["html"], raw_doc["html"])
            self.assertEqual(saved["raw_html"], raw_doc["html"])
            self.assertEqual(saved["html_path"], html_path.as_posix())
            self.assertEqual(html_path.read_text(encoding="utf-8"), raw_doc["html"])

    def test_base_extractor_returns_fetch_result_metadata(self) -> None:
        extractor = BaseExtractor(headers={"User-Agent": "test"})
        response = Mock()
        response.url = "https://www.deu.ac.kr/final"
        response.status_code = 200
        response.headers = {"content-type": "text/html"}
        response.text = "<html></html>"
        response.raise_for_status.return_value = None
        extractor.session.get = Mock(return_value=response)

        result = extractor.fetch_result("https://www.deu.ac.kr/start")
        metadata = extractor.fetch_metadata(result)

        self.assertEqual(result.raw_html, "<html></html>")
        self.assertEqual(metadata["url"], "https://www.deu.ac.kr/start")
        self.assertEqual(metadata["final_url"], "https://www.deu.ac.kr/final")
        self.assertEqual(metadata["status_code"], 200)
        self.assertEqual(metadata["extractor_name"], "base")

    def test_generic_extractor_fallback_extracts_title_and_text(self) -> None:
        html = """
        <html>
          <head><title>Fallback Title</title><style>.x{}</style></head>
          <body><nav>메뉴</nav><main><p>검색 가능한 본문</p></main></body>
        </html>
        """

        result = GenericExtractor().extract_content(html)

        self.assertEqual(result["title"], "Fallback Title")
        self.assertIn("검색 가능한 본문", result["raw_text"])
        self.assertNotIn("메뉴", result["raw_text"])
        self.assertEqual(result["extraction_strategy"], "generic_fallback")

    def test_generic_extractor_merges_json_in_html_text(self) -> None:
        html = """
        <html>
          <head><title>JSON Page</title></head>
          <body>
            <script id="__NEXT_DATA__" type="application/json">
              {"props":{"pageProps":{"notice":"JSON 본문 안내"}}}
            </script>
            <main><p>HTML 본문</p></main>
          </body>
        </html>
        """

        result = GenericExtractor().extract_content(html)

        self.assertIn("HTML 본문", result["raw_text"])
        self.assertIn("JSON 본문 안내", result["raw_text"])
        self.assertEqual(result["extraction_strategy"], "generic_fallback_json")

    def test_static_page_extractor_collects_department_navigation_links(self) -> None:
        html = """
        <html>
          <body>
            <header>
              <nav id="gnb">
                <a href="/computer/sub01_01.do">intro</a>
                <a href="/computer/sub02.do">faculty</a>
                <a href="/ai/index.do">other department</a>
                <a href="https://www.deu.ac.kr/www">university</a>
              </nav>
            </header>
            <main><p>body</p></main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"swcc.deu.ac.kr", "www.deu.ac.kr"})
        soup = BeautifulSoup(html, "html.parser")

        links = extractor.extract_navigation_links(soup, "https://swcc.deu.ac.kr/computer/index.do")

        self.assertIn("https://swcc.deu.ac.kr/computer/sub01_01.do", links)
        self.assertIn("https://swcc.deu.ac.kr/computer/sub02.do", links)
        self.assertNotIn("https://swcc.deu.ac.kr/ai/index.do", links)
        self.assertNotIn("https://www.deu.ac.kr/www", links)

    def test_document_store_can_compress_raw_html_and_keep_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = DocumentStore(
                raw_html_dir=base / "raw" / "html",
                raw_doc_dir=base / "raw" / "documents",
                curated_doc_dir=base / "curated" / "documents",
                compress_raw_html=True,
                raw_json_html_metadata_only=True,
            )

            saved, _raw_path, html_path = store.save_raw_document(
                {
                    "doc_id": "doc1",
                    "source_type": "notice",
                    "raw_html": "<html><body>compressed</body></html>",
                }
            )

            self.assertTrue(html_path.name.endswith(".html.gz"))
            with gzip.open(html_path, "rt", encoding="utf-8") as f:
                self.assertIn("compressed", f.read())
            self.assertNotIn("raw_html", saved)
            self.assertEqual(saved["raw_html_metadata"]["compressed"], True)


if __name__ == "__main__":
    unittest.main()
