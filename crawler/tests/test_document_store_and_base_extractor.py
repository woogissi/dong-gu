import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from crawler.extractors.base import BaseExtractor, GenericExtractor
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


if __name__ == "__main__":
    unittest.main()
