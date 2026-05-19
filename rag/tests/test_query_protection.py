import unittest

from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.preprocess.primary_intent import PrimaryIntentClassifier


class QueryProtectionTest(unittest.TestCase):
    def test_facility_and_bus_queries_are_info(self) -> None:
        classifier = PrimaryIntentClassifier()

        self.assertEqual(classifier.classify("정보공학관 위치"), "INFO")
        self.assertEqual(classifier.classify("콜라보라운지 운영 시간"), "INFO")
        self.assertEqual(classifier.classify("6-1번 버스 운행 정보"), "INFO")

    def test_rewrite_preserves_bus_number_original_query(self) -> None:
        state = PipelineState.from_query("6-1번 버스 운행 정보")

        QueryPreprocessor().run(state)

        self.assertEqual(state.rewritten_query, "6-1번 버스 운행 정보")
        self.assertIn("6-1번 버스 운행 정보", state.rewritten_queries)
        self.assertFalse(state.metadata["query_understanding"]["rewrite_quality"]["rewrite_preserved"])


if __name__ == "__main__":
    unittest.main()
