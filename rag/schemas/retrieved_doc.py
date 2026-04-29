"""검색된 문서 스키마
- 검색 시스템에서 반환된 문서의 구조 정의
"""

from pydantic import BaseModel, Field

class RetrievedDoc(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    score: float = 0.0

    title: str = ""
    source: str = ""
    category: str | None = None

    metadata: dict = Field(default_factory=dict)