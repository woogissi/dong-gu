from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.kakao import router as kakao_router
from app.api.routes.search import router as search_router
from fastapi import FastAPI

app = FastAPI(title="DEU Chatbot API")

app.include_router(health_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(kakao_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "DEU chatbot backend is running"}
