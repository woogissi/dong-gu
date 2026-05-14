import unittest

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.topk_selector import select_topk


class TopKSelectorTest(unittest.TestCase):
    def test_select_topk_deduplicates_by_doc_id(self) -> None:
        docs = [
            RetrievedDoc(doc_id="a", chunk_id="a_1", content="first", score=3.0),
            RetrievedDoc(doc_id="a", chunk_id="a_2", content="second", score=2.0),
            RetrievedDoc(doc_id="b", chunk_id="b_1", content="third", score=1.0),
        ]

        selected = select_topk(docs, k=2)

        self.assertEqual([doc.chunk_id for doc in selected], ["a_1", "b_1"])


if __name__ == "__main__":
    unittest.main()
