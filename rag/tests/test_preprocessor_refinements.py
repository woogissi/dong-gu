import unittest
from dataclasses import dataclass

from rag.preprocess import hybrid_keyword_extractor as hybrid
from rag.pipeline.preprocessor import (
    QueryPreprocessor,
    _apply_synonym_filter,
    _build_aho_automaton,
    _longest_non_overlapping_matches,
)
from rag.pipeline.state import PipelineState


@dataclass(frozen=True)
class FakeToken:
    form: str
    tag: str


class FakeKiwi:
    tokenize_calls = 0

    def tokenize(self, text: str) -> list[FakeToken]:
        FakeKiwi.tokenize_calls += 1
        return [
            FakeToken("등록금", "NNG"),
            FakeToken("고지서", "NNG"),
            FakeToken("확인", "VV"),
        ]


class PreprocessorRefinementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_kiwi_class = hybrid._KIWI_CLASS

    def tearDown(self) -> None:
        hybrid._KIWI_CLASS = self._previous_kiwi_class
        hybrid.clear_kiwi_cache()

    def test_synonym_filter_drops_subsumed_terms(self) -> None:
        self.assertEqual(_apply_synonym_filter("장학금 신청"), "장학금 신청 학자금 지원")

    def test_preprocessor_keeps_normalized_query_free_of_synonym_expansion(self) -> None:
        state = PipelineState.from_query("장학금 신청")

        QueryPreprocessor().run(state)

        query_understanding = state.metadata["query_understanding"]
        self.assertEqual(state.normalized_query, "장학금 신청")
        self.assertEqual(query_understanding["embedding_query"], "장학금 신청")
        self.assertEqual(query_understanding["lexical_query"], "장학금 신청 학자금 지원")
        self.assertIn("장학금 신청 학자금 지원", state.rewritten_queries)

    def test_longest_non_overlapping_match_suppresses_shorter_overlap(self) -> None:
        automaton = _build_aho_automaton({"국가장학", "장학금", "신청"})

        matches = _longest_non_overlapping_matches("국가장학금 신청", automaton)

        self.assertEqual(matches, ["국가장학", "신청"])

    def test_preprocessor_reuses_single_kiwi_analysis(self) -> None:
        hybrid._KIWI_CLASS = FakeKiwi
        hybrid.clear_kiwi_cache()
        FakeKiwi.tokenize_calls = 0
        state = PipelineState.from_query("등록금 고지서 확인")

        QueryPreprocessor().run(state)

        self.assertEqual(FakeKiwi.tokenize_calls, 1)
        self.assertEqual(hybrid.get_kiwi_cache_info()["kiwi_calls"], 1)
        self.assertEqual(state.query_bundle["rewrite_entities"], ["등록금", "고지서"])


if __name__ == "__main__":
    unittest.main()
