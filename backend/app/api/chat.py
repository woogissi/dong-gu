from fastapi import APIRouter

from app.schemas.chat import ChatRequest
from app.schemas.common import BaseResponse
from app.services.chat_service import handle_chat

router = APIRouter()


@router.post("/query", response_model=BaseResponse)
async def chat_query(req: ChatRequest):
    result = await handle_chat(req)

    return BaseResponse(
        success=True,
        code="CHAT_SUCCESS",
        message="질문 처리가 완료되었습니다.",
        data=result.model_dump(),
        meta={},
    )
