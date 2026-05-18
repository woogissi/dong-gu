import os
import unittest

from rag.retrieval import retriever
from rag.schemas.retrieved_doc import RetrievedDoc


class HybridFusionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_score_mode = os.environ.get("HYBRID_SCORE_MODE")
        self._previous_srrf_beta = os.environ.get("HYBRID_SRRF_BETA")

    def tearDown(self) -> None:
        self._restore_env("HYBRID_SCORE_MODE", self._previous_score_mode)
        self._restore_env("HYBRID_SRRF_BETA", self._previous_srrf_beta)

    def test_srrf_uses_score_distribution_not_only_rank(self) -> None:
        os.environ["HYBRID_SCORE_MODE"] = "srrf"
        os.environ["HYBRID_SRRF_BETA"] = "10"

        lexical_docs = [
            self._doc("a", 0.90, "lexical_norm_score"),
            self._doc("b", 0.89, "lexical_norm_score"),
            self._doc("c", 0.10, "lexical_norm_score"),
        ]
        vector_docs = [
            self._doc("c", 0.90, "vector_score"),
            self._doc("a", 0.89, "vector_score"),
            self._doc("b", 0.10, "vector_score"),
        ]

        candidates = retriever.merge_retrieval_candidates(lexical_docs, vector_docs)

        self.assertEqual(candidates[0].chunk_id, "a")
        self.assertEqual(candidates[0].document.metadata["hybrid_score_mode"], "srrf")
        self.assertEqual(candidates[0].document.metadata["srrf_beta"], 10.0)
        self.assertGreater(
            candidates[0].document.metadata["srrf_score"],
            candidates[1].document.metadata["srrf_score"],
        )

    def test_srrf_converges_toward_rrf_with_high_beta(self) -> None:
        os.environ["HYBRID_SCORE_MODE"] = "srrf"
        os.environ["HYBRID_SRRF_BETA"] = "1000"

        lexical_docs = [
            self._doc("a", 0.90, "lexical_norm_score"),
            self._doc("b", 0.89, "lexical_norm_score"),
        ]
        vector_docs = [
            self._doc("b", 0.90, "vector_score"),
            self._doc("a", 0.89, "vector_score"),
        ]

        candidates = retriever.merge_retrieval_candidates(lexical_docs, vector_docs)

        for candidate in candidates:
            self.assertAlmostEqual(candidate.final_score, candidate.rrf_score, places=3)

    def _doc(self, chunk_id: str, score: float, score_key: str) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id=f"doc-{chunk_id}",
            chunk_id=chunk_id,
            content=f"content {chunk_id}",
            score=score,
            metadata={score_key: score},
        )

    def _restore_env(self, key: str, previous_value: str | None) -> None:
        if previous_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous_value


if __name__ == "__main__":
    unittest.main()
