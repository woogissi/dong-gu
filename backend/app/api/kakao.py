from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.kakao_service import handle_kakao

router = APIRouter()


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body = await request.json()
    response = await handle_kakao(body)
    return JSONResponse(content=response)
