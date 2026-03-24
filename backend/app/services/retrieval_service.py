from app.schemas.search import SearchRequest
from app.services.search.hybrid_seach import hybrid_search


async def search_documents(req: SearchRequest) -> dict:
    results = hybrid_search(query=req.query, top_k=req.top_k)
    return {
        "query": req.query,
        "results": results,
    }


async def search_documents_by_text(query: str, top_k: int = 3) -> dict:
    results = hybrid_search(query=query, top_k=top_k)
    return {
        "query": query,
        "results": results,
    }
