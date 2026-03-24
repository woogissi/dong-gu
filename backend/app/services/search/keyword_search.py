def keyword_search(query: str, top_k: int = 3) -> list[dict]:
    """
    추후 PostgreSQL Full Text Search 또는 BM25 연결.
    현재는 더미 데이터 반환.
    """
    return [
        {
            "document_id": "doc_notice_001",
            "chunk_id": "chunk_notice_001",
            "title": "예시 공지사항",
            "content": f"'{query}' 관련 키워드 검색 결과 예시입니다.",
            "score": 0.90,
            "source": "deu_notice",
        }
    ][:top_k]
