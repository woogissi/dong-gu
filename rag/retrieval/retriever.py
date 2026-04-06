"""
검색 단일 진입점
재작성된 쿼리, 키워드를 기준으로 검색 전략 적용
검색 방식, 범위, tok-k 개수, fallback 여부 등
검색 결과 RetrievedDoc 형식으로 반환
"""

from typing import List
from rag.schemas.retrieved_doc import RetrievedDoc

def retrieve_documents(query: str, keywords: list[str]) -> List[RetrievedDoc]:
    return [
        RetrievedDoc(
            doc_id="doc-1",
            chunk_id="chunk-1",
            content="테스트 문서 내용입니다.",
            score=0.9,
            source="dummy",
            title="테스트 공지",
        )
    ]