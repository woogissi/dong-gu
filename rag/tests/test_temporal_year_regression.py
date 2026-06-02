import unittest

from rag.retrieval.temporal import temporal_rerank_signals, validate_temporal_evidence
from rag.schemas.retrieved_doc import RetrievedDoc


class TemporalYearRegressionTest(unittest.TestCase):
    """연도 토큰이 int로 들어와도 `'in <string>' requires string as left operand, not int`
    예외가 발생하지 않아야 한다(보고서 q019 버그 회귀 방지).
    """

    def _doc(self) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id="sched-1",
            chunk_id="sched-1-chunk-1",
            title="2025학년도 학사일정",
            content="2025년 1학기 개강일은 3월 2일입니다.",
            source="https://example.com/schedule",
        )

    def test_temporal_rerank_signals_accepts_int_years(self) -> None:
        signals = {"years": [2025], "semesters": [1], "recency_intent": False}

        result = temporal_rerank_signals(self._doc(), signals)

        # int 연도가 문자열로 정규화되어 문서 연도와 매칭되어야 한다.
        self.assertGreater(result["temporal_match"], 0.0)

    def test_validate_temporal_evidence_accepts_int_years(self) -> None:
        signals = {"years": [2025], "semesters": [1]}

        validation = validate_temporal_evidence([self._doc()], signals)

        self.assertTrue(validation["valid"])
        self.assertTrue(validation["matched"])


if __name__ == "__main__":
    unittest.main()
