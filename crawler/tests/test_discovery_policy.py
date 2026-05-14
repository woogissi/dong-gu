import unittest

from crawler.config.seeds import normalize_seed
from crawler.discovery.board_candidate_policy import (
    board_candidate_reason,
    build_board_candidate_record,
)
from crawler.discovery.url_classifier import URLClassifier


class DiscoveryPolicyTest(unittest.TestCase):
    def test_static_seed_defaults_to_candidate_discovery(self) -> None:
        seed = normalize_seed(
            {
                "name": "deu_home",
                "url": "https://www.deu.ac.kr/www/index.do",
                "source_type": "homepage",
                "page_kind": "static_page",
            }
        )

        self.assertTrue(seed["crawl_enabled"])
        self.assertTrue(seed["discover_board_candidates"])
        self.assertEqual(seed["source_group"], "homepage")

    def test_board_list_seed_does_not_auto_discover_candidates(self) -> None:
        seed = normalize_seed(
            {
                "name": "deu_notice_list",
                "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
                "source_type": "notice",
                "page_kind": "board_list",
            }
        )

        self.assertFalse(seed["discover_board_candidates"])

    def test_board_candidate_policy_accepts_board_list_url(self) -> None:
        classifier = URLClassifier()
        url = "https://www.deu.ac.kr/www/deu-notice.do?mode=list"
        page_kind = classifier.classify(url)

        record = build_board_candidate_record(
            url=url,
            page_kind=page_kind,
            discovered_from="https://www.deu.ac.kr/www/index.do",
            source_type="homepage",
            source_group="homepage",
            depth=1,
        )

        self.assertEqual(page_kind, "board_list")
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "candidate_only")
        self.assertEqual(record["reason"], "board_list")

    def test_board_candidate_policy_ignores_plain_static_page(self) -> None:
        self.assertIsNone(
            board_candidate_reason(
                "https://www.deu.ac.kr/www/deu-bus.do",
                "static_page",
            )
        )
        self.assertIsNone(
            board_candidate_reason(
                "https://www.deu.ac.kr/www/index.do?mode=main",
                "static_page",
            )
        )


if __name__ == "__main__":
    unittest.main()
