from fastapi import FastAPI
from backend.app.api.router import api_router

app = FastAPI(
    title="DEU Chatbot API",
    description="동의대학교 챗봇 백엔드 서버",
    version="1.0.0"
)

app.include_router(api_router)

@app.on_event("startup")
async def startup_event() -> None:
    from backend.app.api.kakao import get_chat_pipeline

    try:
        get_chat_pipeline().initialize()
    except Exception as exc:
        print(f"[startup] failed to initialize chat pipeline: {exc}")

@app.get("/")
def root():
    return {"message": "DEU chatbot backend is running"}
