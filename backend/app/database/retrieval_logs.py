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

    stage = _retrieval_stage(log_data.get("stage"))
    attempt_no = _int_value(log_data.get("attempt_no"), default=1)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_logs
                (
                    request_id,
                    attempt_no,
                    stage,
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
                ON CONFLICT (request_id, attempt_no, stage) DO UPDATE SET
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
                    context = EXCLUDED.context,
                    success = EXCLUDED.success,
                    error_message = EXCLUDED.error_message,
                    metadata = EXCLUDED.metadata
                RETURNING id;
                """,
                (
                    request_id,
                    attempt_no,
                    stage,
                    log_data.get("original_query") or "",
                    log_data.get("normalized_query") or None,
                    log_data.get("rewritten_query") or None,
                    _text_list(log_data.get("rewritten_queries")),
                    _text_list(log_data.get("keywords")),
                    Json(_json_object(log_data.get("entities"))),
                    Json(_json_object(log_data.get("filters"))),
                    log_data.get("category"),
                    _retrieval_strategy(log_data.get("retrieval_strategy")),
                    _int_value(log_data.get("retrieval_top_k"), default=10),
                    Json(_json_object(log_data.get("retrieval_strategy_log"))),
                    bool(log_data.get("fallback_used", False)),
                    _int_value(log_data.get("retrieved_doc_count")),
                    _int_value(log_data.get("reranked_doc_count")),
                    _int_value(log_data.get("selected_doc_count"), default=len(selected_docs)),
                    log_data.get("context") or None,
                    bool(log_data.get("success", False)),
                    log_data.get("error") or log_data.get("error_message") or None,
                    Json(_json_object(log_data.get("metadata"))),
                ),
            )
            retrieval_log_id = int(cur.fetchone()[0])

            cur.execute(
                "DELETE FROM retrieval_selected_chunks WHERE retrieval_log_id = %s;",
                (retrieval_log_id,),
            )
            for rank, doc in enumerate(selected_docs, start=1):
                if not isinstance(doc, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO retrieval_selected_chunks (
                        retrieval_log_id,
                        chunk_id,
                        raw_chunk_id,
                        doc_id,
                        rank,
                        score,
                        rerank_score,
                        title_snapshot,
                        source_snapshot,
                        content_snapshot,
                        metadata
                    )
                    VALUES (
                        %s,
                        (SELECT chunk_id FROM chunks WHERE chunk_id = %s),
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    );
                    """,
                    (
                        retrieval_log_id,
                        doc.get("chunk_id"),
                        doc.get("chunk_id"),
                        doc.get("doc_id"),
                        rank,
                        _float_value(doc.get("score")),
                        _float_value(doc.get("rerank_score")),
                        doc.get("title") or None,
                        doc.get("source") or doc.get("source_url") or None,
                        doc.get("content") or None,
                        Json(_json_object(doc.get("metadata"))),
                    ),
                )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)


def _retrieval_strategy(value: Any) -> str | None:
    if value in ("vector", "hybrid", "keyword"):
        return value
    if value == "dense":
        return "vector"
    if value in ("lexical", "bm25", "fts"):
        return "keyword"
    return None


def _retrieval_stage(value: Any) -> str:
    if value in ("initial", "fallback", "retry", "rerank"):
        return value
    return "initial"


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


def _float_value(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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
