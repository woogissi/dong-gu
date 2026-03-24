from typing import Any

from pydantic import BaseModel


class BaseResponse(BaseModel):
    success: bool
    code: str
    message: str
    data: Any = None
    meta: dict | None = None
