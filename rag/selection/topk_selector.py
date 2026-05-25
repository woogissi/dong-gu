"""Select top documents for answer context."""

from rag.preprocess.query_features import ui_noise_hits
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
    selected_doc_counts: dict[str, int] = {}
    prioritized = [*exact, *preferred, *static_late]
    for index, doc in enumerate(prioritized):
        if selected_doc_counts.get(doc.doc_id, 0) >= max_chunks_per_doc:
            rejected.append(_rejection(doc, "duplicate_doc_id_after_priority"))
            continue
        if _would_overfill_source_type(doc, selected, prioritized[index + 1 :], selected_doc_counts, max_chunks_per_doc):
            rejected.append(_rejection(doc, "source_type_diversity"))
            continue
        selected.append(doc)
        selected_doc_counts[doc.doc_id] = selected_doc_counts.get(doc.doc_id, 0) + 1
        if len(selected) >= k:
            break

    if len(selected) < min(k, min_fallback):
        for doc in deduped:
            if selected_doc_counts.get(doc.doc_id, 0) >= max_chunks_per_doc:
                continue
            selected.append(doc)
            selected_doc_counts[doc.doc_id] = selected_doc_counts.get(doc.doc_id, 0) + 1
            if len(selected) >= min(k, min_fallback):
                break

    for doc in deduped:
        if doc not in selected and not any(item["chunk_id"] == doc.chunk_id for item in rejected):
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
    metadata = doc.metadata or {}
    return {
        "doc_id": doc.doc_id,
        "chunk_id": doc.chunk_id,
        "title": doc.title,
        "score": doc.score,
        "source_type": metadata.get("source_type"),
        "section_type": metadata.get("section_type"),
        "section_title": metadata.get("section_title"),
        "source_url": doc.source,
        "rerank_score": metadata.get("rerank_score"),
        "reason": reason,
    }


def _would_overfill_source_type(
    doc: RetrievedDoc,
    selected: list[RetrievedDoc],
    remaining: list[RetrievedDoc],
    selected_doc_counts: dict[str, int],
    max_chunks_per_doc: int,
) -> bool:
    if len(selected) < 2:
        return False
    source_type = _source_type(doc)
    if not source_type:
        return False
    same_type_count = sum(1 for selected_doc in selected if _source_type(selected_doc) == source_type)
    if same_type_count < 2:
        return False
    return any(
        _source_type(candidate) != source_type
        and selected_doc_counts.get(candidate.doc_id, 0) < max_chunks_per_doc
        and not _is_context_contamination_candidate(candidate)
        for candidate in remaining
    )


def _source_type(doc: RetrievedDoc) -> str:
    return str((doc.metadata or {}).get("source_type") or "").strip().lower()


def _has_exact_or_strong_match(doc: RetrievedDoc) -> bool:
    signals = doc.metadata.get("rerank_signals") or {}
    if not isinstance(signals, dict):
        return False
    return (
        _float_signal(signals, "exact_query_match") > 0.0
        or _float_signal(signals, "strong_term_match") >= 0.45
        or _float_signal(signals, "title_match") >= 0.35
        or _float_signal(signals, "section_title_match") >= 0.35
        or _float_signal(signals, "verified_title_boost") > 0.0
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
    return max(ui_hits, ui_noise_hits(f"{doc.title}\n{doc.source}\n{doc.content}")) >= 3


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
    required_entity_match = _float_signal(signals, "required_entity_match")
    verified_title_boost = _float_signal(signals, "verified_title_boost")
    query_family_boost = _float_signal(signals, "query_family_boost")
    strong_term_match = _float_signal(signals, "strong_term_match")
    exact_query_match = _float_signal(signals, "exact_query_match")
    has_required_terms = bool(doc.metadata.get("required_terms"))

    if verified_title_boost > 0.0:
        return False
    if query_family_boost >= 0.6 and heading_relevance <= 0.0 and exact_query_match <= 0.0 and strong_term_match <= 0.45:
        return True
    if has_required_terms and required_entity_match <= 0.0 and heading_relevance <= 0.0:
        return True
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
