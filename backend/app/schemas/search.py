from typing import Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., description="사용자 검색 질의")
    top_k: int = Field(default=3, ge=1, le=10, description="반환 문서 수")
    use_hybrid: bool = True
    use_rerank: bool = False


class SearchItem(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    title: str
    content: str
    score: float
    source: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchItem]
