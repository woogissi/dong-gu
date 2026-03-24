import time

from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.llm_service import generate_answer
from app.services.log_service import save_query_log
from app.services.retrieval_service import search_documents_by_text


async def handle_chat(req: ChatRequest) -> ChatResponse:
    start = time.time()

    search_result = await search_documents_by_text(req.message, top_k=3)
    search_items = search_result["results"]

    answer = await generate_answer(
        question=req.message,
        search_results=search_items,
    )

    elapsed_ms = int((time.time() - start) * 1000)

    sources = [
        ChatSource(
            doc_id=item.get("document_id"),
            title=item.get("title"),
            score=item.get("score"),
            source=item.get("source"),
        )
        for item in search_items
    ]

    await save_query_log(
        user_id=req.user_id,
        session_id=req.session_id,
        question=req.message,
        answer=answer,
        success=True,
        response_time_ms=elapsed_ms,
        sources=[item for item in search_items],
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
        intent="general",
        response_time_ms=elapsed_ms,
    )
