from typing import List
from rag.schemas.retrieved_doc import RetrievedDoc

def select_topk(docs: List[RetrievedDoc], k: int = 3) -> List[RetrievedDoc]:
    return docs[:k]