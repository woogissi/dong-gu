from typing import Any

from psycopg2.extras import Json

from backend.app.database.db import get_conn, put_conn


def save_retrieval_log(request_id: str, log_data: dict[str, Any] | None) -> None:
    if not request_id or not log_data:
        return

    selected_docs = log_data.get("selected_docs") or []
    selected_chunk_ids = [
        doc.get("chunk_id")
        for doc in selected_docs
        if isinstance(doc, dict) and doc.get("chunk_id")
    ]

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_logs
                (
                    request_id,
                    original_query,
                    normalized_query,
                    rewritten_query,
                    rewritten_queries,
                    keywords,
                    entities,
                    filters,
                    category,
                    retrieval_strategy,
                    retrieval_top_k,
                    retrieval_strategy_log,
                    fallback_used,
                    retrieved_doc_count,
                    reranked_doc_count,
                    selected_doc_count,
                    selected_chunk_ids,
                    selected_documents,
                    context,
                    success,
                    error_message,
                    metadata
                )
                VALUES
                (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (request_id) DO UPDATE SET
                    original_query = EXCLUDED.original_query,
                    normalized_query = EXCLUDED.normalized_query,
                    rewritten_query = EXCLUDED.rewritten_query,
                    rewritten_queries = EXCLUDED.rewritten_queries,
                    keywords = EXCLUDED.keywords,
                    entities = EXCLUDED.entities,
                    filters = EXCLUDED.filters,
                    category = EXCLUDED.category,
                    retrieval_strategy = EXCLUDED.retrieval_strategy,
                    retrieval_top_k = EXCLUDED.retrieval_top_k,
                    retrieval_strategy_log = EXCLUDED.retrieval_strategy_log,
                    fallback_used = EXCLUDED.fallback_used,
                    retrieved_doc_count = EXCLUDED.retrieved_doc_count,
                    reranked_doc_count = EXCLUDED.reranked_doc_count,
                    selected_doc_count = EXCLUDED.selected_doc_count,
                    selected_chunk_ids = EXCLUDED.selected_chunk_ids,
                    selected_documents = EXCLUDED.selected_documents,
                    context = EXCLUDED.context,
                    success = EXCLUDED.success,
                    error_message = EXCLUDED.error_message,
                    metadata = EXCLUDED.metadata;
                """,
                (
                    request_id,
                    log_data.get("original_query") or "",
                    log_data.get("normalized_query") or None,
                    log_data.get("rewritten_query") or None,
                    log_data.get("rewritten_queries") or [],
                    log_data.get("keywords") or [],
                    Json(log_data.get("entities") or {}),
                    Json(log_data.get("filters") or {}),
                    log_data.get("category"),
                    log_data.get("retrieval_strategy") or "lexical",
                    log_data.get("retrieval_top_k") or 10,
                    Json(log_data.get("retrieval_strategy_log") or {}),
                    bool(log_data.get("fallback_used", False)),
                    int(log_data.get("retrieved_doc_count") or 0),
                    int(log_data.get("reranked_doc_count") or 0),
                    int(log_data.get("selected_doc_count") or 0),
                    selected_chunk_ids,
                    Json(selected_docs),
                    log_data.get("context") or None,
                    bool(log_data.get("success", False)),
                    log_data.get("error") or None,
                    Json(log_data.get("metadata") or {}),
                ),
            )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)
