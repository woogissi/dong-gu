"""Retrieval entrypoint.

Week 3 defines the keyword retrieval contract. The actual PostgreSQL FTS
implementation is planned for Week 4, so this function still returns a
deterministic placeholder document for pipeline wiring.
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
