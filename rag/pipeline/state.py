"""
RAG 파이프라인 전체 실행 상태를 저장하는 객체.

역할:
- 사용자 원본 질문부터 최종 답변까지 중간 결과를 보관
- 각 단계(preprocess, retrieval, selection, prompt, generation)의 출력 저장
- 디버깅, 로깅, 예외 처리, fallback 여부 추적
"""


from dataclasses import dataclass, field
from typing import Any

from rag.schemas.retrieved_doc import RetrievedDoc

@dataclass
class PipelineState:
    original_query: str

    normalized_query: str = ""
    rewritten_query: str = ""
    rewritten_queries: list[str] = field(default_factory=list)
    query_bundle: dict[str, Any] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, list[str]] = field(default_factory=dict)
    category: str | None = None
    query_vector: list[float] = field(default_factory=list)

    retrieval_strategy: str = "lexical"
    retrieval_top_k: int = 10
    fallback_used: bool = False

    retrieved_docs: list[RetrievedDoc] = field(default_factory=list)
    reranked_docs: list[RetrievedDoc] = field(default_factory=list)
    selected_docs: list[RetrievedDoc] = field(default_factory=list)

    context: str = ""
    prompt: str = ""
    answer_text: str = ""

    success: bool = False
    error: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_query(cls, query: str) -> "PipelineState":
        return cls(original_query=query)

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "rewritten_query": self.rewritten_query,
            "rewritten_queries": self.rewritten_queries,
            "query_bundle": self.query_bundle,
            "keywords": self.keywords,
            "entities": self.entities,
            "filters": self.filters,
            "category": self.category,
            "retrieval_strategy": self.retrieval_strategy,
            "retrieval_top_k": self.retrieval_top_k,
            "retrieval_strategy_log": self.metadata.get("retrieval_strategy_log", {}),
            "fallback_used": self.fallback_used,
            "retrieved_doc_count": len(self.retrieved_docs),
            "reranked_doc_count": len(self.reranked_docs),
            "selected_doc_count": len(self.selected_docs),
            "selected_docs": [
                doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
                for doc in self.selected_docs
            ],
            "context": self.context,
            "prompt": self.prompt,
            "answer_text": self.answer_text,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }
