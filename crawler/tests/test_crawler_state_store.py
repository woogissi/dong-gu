import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from crawler.run.run_rag_load_check import retry_candidate_to_enqueue_args
from crawler.run.run_retry_failed_documents import RetryTarget
from crawler.run.run_full_pipeline import merge_dynamic_board_seeds
from crawler.run.scan_existing_artifacts import infer_artifact_state
from crawler.state.crawler_state_store import (
    canonicalize_url,
    confidence_for_reason,
    dynamic_seed_row_to_seed,
    json_safe,
)


class CrawlerStateStoreTest(unittest.TestCase):
    def test_canonicalize_url_removes_fragment(self) -> None:
        self.assertEqual(
            canonicalize_url("https://www.deu.ac.kr/www/index.do#content"),
            "https://www.deu.ac.kr/www/index.do",
        )

    def test_confidence_for_board_candidate_reason(self) -> None:
        self.assertEqual(confidence_for_reason("board_list"), 0.9)
        self.assertEqual(confidence_for_reason("board_mode_hint"), 0.85)
        self.assertEqual(confidence_for_reason("board_path_hint"), 0.75)
        self.assertEqual(confidence_for_reason("board_query_hint"), 0.6)
        self.assertEqual(confidence_for_reason(None), 0.0)

    def test_dynamic_seed_row_converts_to_seed_shape(self) -> None:
        seed = dynamic_seed_row_to_seed(
            {
                "id": 12,
                "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
                "confidence": 0.9,
                "source_type": "notice",
                "source_group": "homepage",
                "page_kind": "board_list",
                "pattern_reason": "board_list",
            }
        )

        self.assertEqual(seed["name"], "dynamic_seed_12")
        self.assertEqual(seed["source_type"], "notice")
        self.assertEqual(seed["page_kind"], "board_list")
        self.assertTrue(seed["crawl_enabled"])
        self.assertFalse(seed["discover_board_candidates"])

    def test_infer_artifact_state_prefers_furthest_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw = base / "raw.json"
            curated = base / "curated.json"
            chunks = base / "chunks.json"

            raw.write_text("{}", encoding="utf-8")
            self.assertEqual(infer_artifact_state(raw, curated, chunks), "CRAWLED")

            curated.write_text("{}", encoding="utf-8")
            self.assertEqual(infer_artifact_state(raw, curated, chunks), "PARSED")

            chunks.write_text("[]", encoding="utf-8")
            self.assertEqual(infer_artifact_state(raw, curated, chunks), "CHUNKED")
            self.assertEqual(infer_artifact_state(raw, curated, chunks, embedded=True), "EMBEDDED")

    def test_merge_dynamic_board_seeds_keeps_static_seed_and_adds_new_urls(self) -> None:
        static_seed = {
            "name": "deu_notice",
            "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
            "source_type": "notice",
            "page_kind": "board_list",
        }
        dynamic_duplicate = {**static_seed, "name": "dynamic_duplicate"}
        dynamic_new = {
            "name": "dynamic_1",
            "url": "https://www.deu.ac.kr/www/another-notice.do?mode=list",
            "source_type": "notice",
            "page_kind": "board_list",
        }

        merged = merge_dynamic_board_seeds([static_seed], [dynamic_duplicate, dynamic_new])

        self.assertEqual([seed["name"] for seed in merged], ["deu_notice", "dynamic_1"])

    def test_json_safe_converts_decimal_values(self) -> None:
        self.assertEqual(json_safe({"confidence": Decimal("0.85")}), {"confidence": 0.85})

    def test_retry_target_accepts_queue_fields(self) -> None:
        target = RetryTarget.from_row(
            {
                "id": 7,
                "queue_id": 7,
                "stage": "vector_ingestion",
                "source_type": "notice",
                "doc_id": "doc1",
                "url": "https://www.deu.ac.kr",
                "error_type": "chunked_but_not_embedded",
                "error_message": None,
                "reason": "chunked_but_not_embedded",
                "file_path": "crawler/data/rag_ready/chunks/notice/doc1.json",
            }
        )

        self.assertEqual(target.queue_id, 7)
        self.assertEqual(target.task_type, "vector_ingestion")
        self.assertEqual(target.reason, "chunked_but_not_embedded")
        self.assertEqual(target.file_path, "crawler/data/rag_ready/chunks/notice/doc1.json")

    def test_retry_candidate_to_enqueue_args_preserves_retry_reason(self) -> None:
        args = retry_candidate_to_enqueue_args(
            {
                "doc_id": "doc1",
                "url": "https://www.deu.ac.kr",
                "source_type": "notice",
                "page_kind": "board_detail",
                "file_path": "chunks/notice/doc1.json",
                "stage": "vector_ingestion",
                "reason": "chunked_but_not_embedded",
                "context": {"chunk_id": "chunk1"},
            }
        )

        self.assertEqual(args["stage"], "vector_ingestion")
        self.assertEqual(args["task_type"], "vector_ingestion")
        self.assertEqual(args["reason"], "chunked_but_not_embedded")
        self.assertEqual(args["context"], {"chunk_id": "chunk1"})
        self.assertEqual(args["payload"], {"chunk_id": "chunk1"})


if __name__ == "__main__":
    unittest.main()
