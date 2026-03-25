from fastapi import APIRouter

# 서버 상태 확인용 라우터
router = APIRouter()

@router.get("/")
def health_check():
    return {"status": "ok"}