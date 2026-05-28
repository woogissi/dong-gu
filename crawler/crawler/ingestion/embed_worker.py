# crawler/ingestion/embed_worker.py

from __future__ import annotations

import os
from typing import List

from sentence_transformers import SentenceTransformer


class EmbeddingWorker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "nlpai-lab/KoE5")
        print(
            "[EmbeddingWorker] provider=sentence_transformer "
            f"model={self.model_name} "
            f"openai_api_key_present={bool(os.getenv('OPENAI_API_KEY'))} "
            "openai_api_used=False"
        )
        self.model = SentenceTransformer(self.model_name)

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        vector = self.model.encode(f"passage: {text}", normalize_embeddings=True)
        return vector.tolist()

    def embed_chunks(self, chunks: list[dict], batch_size: int = 32) -> list[dict]:
        texts = [f"passage: {chunk['content']}" for chunk in chunks]
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=batch_size)

        embedded_chunks = []
        for chunk, vector in zip(chunks, vectors):
            embedded_chunks.append(
                {
                    **chunk,
                    "embedding": vector.tolist(),
                    "embedding_model": self.model_name,
                }
            )
        return embedded_chunks
