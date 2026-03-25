from fastapi import APIRouter

# 일반 챗 API
router = APIRouter()

@router.post("/")
def chat():
    return {"message": "chat endpoint working"}