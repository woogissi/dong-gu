from app.core.logging import get_logger

logger = get_logger(__name__)


async def log_query(
    question: str,
    answer: str,
    user_id: str | None = None,
    session_id: str | None = None,
    success: bool = True,
    response_time_ms: int | None = None,
    sources: list | None = None,
) -> None:
    logger.info(
        {
            "user_id": user_id,
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "success": success,
            "response_time_ms": response_time_ms,
            "sources": sources or [],
        }
    )
