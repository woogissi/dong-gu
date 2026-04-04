"""
rag 검색 문서 metadata 클래스
구조 수정시 retrieval/retriever.py 수정
"""

from pydantic import BaseModel


class RetrievedDoc(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    score: float = 0.0
    source: str = ""
    title: str = ""