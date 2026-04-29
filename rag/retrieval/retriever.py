"""문서 검색기 (Retriever)
- 검색 전략에서 생성된 검색 요청을 받아서, 실제 검색 시스템과 통신하여 문서를 검색하는 역할
- 현재는 더미 구현으로, 고정된 문서 하나를 반환하도록 되어 있음
"""

from typing import List

from rag.schemas.retrieval import RetrievalRequest
from rag.schemas.retrieved_doc import RetrievedDoc


def retrieve_documents(
    query: str | None = None,
    keywords: list[str] | None = None,
    request: RetrievalRequest | None = None,
) -> List[RetrievedDoc]:
    if request is None:
        request = RetrievalRequest(
            query=query or "",
            query_variants=[query] if query else [],
            keywords=keywords or [],
        )

    if "empty_query" in request.fallback_triggers:
        return []

    return [
        RetrievedDoc(
            doc_id="doc-1",
            chunk_id="chunk-1",
            content="테스트 문서 내용입니다.",
            score=0.9,
            source="dummy",
            title="테스트 공지",
            category=request.category,
            metadata={
                "strategy": request.strategy,
                "query": request.query,
                "keywords": request.keywords,
                "filters": request.filters,
            },
        )
    ][: request.top_k]
