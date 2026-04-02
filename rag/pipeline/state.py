"""
rag의 전처리~후처리까지의 과정에서 발생하는
데이터들 저장용 추후 db 적재 고려
"""

from dataclasses import dataclass, field
from typing import List

from rag.schemas.retrieved_doc import RetrievedDoc


@dataclass
class PipelineState:
    original_query: str
    normalized_query: str = ""
    rewritten_query: str = ""
    keywords: List[str] = field(default_factory=list)

    retrieved_docs: List[RetrievedDoc] = field(default_factory=list)
    selected_docs: List[RetrievedDoc] = field(default_factory=list)

    context: str = ""
    prompt: str = ""
    answer_text: str = ""

    error: str = ""

    @classmethod
    def from_query(cls, query: str) -> "PipelineState":
        return cls(original_query=query)