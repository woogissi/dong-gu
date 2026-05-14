from fastapi import APIRouter
from backend.app.api import chat, health, kakao

# 전체 API 라우터
api_router = APIRouter(prefix="/api")

# 각 기능별 라우터 등록
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(kakao.router, prefix="/kakao", tags=["kakao"])