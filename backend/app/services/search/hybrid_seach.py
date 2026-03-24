from app.services.search.keyword_search import keyword_search
from app.services.search.vector_search import vector_search


def hybrid_search(query: str, top_k: int = 3) -> list[dict]:
    keyword_results = keyword_search(query=query, top_k=top_k)
    vector_results = vector_search(query=query, top_k=top_k)

    merged = keyword_results + vector_results

    unique_by_doc: dict[str, dict] = {}
    for item in merged:
        key = item["document_id"]
        if key not in unique_by_doc or item["score"] > unique_by_doc[key]["score"]:
            unique_by_doc[key] = item

    sorted_results = sorted(unique_by_doc.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results[:top_k]
