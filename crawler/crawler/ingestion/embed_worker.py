# crawler/ingestion/embed_worker.py



from typing import List                                                 # 타입 힌트용
from sentence_transformers import SentenceTransformer                   # 임베딩 모델


class EmbeddingWorker:
    def __init__(self, model_name: str = "nlpai-lab/KoE5"):             # 모델명 : "nlpai-lab/KoE5"
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)                    # 모델 로드

    def embed_text(self, text: str) -> List[float]:                     # 단일 텍스트 하나를 임베딩 벡터로 바꾸는 함수
        if not text or not text.strip():                                # 비어있거나 공백 뿐인지 검사
            raise ValueError("Cannot embed empty text")

        # KoE5는 prefix 중요함
        text = f"passage: {text}"                                       # query용은 query: / 문서/패시지용은 passage:

        vector = self.model.encode(text, normalize_embeddings=True)     # 임베딩 생성

        return vector.tolist()                                          # numpy배열에서 python 기본 리스트로 변환

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:           # chunk 여러 개를 한 번에 임베딩하는 함수
        embedded_chunks = []

        texts = [f"passage: {c['content']}" for c in chunks]            # 각 chunk의 content를 꺼내서 전부 passage: prefix를 붙임
        vectors = self.model.encode(texts, normalize_embeddings=True)   # 임베딩 생성

        for chunk, vector in zip(chunks, vectors):                      # 첫번째 청크와 첫번째 벡터끼리 묶기
            embedded_chunks.append({
                **chunk,                                                # 기본 청크의 필드를 그대로 넣어두기
                "embedding": vector.tolist(),                           # 실제 벡터값
                "embedding_model": self.model_name,                     # 어떤 모델인지 기입
            })

        return embedded_chunks