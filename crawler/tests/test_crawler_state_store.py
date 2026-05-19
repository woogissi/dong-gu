import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from crawler.run import run_full_pipeline as full_pipeline
from crawler.run import run_static_discovery as static_discovery
from crawler.run.run_rag_load_check import CHECK_SQL, retry_candidate_to_enqueue_args
from crawler.run.run_retry_failed_documents import RetryTarget
from crawler.run.run_full_pipeline import (
    canonical_board_list_seed_key,
    merge_dynamic_board_seeds,
    merge_static_seeds,
    filter_static_seeds_for_recrawl,
    resolve_since_date,
    select_board_seeds_by_names,
    select_static_seeds_by_names,
)
from crawler.run.scan_existing_artifacts import infer_artifact_state
from crawler.state.crawler_state_store import (
    canonicalize_url,
    confidence_for_reason,
    crawler_document_row_to_seed,
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

    def test_crawler_document_row_converts_to_static_seed_shape(self) -> None:
        seed = crawler_document_row_to_seed(
            {
                "id": 3,
                "url": "https://www.deu.ac.kr/www/former-university-presidents.do",
                "source_type": "institution",
                "page_kind": "static_page",
                "discovered_from": "https://www.deu.ac.kr/www/index.do",
                "discovery_depth": 1,
            }
        )

        self.assertEqual(seed["name"], "crawler_document_3")
        self.assertEqual(seed["page_kind"], "static_page")
        self.assertEqual(seed["source_type"], "institution")
        self.assertTrue(seed["crawl_enabled"])
        self.assertTrue(seed["discover_board_candidates"])

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

    def test_merge_static_seeds_adds_promoted_static_urls(self) -> None:
        static_seed = {
            "name": "deu_message",
            "url": "https://www.deu.ac.kr/www/deu-message.do",
            "source_type": "institution",
            "page_kind": "static_page",
        }
        duplicate = {**static_seed, "name": "dynamic_duplicate"}
        promoted = {
            "name": "crawler_document_3",
            "url": "https://www.deu.ac.kr/www/former-university-presidents.do",
            "source_type": "institution",
            "page_kind": "static_page",
        }

        merged = merge_static_seeds([static_seed], [duplicate, promoted])

        self.assertEqual([seed["name"] for seed in merged], ["deu_message", "crawler_document_3"])

    def test_filter_static_seeds_skips_already_parsed_urls(self) -> None:
        state_store = Mock()
        state_store.get_document_states_by_urls.return_value = {
            "https://www.deu.ac.kr/www/deu-message.do": {
                "parse_status": "PARSED",
                "status": "PARSED",
                "updated_at": "2026-05-16T00:00:00+09:00",
            }
        }
        seeds = [
            {
                "name": "deu_message",
                "url": "https://www.deu.ac.kr/www/deu-message.do",
                "source_type": "institution",
                "page_kind": "static_page",
            },
            {
                "name": "deu_former_presidents",
                "url": "https://www.deu.ac.kr/www/former-university-presidents.do",
                "source_type": "institution",
                "page_kind": "static_page",
            },
        ]

        with patch.object(full_pipeline, "CrawlerStateStore", return_value=state_store):
            filtered = filter_static_seeds_for_recrawl(seeds)

        self.assertEqual([seed["name"] for seed in filtered], ["deu_former_presidents"])

    def test_filter_static_seeds_keeps_all_when_force_recrawl(self) -> None:
        seeds = [
            {
                "name": "deu_message",
                "url": "https://www.deu.ac.kr/www/deu-message.do",
                "source_type": "institution",
                "page_kind": "static_page",
            }
        ]

        self.assertEqual(filter_static_seeds_for_recrawl(seeds, force_recrawl=True), seeds)

    def test_select_static_seed_names_can_pick_disabled_catalog_seed(self) -> None:
        selected = select_static_seeds_by_names({"deu_former_presidents"})

        self.assertEqual([seed["name"] for seed in selected], ["deu_former_presidents"])
        self.assertTrue(selected[0]["crawl_enabled"])

    def test_select_board_seed_names_can_pick_disabled_catalog_seed(self) -> None:
        selected = select_board_seeds_by_names({"deu_foundation_notices_list"})

        self.assertEqual([seed["name"] for seed in selected], ["deu_foundation_notices_list"])
        self.assertTrue(selected[0]["crawl_enabled"])

    def test_board_seed_key_ignores_list_paging_query(self) -> None:
        self.assertEqual(
            canonical_board_list_seed_key(
                "https://www.deu.ac.kr/www/deu-education.do?mode=list&&articleLimit=10"
                "&article.offset=70&article.offset=0"
            ),
            "https://www.deu.ac.kr/www/deu-education.do",
        )

    def test_merge_dynamic_board_seeds_dedupes_offset_variants(self) -> None:
        static_seed = {
            "name": "deu_education",
            "url": "https://www.deu.ac.kr/www/deu-education.do?mode=list",
            "source_type": "homepage",
            "page_kind": "board_list",
        }
        dynamic_offset_duplicate = {
            "name": "dynamic_offset_duplicate",
            "url": "https://www.deu.ac.kr/www/deu-education.do?mode=list&&articleLimit=10&article.offset=70",
            "source_type": "homepage",
            "page_kind": "board_list",
        }
        dynamic_bids_offset = {
            "name": "dynamic_bids_offset",
            "url": "https://www.deu.ac.kr/www/deu-bids.do?mode=list&&articleLimit=10&article.offset=70",
            "source_type": "homepage",
            "page_kind": "board_list",
        }
        dynamic_bids_second_offset = {
            "name": "dynamic_bids_second_offset",
            "url": "https://www.deu.ac.kr/www/deu-bids.do?mode=list&&articleLimit=10&article.offset=90",
            "source_type": "homepage",
            "page_kind": "board_list",
        }

        merged = merge_dynamic_board_seeds(
            [static_seed],
            [dynamic_offset_duplicate, dynamic_bids_offset, dynamic_bids_second_offset],
        )

        self.assertEqual([seed["name"] for seed in merged], ["deu_education", "dynamic_bids_offset"])
        self.assertEqual(merged[1]["url"], "https://www.deu.ac.kr/www/deu-bids.do")

    def test_run_board_pipeline_skips_doc_ids_seen_by_previous_seed(self) -> None:
        list_extractor = Mock()
        list_extractor.extract_list.return_value = {
            "list_url": "https://www.deu.ac.kr/www/deu-education.do?mode=list",
            "page_no": 1,
            "count": 1,
            "items": [
                {
                    "article_no": "79937",
                    "detail_url": "https://www.deu.ac.kr/www/deu-education.do?mode=view&articleNo=79937",
                    "title_hint": "title",
                }
            ],
        }
        detail_extractor = Mock()
        detail_extractor.extract_detail.return_value = {
            "doc_id": "deu_homepage_79937",
            "source_type": "homepage",
            "page_kind": "board_detail",
        }
        seen_doc_ids: set[str] = set()

        with patch.object(full_pipeline, "BoardListExtractor", return_value=list_extractor), patch.object(
            full_pipeline, "BoardDetailExtractor", return_value=detail_extractor
        ), patch.object(full_pipeline, "save_document_bundle"), patch.object(full_pipeline, "save_json"), patch.object(
            full_pipeline, "get_existing_processed_doc_ids", return_value=set()
        ):
            full_pipeline.run_board_pipeline(
                source_type="homepage",
                list_url="https://www.deu.ac.kr/www/deu-education.do?mode=list",
                pages=1,
                seen_doc_ids=seen_doc_ids,
            )
            full_pipeline.run_board_pipeline(
                source_type="homepage",
                list_url="https://www.deu.ac.kr/www/deu-education.do?mode=list&article.offset=70",
                pages=1,
                seen_doc_ids=seen_doc_ids,
            )

        detail_extractor.extract_detail.assert_called_once()
        self.assertEqual(seen_doc_ids, {"deu_homepage_79937"})

    def test_run_board_pipeline_skips_existing_processed_doc_ids_before_detail_fetch(self) -> None:
        list_extractor = Mock()
        list_extractor.extract_list.return_value = {
            "list_url": "https://www.deu.ac.kr/www/deu-education.do?mode=list",
            "page_no": 1,
            "count": 1,
            "items": [
                {
                    "article_no": "79937",
                    "detail_url": "https://www.deu.ac.kr/www/deu-education.do?mode=view&articleNo=79937",
                    "title_hint": "title",
                }
            ],
        }
        detail_extractor = Mock()

        with patch.object(full_pipeline, "BoardListExtractor", return_value=list_extractor), patch.object(
            full_pipeline, "BoardDetailExtractor", return_value=detail_extractor
        ), patch.object(full_pipeline, "save_json"), patch.object(
            full_pipeline, "get_existing_processed_doc_ids", return_value={"deu_homepage_79937"}
        ):
            full_pipeline.run_board_pipeline(
                source_type="homepage",
                list_url="https://www.deu.ac.kr/www/deu-education.do?mode=list",
                pages=1,
            )

        detail_extractor.extract_detail.assert_not_called()

    def test_resolve_since_date_uses_recent_lookback_floor(self) -> None:
        resolved = resolve_since_date(
            explicit_since_date=None,
            latest_published_at=None,
            lookback_days=180,
            now=full_pipeline.datetime(2026, 5, 15),
        )

        self.assertEqual(resolved, "2025-11-16")

    def test_resolve_since_date_uses_most_recent_bound(self) -> None:
        resolved = resolve_since_date(
            explicit_since_date="2026-01-01",
            latest_published_at="2026-03-15",
            lookback_days=180,
            now=full_pipeline.datetime(2026, 5, 15),
        )

        self.assertEqual(resolved, "2026-03-15")

    def test_resolve_since_date_can_disable_lookback(self) -> None:
        self.assertIsNone(
            resolve_since_date(
                explicit_since_date=None,
                latest_published_at=None,
                lookback_days=0,
                now=full_pipeline.datetime(2026, 5, 15),
            )
        )

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

    def test_rag_smoke_check_reports_indexed_state(self) -> None:
        self.assertIn("vector_status = 'INDEXED'", CHECK_SQL)
        self.assertIn("'indexed_state'", CHECK_SQL)

    def test_static_discovery_persists_discovered_url_state(self) -> None:
        state_store = Mock()
        state_store.preview_dynamic_seed_promotions.return_value = []
        extractor = Mock()
        extractor.extract_static_page.return_value = {
            "doc_id": "static_1",
            "source_type": "institution",
            "page_kind": "static_page",
            "source_url": "https://www.deu.ac.kr/www/index.do",
            "final_url": "https://www.deu.ac.kr/www/index.do",
            "content_hash": "hash",
            "outgoing_links": [],
            "extractor_name": "static_page",
            "extractor_version": "1",
        }

        with patch.object(static_discovery, "CrawlerStateStore", return_value=state_store), patch.object(
            static_discovery, "StaticPageExtractor", return_value=extractor
        ), patch.object(static_discovery, "save_static_document"), patch.object(
            static_discovery, "iter_enabled_seeds",
            return_value=[
                {
                    "name": "deu_home",
                    "url": "https://www.deu.ac.kr/www/index.do",
                    "source_type": "institution",
                    "page_kind": "static_page",
                    "discover_board_candidates": True,
                }
            ],
        ):
            static_discovery.main(max_pages=1, sleep_seconds=0, promote_discovery_results=True)

        state_store.upsert_discovered_url.assert_called()
        state_store.upsert_document_state.assert_called()
        self.assertEqual(state_store.upsert_document_state.call_args.kwargs["status"], "PARSED")
        state_store.promote_static_seed_candidates.assert_called_once()


if __name__ == "__main__":
    unittest.main()
