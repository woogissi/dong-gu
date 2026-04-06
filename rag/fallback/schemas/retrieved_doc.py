from pydantic import BaseModel


class RetrievedDoc(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    score: float = 0.0
    source: str = ""
    title: str = ""