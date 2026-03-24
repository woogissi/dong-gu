from app.services.llm_service import generate_answer
from app.services.retrieval_service import search_documents_by_text


async def run_rag_pipeline(question: str, top_k: int = 3) -> dict:
    search_result = await search_documents_by_text(question, top_k=top_k)
    answer = await generate_answer(question=question, search_results=search_result["results"])
    return {
        "answer": answer,
        "sources": search_result["results"],
    }
