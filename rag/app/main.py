from fastapi import FastAPI

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query


app = FastAPI(
    title="DEU RAG API",
    description="RAG pipeline service",
    version="1.0.0",
)

chat_pipeline = ChatPipeline()


@app.on_event("startup")
async def startup_event() -> None:
    try:
        chat_pipeline.initialize()
    except Exception as exc:
        print(f"[rag startup] failed to initialize chat pipeline: {exc}")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/rag/chat")
def chat(query: Query) -> dict:
    return chat_pipeline.run(query).model_dump()
