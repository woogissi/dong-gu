"""Retrieval request/response contracts shared by strategy and retrievers."""

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
