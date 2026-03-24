from app.services.search.hybrid_seach import hybrid_search


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    return hybrid_search(query=query, top_k=top_k)
