import unittest

from rag.pipeline.preprocessor import (
    QueryPreprocessor,
    _apply_synonym_filter,
    _build_aho_automaton,
    _longest_non_overlapping_matches,
)
from rag.pipeline.state import PipelineState


class PreprocessorRefinementTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
