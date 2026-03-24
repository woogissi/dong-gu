from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.kakao import router as kakao_router
from app.api.search import router as search_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/api/health", tags=["Health"])
api_router.include_router(kakao_router, prefix="/api/kakao", tags=["Kakao"])
api_router.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
api_router.include_router(search_router, prefix="/api/search", tags=["Search"])
api_router.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
