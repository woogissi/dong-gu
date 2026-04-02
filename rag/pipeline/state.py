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

    # 입력 질문
    original_query: str 

    # 전처리 결과
    normalized_query: str = ""
    rewritten_query: str = ""
    keywords: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    category: str | None = None

    # 검색 관련 상태
    retrieval_strategy: str = "hybrid"
    retrieval_top_k: int = 10
    fallback_used: bool = False

    retrieved_docs: list[RetrievedDoc] = field(default_factory=list)
    reranked_docs: list[RetrievedDoc] = field(default_factory=list)
    selected_docs: list[RetrievedDoc] = field(default_factory=list)

    # LLM 입력 구성
    context: str = ""
    prompt: str = ""

    # 최종 생성 결과
    answer_text: str = ""

    # 실행 메타/에러
    success: bool = False
    error: str = ""

    # 로그/추적용 메타데이터
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_query(cls, query: str) -> "PipelineState":
        """
        사용자 질문만으로 초기 PipelineState 생성
        """
        return cls(original_query=query)

    def mark_fallback_used(self) -> None:
        """
        fallback 검색 또는 fallback 응답 사용 여부 표시
        """
        self.fallback_used = True

    def set_category(self, category: str | None) -> None:
        """
        추론된 카테고리 저장
        """
        self.category = category

    def set_keywords(self, keywords: list[str]) -> None:
        """
        추출된 키워드 저장
        """
        self.keywords = keywords

    def set_entities(self, entities: dict[str, Any]) -> None:
        """
        추출된 엔티티 저장
        예:
        {
            "department": "컴퓨터공학과",
            "target": "신입생",
            "topic": "수강신청",
            "attribute": "기간"
        }
        """
        self.entities = entities

    def set_retrieved_docs(self, docs: list[RetrievedDoc]) -> None:
        """
        1차 검색 결과 저장
        """
        self.retrieved_docs = docs

    def set_reranked_docs(self, docs: list[RetrievedDoc]) -> None:
        """
        reranking 결과 저장
        """
        self.reranked_docs = docs

    def set_selected_docs(self, docs: list[RetrievedDoc]) -> None:
        """
        최종 선택된 문서 저장
        """
        self.selected_docs = docs

    def get_active_docs(self) -> list[RetrievedDoc]:
        """
        현재 활성 문서 목록 반환.
        reranked_docs가 있으면 그것을 우선 사용하고,
        없으면 retrieved_docs를 반환.
        """
        if self.reranked_docs:
            return self.reranked_docs
        return self.retrieved_docs

    def mark_success(self) -> None:
        """
        파이프라인 성공 처리
        """
        self.success = True
        self.error = ""

    def mark_failure(self, error: str) -> None:
        """
        파이프라인 실패 처리
        """
        self.success = False
        self.error = error

    def add_metadata(self, key: str, value: Any) -> None:
        """
        로깅/디버깅용 메타데이터 저장
        """
        self.metadata[key] = value

    def to_log_dict(self) -> dict[str, Any]:
        """
        로그 저장용 dict 반환
        """
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "rewritten_query": self.rewritten_query,
            "keywords": self.keywords,
            "entities": self.entities,
            "category": self.category,
            "retrieval_strategy": self.retrieval_strategy,
            "retrieval_top_k": self.retrieval_top_k,
            "fallback_used": self.fallback_used,
            "retrieved_doc_count": len(self.retrieved_docs),
            "reranked_doc_count": len(self.reranked_docs),
            "selected_doc_count": len(self.selected_docs),
            "context": self.context,
            "prompt": self.prompt,
            "answer_text": self.answer_text,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }