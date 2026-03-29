from fastapi import FastAPI
from backend.app.api.router import api_router

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="DEU Chatbot API",
    description="동의대학교 챗봇 백엔드 서버",
    version="1.0.0"
)

# API 라우터 등록
app.include_router(api_router)

# 서버 상태 확인용 엔드포인트
@app.get("/")
def root():
    return {"message": "DEU chatbot backend is running"}