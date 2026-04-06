
from typing import List
from rag.schemas.retrieved_doc import RetrievedDoc

#config로 k 변수 관리 고려
def select_topk(docs: List[RetrievedDoc], k: int = 3) -> List[RetrievedDoc]:
    return docs[:k]