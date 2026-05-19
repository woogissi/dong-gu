"""Select top documents for answer context."""

from rag.schemas.retrieved_doc import RetrievedDoc


def select_topk(docs: list[RetrievedDoc], k: int = 3, min_fallback: int = 1) -> list[RetrievedDoc]:
    return select_topk_with_diagnostics(docs, k=k, min_fallback=min_fallback)["selected"]


def select_topk_with_diagnostics(
    docs: list[RetrievedDoc],
    k: int = 3,
    min_fallback: int = 1,
    max_chunks_per_doc: int = 1,
) -> dict:
    deduped: list[RetrievedDoc] = []
    seen_doc_ids: set[str] = set()
    seen_chunk_ids: set[str] = set()
    rejected: list[dict] = []

    for doc in docs:
        if doc.chunk_id in seen_chunk_ids:
            rejected.append(_rejection(doc, "duplicate_chunk_id"))
            continue
        if max_chunks_per_doc == 1 and doc.doc_id in seen_doc_ids:
            rejected.append(_rejection(doc, "duplicate_doc_id"))
            continue
        seen_chunk_ids.add(doc.chunk_id)
        deduped.append(doc)
        seen_doc_ids.add(doc.doc_id)

    exact = [doc for doc in deduped if _has_exact_or_strong_match(doc) and not _is_context_contamination_candidate(doc)]
    preferred = [
        doc
        for doc in deduped
        if doc not in exact and not _is_context_contamination_candidate(doc) and not _is_static_or_menu_candidate(doc)
    ]
    static_late = [
        doc
        for doc in deduped
        if doc not in exact and doc not in preferred and not _is_context_contamination_candidate(doc)
    ]
    for doc in deduped:
        if _is_context_contamination_candidate(doc):
            rejected.append(_rejection(doc, "context_contamination"))

    selected: list[RetrievedDoc] = []
    selected_ids: set[str] = set()
    for doc in [*exact, *preferred, *static_late]:
        if doc.doc_id in selected_ids:
            rejected.append(_rejection(doc, "duplicate_doc_id_after_priority"))
            continue
        selected.append(doc)
        selected_ids.add(doc.doc_id)
        if len(selected) >= k:
            break

    if len(selected) < min(k, min_fallback):
        for doc in deduped:
            if doc.doc_id in selected_ids:
                continue
            selected.append(doc)
            selected_ids.add(doc.doc_id)
            if len(selected) >= min(k, min_fallback):
                break

    for doc in deduped:
        if doc.doc_id not in selected_ids and not any(item["chunk_id"] == doc.chunk_id for item in rejected):
            rejected.append(_rejection(doc, "not_selected_topk_limit"))

    return {
        "selected": selected[:k],
        "rejected_chunks": rejected,
        "selection_policy": {
            "k": k,
            "min_fallback": min_fallback,
            "max_chunks_per_doc": max_chunks_per_doc,
            "exact_match_preserved": len(exact),
        },
    }


def _rejection(doc: RetrievedDoc, reason: str) -> dict:
    return {
        "doc_id": doc.doc_id,
        "chunk_id": doc.chunk_id,
        "title": doc.title,
        "score": doc.score,
        "reason": reason,
    }


def _has_exact_or_strong_match(doc: RetrievedDoc) -> bool:
    signals = doc.metadata.get("rerank_signals") or {}
    if not isinstance(signals, dict):
        return False
    return (
        _float_signal(signals, "exact_query_match") > 0.0
        or _float_signal(signals, "strong_term_match") >= 0.45
        or _float_signal(signals, "title_match") >= 0.35
        or _float_signal(signals, "section_title_match") >= 0.35
    )


def _is_static_or_menu_candidate(doc: RetrievedDoc) -> bool:
    metadata = doc.metadata or {}
    source_type = str(metadata.get("source_type") or "").lower()
    source = (doc.source or "").lower()
    section_title = str(metadata.get("section_title") or "").lower()
    content = (doc.content or "").lower()
    if source_type in {"static", "index", "menu"}:
        return True
    if any(marker in source for marker in ("index.do", "main.do", "/main", "sitemap")):
        return True
    if section_title in {"menu", "navigation", "breadcrumb"}:
        return True
    ui_hits = sum(1 for marker in ("more", "본문 바로가기", "사이트맵", "로그인", "회원가입", "sns", "바로가기") if marker in content)
    return ui_hits >= 3


def _is_context_contamination_candidate(doc: RetrievedDoc) -> bool:
    signals = doc.metadata.get("rerank_signals") or {}
    if not isinstance(signals, dict):
        return False

    heading_relevance = _float_signal(signals, "title_match") + _float_signal(signals, "section_title_match")
    semantic_relevance = (
        heading_relevance
        + _float_signal(signals, "content_match")
        + _float_signal(signals, "strong_term_match")
        + _float_signal(signals, "exact_query_match")
        + _float_signal(signals, "query_family_boost")
        + _float_signal(signals, "category_match")
    )
    noise_score = _float_signal(signals, "noise_score")

    if noise_score >= 0.8 and _float_signal(signals, "query_family_penalty") < 0.0:
        return True
    if noise_score >= 1.5 and heading_relevance <= 0.0:
        return True
    if noise_score >= 2.0 and semantic_relevance < 1.2:
        return True
    return False


def _float_signal(signals: dict, key: str) -> float:
    try:
        return float(signals.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0
