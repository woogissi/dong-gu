from typing import List
from pydantic import BaseModel, Field

from rag.schemas.retrieved_doc import RetrievedDoc


class Answer(BaseModel):
    question: str
    answer: str
    sources: List[RetrievedDoc] = Field(default_factory=list)
    success: bool = True