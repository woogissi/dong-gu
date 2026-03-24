from typing import Any

from pydantic import BaseModel


class KakaoUser(BaseModel):
    id: str | None = None


class KakaoUserRequest(BaseModel):
    utterance: str = ""
    user: KakaoUser | None = None
    conversationId: str | None = None


class KakaoAction(BaseModel):
    params: dict[str, Any] | None = None
