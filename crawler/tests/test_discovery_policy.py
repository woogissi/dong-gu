import unittest

from crawler.config.domains import ALLOWED_HOSTS
from crawler.config.seeds import iter_enabled_seeds, iter_seed_catalog, normalize_seed
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

    def test_required_www_static_menu_pages_are_seeded(self) -> None:
        static_seed_urls = {
            seed["url"]
            for seed in iter_enabled_seeds("static_page")
            if seed["url"].startswith("https://www.deu.ac.kr/www/")
        }

        self.assertIn("https://www.deu.ac.kr/www/deu-message.do", static_seed_urls)
        self.assertIn("https://www.deu.ac.kr/www/deu-student-council.do", static_seed_urls)

    def test_extended_static_seed_catalog_includes_expanded_pages(self) -> None:
        catalog_by_name = {seed["name"]: seed for seed in iter_seed_catalog("static_page")}

        self.assertIn("deu_former_presidents", catalog_by_name)
        self.assertIn("deu_ipsi_university_detail", catalog_by_name)
        self.assertIn("deu_research_ethics_home", catalog_by_name)
        self.assertTrue(catalog_by_name["deu_former_presidents"]["crawl_enabled"])
        self.assertTrue(catalog_by_name["deu_ipsi_university_detail"]["crawl_enabled"])
        self.assertTrue(catalog_by_name["deu_research_ethics_home"]["crawl_enabled"])

    def test_known_www_board_urls_infer_source_type(self) -> None:
        classifier = URLClassifier()

        cases = {
            "https://www.deu.ac.kr/www/deu-scholarship.do?mode=list": "scholarship",
            "https://www.deu.ac.kr/www/deu-education.do?mode=list": "education",
            "https://www.deu.ac.kr/www/deu-job.do?mode=list": "job",
            "https://www.deu.ac.kr/www/deu-support-notice.do?mode=list": "disability_support",
            "https://www.deu.ac.kr/www/deu-bids.do?mode=list": "bids",
            "https://www.deu.ac.kr/www/deu-today.do?mode=list": "news",
            "https://www.deu.ac.kr/www/deu-foundation-notices.do?mode=list": "foundation_notice",
            "https://www.deu.ac.kr/www/deu-council-notice.do?mode=list": "council_notice",
        }

        for url, source_type in cases.items():
            with self.subTest(url=url):
                self.assertEqual(classifier.infer_source_type(url), source_type)

    def test_department_hosts_infer_department_source_type(self) -> None:
        classifier = URLClassifier()

        self.assertEqual(classifier.infer_source_type("https://mse.deu.ac.kr"), "department")
        self.assertEqual(classifier.infer_source_type("https://sw.deu.ac.kr/sw"), "department")

    def test_seed_department_hosts_are_allowed_for_static_discovery(self) -> None:
        self.assertIn("koreanl.deu.ac.kr", ALLOWED_HOSTS)
        self.assertIn("massmedia.deu.ac.kr", ALLOWED_HOSTS)
        self.assertIn("kbeauty.deu.ac.kr", ALLOWED_HOSTS)

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
