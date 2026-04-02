"""
rag pipeline 최종 답변 형식
db, kakao json 형식 고려해서 수정
"""

from typing import List
from pydantic import BaseModel, Field

from rag.schemas.retrieved_doc import RetrievedDoc


class Answer(BaseModel):
    question: str
    answer: str
    sources: List[RetrievedDoc] = Field(default_factory=list)
    success: bool = True