import unittest
from dataclasses import dataclass
import re

from rag.preprocess import normalizer


@dataclass(frozen=True)
class FakeToken:
    form: str
    tag: str
    start: int
    len: int


class FakeKiwi:
    def tokenize(self, text: str) -> list[FakeToken]:
        tokens: list[FakeToken] = []
        for match in re.finditer(r"[0-9A-Za-z가-힣]+", text):
            word = match.group(0)
            tokens.append(FakeToken(word, "NNG", match.start(), len(word)))
        return tokens


class NormalizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_kiwi_class = normalizer._KiwiClass
        normalizer._KiwiClass = FakeKiwi
        normalizer._get_kiwi.cache_clear()

    def tearDown(self) -> None:
        normalizer._KiwiClass = self._previous_kiwi_class
        normalizer._get_kiwi.cache_clear()

    def test_replaces_colloquial_expression_on_token_boundary(self) -> None:
        self.assertEqual(normalizer.normalize_query("어케 신청해?"), "어떻게 신청해?")

    def test_does_not_replace_inside_larger_context(self) -> None:
        self.assertEqual(normalizer.normalize_query("상어케이스 안내"), "상어케이스 안내")

    def test_replaces_eojeol_only_expression_without_substring_noise(self) -> None:
        self.assertEqual(normalizer.normalize_query("신청 기한이야?"), "신청 기한?")
        self.assertEqual(normalizer.normalize_query("기한이야말로 중요"), "기한이야말로 중요")

    def test_compacts_spaced_phrase_with_boundaries(self) -> None:
        self.assertEqual(normalizer.normalize_query("신청 언제 까지 가능해?"), "신청 언제까지 가능해?")

    def test_regex_fallback_keeps_boundary_behavior_when_kiwi_is_unavailable(self) -> None:
        normalizer._KiwiClass = None
        normalizer._get_kiwi.cache_clear()

        self.assertEqual(normalizer.normalize_query("어떡해 확인해?"), "어떻게 확인해?")
        self.assertEqual(normalizer.normalize_query("상어케이스 확인"), "상어케이스 확인")


if __name__ == "__main__":
    unittest.main()
