import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg2.extras import Json

from backend.app.database.db import get_conn, put_conn


def save_retrieval_log(request_id: str, log_data: dict[str, Any] | None) -> None:
    if not request_id or not log_data:
        return

    selected_docs = _json_safe(log_data.get("selected_docs") or [])
    if not isinstance(selected_docs, list):
        selected_docs = []

    selected_chunk_ids = [
        str(doc.get("chunk_id"))
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
                    _text_list(log_data.get("rewritten_queries")),
                    _text_list(log_data.get("keywords")),
                    Json(_json_object(log_data.get("entities"))),
                    Json(_json_object(log_data.get("filters"))),
                    log_data.get("category"),
                    log_data.get("retrieval_strategy") or "lexical",
                    _int_value(log_data.get("retrieval_top_k"), default=10),
                    Json(_json_object(log_data.get("retrieval_strategy_log"))),
                    bool(log_data.get("fallback_used", False)),
                    _int_value(log_data.get("retrieved_doc_count")),
                    _int_value(log_data.get("reranked_doc_count")),
                    _int_value(log_data.get("selected_doc_count")),
                    selected_chunk_ids,
                    Json(selected_docs),
                    log_data.get("context") or None,
                    bool(log_data.get("success", False)),
                    log_data.get("error") or None,
                    Json(_json_object(log_data.get("metadata"))),
                ),
            )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _json_object(value: Any) -> dict[str, Any]:
    safe_value = _json_safe(value)
    return safe_value if isinstance(safe_value, dict) else {}


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        as_float = float(value)
        return as_float if math.isfinite(as_float) else None
    if isinstance(value, (datetime, date, UUID)):
        return str(value)
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "dict"):
        return _json_safe(value.dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
