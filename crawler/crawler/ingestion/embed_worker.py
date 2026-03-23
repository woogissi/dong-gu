# crawler/ingestion/embed_worker.py

from typing import List
from sentence_transformers import SentenceTransformer


class EmbeddingWorker:
    def __init__(self, model_name: str = "nlpai-lab/KoE5"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        # KoE5는 prefix 중요함
        text = f"passage: {text}"

        vector = self.model.encode(text, normalize_embeddings=True)

        return vector.tolist()

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        embedded_chunks = []

        texts = [f"passage: {c['content']}" for c in chunks]
        vectors = self.model.encode(texts, normalize_embeddings=True)

        for chunk, vector in zip(chunks, vectors):
            embedded_chunks.append({
                **chunk,
                "embedding": vector.tolist(),
                "embedding_model": self.model_name,
            })

        return embedded_chunks