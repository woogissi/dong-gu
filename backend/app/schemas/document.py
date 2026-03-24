from pydantic import BaseModel


class DocumentSchema(BaseModel):
    doc_id: str
    title: str
    content: str | None = None
    source: str | None = None
    url: str | None = None
