from __future__ import annotations

from sentence_transformers import SentenceTransformer


class KoE5Embedder:
    """
    KoE5 기반 임베딩 생성기.

    - 단일 문서 임베딩
    - 여러 문서(batch) 임베딩
    - 검색 query 임베딩
    - 벡터 차원 확인
    - 기본 예외 처리
    """

    def __init__(
        self,
        model_name: str = "nlpai-lab/KoE5",
        device: str | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        self.model_name = model_name
        self.normalize_embeddings = normalize_embeddings
        self.model = SentenceTransformer(model_name, device=device)

        dimension = self.model.get_sentence_embedding_dimension()
        self.dimension = int(dimension) if dimension is not None else self._infer_dimension()

    def _infer_dimension(self) -> int:
        test_vector = self.model.encode(
            "passage: test",
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
        )
        return int(test_vector.shape[0])

    def _validate_text(self, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be a string.")
        if not text.strip():
            raise ValueError("text must not be empty.")

    def _validate_text_list(self, text_list: list[str]) -> None:
        if not isinstance(text_list, list):
            raise TypeError("text_list must be a list of strings.")
        if not text_list:
            raise ValueError("text_list must not be empty.")

        for i, text in enumerate(text_list):
            if not isinstance(text, str):
                raise TypeError(f"text_list[{i}] must be a string.")
            if not text.strip():
                raise ValueError(f"text_list[{i}] must not be empty.")

    def _add_passage_prefix(self, text: str) -> str:
        return f"passage: {text.strip()}"

    def _add_query_prefix(self, text: str) -> str:
        return f"query: {text.strip()}"

    def embed_text(self, text: str) -> list[float]:
        """
        단일 문서 텍스트를 임베딩한다.
        """
        self._validate_text(text)

        embedding = self.model.encode(
            self._add_passage_prefix(text),
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
        )

        return embedding.tolist()

    def embed_documents(self, text_list: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        여러 문서 텍스트를 batch 단위로 임베딩한다.
        """
        self._validate_text_list(text_list)

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")

        prefixed_texts = [self._add_passage_prefix(text) for text in text_list]

        embeddings = self.model.encode(
            prefixed_texts,
            batch_size=batch_size,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """
        검색용 query 임베딩.
        retrieval 단계에서 사용.
        """
        self._validate_text(text)

        embedding = self.model.encode(
            self._add_query_prefix(text),
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
        )

        return embedding.tolist()

    def get_dimension(self) -> int:
        """
        임베딩 벡터 차원 수를 반환한다.
        """
        return self.dimension