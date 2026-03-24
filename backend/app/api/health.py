from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("")
def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
    }


@router.get("/detail")
def health_detail():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "debug": settings.DEBUG,
        "db_configured": bool(settings.DATABASE_URL),
        "openai_configured": bool(settings.OPENAI_API_KEY),
    }
