"""Select top documents for answer context."""

from rag.schemas.retrieved_doc import RetrievedDoc


def select_topk(docs: list[RetrievedDoc], k: int = 3) -> list[RetrievedDoc]:
    selected: list[RetrievedDoc] = []
    seen_doc_ids: set[str] = set()

    for doc in docs:
        if doc.doc_id in seen_doc_ids:
            continue
        selected.append(doc)
        seen_doc_ids.add(doc.doc_id)
        if len(selected) >= k:
            break

    return selected
