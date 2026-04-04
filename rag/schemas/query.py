"""
사용자의 입력을 받는 객체
"""

from pydantic import BaseModel


class Query(BaseModel):
    text: str