import unittest
from unittest.mock import Mock, patch

from crawler.ingestion.embed_worker import EmbeddingWorker


class FakeVector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class EmbedWorkerTest(unittest.TestCase):
    def test_embedding_worker_exposes_model_name_and_tags_chunks(self) -> None:
        model = Mock()
        model.encode.return_value = [FakeVector([0.1, 0.2])]

        with patch("crawler.ingestion.embed_worker.SentenceTransformer", return_value=model):
            worker = EmbeddingWorker(model_name="test/model")
            embedded = worker.embed_chunks([{"chunk_id": "c1", "content": "hello"}])

        self.assertEqual(worker.model_name, "test/model")
        self.assertEqual(embedded[0]["embedding_model"], "test/model")
        self.assertEqual(embedded[0]["embedding"], [0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
