import os
import unittest
from dataclasses import dataclass

from rag.preprocess import hybrid_keyword_extractor as hybrid


@dataclass(frozen=True)
class FakeToken:
    form: str
    tag: str


class FakeKiwi:
    tokenize_calls = 0

    def tokenize(self, text: str) -> list[FakeToken]:
        FakeKiwi.tokenize_calls += 1
        if "삼성전자" in text:
            return [
                FakeToken("삼성전자", "NNP"),
                FakeToken("에서", "JKB"),
                FakeToken("발표", "NNG"),
                FakeToken("보고서", "NNG"),
            ]
        if "개인정보보호법" in text:
            return [
                FakeToken("개인정보", "NNG"),
                FakeToken("보호법", "NNG"),
                FakeToken("상", "XSN"),
                FakeToken("의", "JKG"),
                FakeToken("의무", "NNG"),
            ]
        if "카카오" in text:
            return [
                FakeToken("카카오", "NNP"),
                FakeToken("뱅크", "NNG"),
                FakeToken("관련", "NNG"),
                FakeToken("문서", "NNG"),
            ]
        return [FakeToken("후보", "NNG")]


class HybridKeywordExtractorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_kiwi_class = hybrid._KIWI_CLASS
        self._previous_env = {
            hybrid.HYBRID_MODE_ENV: os.environ.get(hybrid.HYBRID_MODE_ENV),
            hybrid.MIN_AHO_MATCHES_ENV: os.environ.get(hybrid.MIN_AHO_MATCHES_ENV),
        }
        hybrid._KIWI_CLASS = FakeKiwi
        FakeKiwi.tokenize_calls = 0
        hybrid.clear_kiwi_cache()

    def tearDown(self) -> None:
        hybrid._KIWI_CLASS = self._previous_kiwi_class
        hybrid.clear_kiwi_cache()
        for name, value in self._previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_auto_mode_skips_kiwi_when_aho_is_sufficient(self) -> None:
        result = hybrid.extract_hybrid_keywords(
            "수강신청 기간",
            aho_keywords=["수강신청"],
            lexical_keywords=["수강신청", "기간"],
            config=hybrid.HybridKeywordConfig(mode="auto", min_aho_matches=1),
        )

        self.assertFalse(result.stats.kiwi_called)
        self.assertEqual(FakeKiwi.tokenize_calls, 0)
        self.assertIn("수강신청", result.keywords)

    def test_hybrid_mode_calls_kiwi_even_when_aho_matches(self) -> None:
        result = hybrid.extract_hybrid_keywords(
            "삼성전자에서 발표한 보고서",
            aho_keywords=["보고서"],
            lexical_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="on", min_aho_matches=1),
        )

        self.assertTrue(result.stats.kiwi_called)
        self.assertIn("삼성전자", result.keywords)

    def test_auto_mode_uses_kiwi_for_aho_miss(self) -> None:
        result = hybrid.extract_hybrid_keywords(
            "삼성전자에서 발표한 보고서",
            aho_keywords=[],
            lexical_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="auto", min_aho_matches=1),
        )

        self.assertTrue(result.stats.kiwi_called)
        self.assertIn("삼성전자", result.keywords)
        self.assertNotIn("보고서", result.keywords)

    def test_kiwi_compound_candidates_handle_particles(self) -> None:
        result = hybrid.extract_hybrid_keywords(
            "개인정보보호법상의 의무",
            aho_keywords=[],
            lexical_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="auto", min_aho_matches=1),
        )

        self.assertIn("개인정보보호법", result.keywords)
        self.assertLess(
            result.keywords.index("개인정보보호법"),
            result.keywords.index("개인정보"),
        )

    def test_kiwi_compacts_spaced_named_entity(self) -> None:
        result = hybrid.extract_hybrid_keywords(
            "카카오 뱅크 관련 문서",
            aho_keywords=[],
            lexical_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="auto", min_aho_matches=1),
        )

        self.assertIn("카카오뱅크", result.keywords)

    def test_kiwi_result_cache_uses_chunk_id_or_hash(self) -> None:
        first = hybrid.extract_hybrid_keywords(
            "삼성전자에서 발표한 보고서",
            aho_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="on"),
            text_id="chunk-1",
        )
        second = hybrid.extract_hybrid_keywords(
            "삼성전자에서 발표한 보고서",
            aho_keywords=[],
            config=hybrid.HybridKeywordConfig(mode="on"),
            text_id="chunk-1",
        )

        self.assertFalse(first.stats.kiwi_cache_hit)
        self.assertTrue(second.stats.kiwi_cache_hit)
        self.assertEqual(FakeKiwi.tokenize_calls, 1)
        self.assertEqual(hybrid.get_kiwi_cache_info()["kiwi_calls"], 1)

    def test_missing_kiwi_falls_back_to_aho_and_lexical(self) -> None:
        hybrid._KIWI_CLASS = None
        hybrid.clear_kiwi_cache()

        result = hybrid.extract_hybrid_keywords(
            "수강신청 기간",
            aho_keywords=["수강신청"],
            lexical_keywords=["기간"],
            config=hybrid.HybridKeywordConfig(mode="on"),
        )

        self.assertFalse(result.stats.kiwi_enabled)
        self.assertFalse(result.stats.kiwi_called)
        self.assertEqual(result.keywords, ["수강신청", "기간"])


if __name__ == "__main__":
    unittest.main()
