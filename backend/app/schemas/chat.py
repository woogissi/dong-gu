from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    channel: str = "internal"
    message: str = Field(..., min_length=1)


class ChatSource(BaseModel):
    doc_id: Optional[str] = None
    title: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = []
    intent: Optional[str] = None
    response_time_ms: Optional[int] = None
