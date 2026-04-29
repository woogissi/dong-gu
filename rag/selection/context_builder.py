"""
전달된 문서들의 content 결합
"""

from typing import List
from rag.schemas.retrieved_doc import RetrievedDoc

def build_context(docs: List[RetrievedDoc]) -> str:
    return "\n\n".join(doc.content for doc in docs)