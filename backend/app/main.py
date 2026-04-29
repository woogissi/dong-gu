from fastapi import FastAPI
from backend.app.api.router import api_router
from backend.app.routers import chat

app = FastAPI(
    title="DEU Chatbot API",
    description="동의대학교 챗봇 백엔드 서버",
    version="1.0.0"
)

app.include_router(api_router)
app.include_router(chat.router)

@app.get("/")
def root():
    return {"message": "DEU chatbot backend is running"}