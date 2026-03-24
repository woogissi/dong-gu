def vector_search(query: str, top_k: int = 3) -> list[dict]:
    """
    추후 pgvector 기반 유사도 검색 연결.
    현재는 더미 데이터 반환.
    """
    return [
        {
            "document_id": "doc_vector_001",
            "chunk_id": "chunk_vector_001",
            "title": "벡터 검색 예시 문서",
            "content": f"'{query}' 관련 벡터 검색 결과 예시입니다.",
            "score": 0.85,
            "source": "vector_index",
        }
    ][:top_k]
