from typing import List
from rag.schemas.retrieved_doc import RetrievedDoc

def retrieve_documents(query: str, keywords: list[str]) -> List[RetrievedDoc]:
    return [
        RetrievedDoc(
            doc_id="doc-1",
            chunk_id="chunk-1",
            content="테스트 문서 내용입니다.",
            score=0.9,
            source="dummy",
            title="테스트 공지",
        )
    ]