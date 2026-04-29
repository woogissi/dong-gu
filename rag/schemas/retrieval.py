"""요청/응답 스키마
- 검색 요청과 응답의 구조를 정의하는 Pydantic 모델
- 검색 요청에는 쿼리, 키워드, 필터, 카테고리, 검색 전략, top_k, fallback 트리거 등이 포함됨
- 검색 응답에는 검색 요청, 검색된 문서 목록, fallback 사용 여부, 로그 필드 등이 포함됨
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rag.schemas.retrieved_doc import RetrievedDoc

SearchStrategy = Literal["lexical", "dense", "hybrid"]


class RetrievalRequest(BaseModel):
    query: str
    query_variants: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    category: str | None = None
    strategy: SearchStrategy = "lexical"
    top_k: int = 10
    fallback_triggers: list[str] = Field(default_factory=list)
    log_fields: dict[str, object] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    request: RetrievalRequest
    documents: list[RetrievedDoc] = Field(default_factory=list)
    fallback_used: bool = False
    log_fields: dict[str, object] = Field(default_factory=dict)
