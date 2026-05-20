from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
REPORT_PATH = ROOT / "reports" / "supabase_log_quality_evaluation.json"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    return value


def fetch_all(cur: psycopg2.extensions.cursor, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return [clean(dict(row)) for row in cur.fetchall()]


def fetch_one(cur: psycopg2.extensions.cursor, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = fetch_all(cur, sql, params)
    return rows[0] if rows else {}


def main() -> None:
    load_env(ENV_PATH)
    database_url = (os.getenv("DATABASE_URL") or os.getenv("CRAWLER_DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL or CRAWLER_DATABASE_URL is required")

    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '30s';")
            cur.execute("SET TRANSACTION READ ONLY;")

            report: dict[str, Any] = {}
            report["generated_at"] = datetime.now().isoformat(timespec="seconds")

            report["table_counts"] = fetch_all(
                cur,
                """
                SELECT 'query_logs' AS table_name, count(*)::int AS row_count, min(created_at) AS first_at, max(created_at) AS last_at FROM query_logs
                UNION ALL
                SELECT 'response_logs', count(*)::int, min(created_at), max(created_at) FROM response_logs
                UNION ALL
                SELECT 'retrieval_logs', count(*)::int, min(created_at), max(created_at) FROM retrieval_logs
                UNION ALL
                SELECT 'retrieval_selected_chunks', count(*)::int, min(created_at), max(created_at) FROM retrieval_selected_chunks
                UNION ALL
                SELECT 'crawl_logs', count(*)::int, min(created_at), max(created_at) FROM crawl_logs
                UNION ALL
                SELECT 'documents', count(*)::int, min(created_at), max(created_at) FROM documents
                UNION ALL
                SELECT 'chunks', count(*)::int, min(created_at), max(created_at) FROM chunks
                UNION ALL
                SELECT 'chunk_embeddings', count(*)::int, min(created_at), max(created_at) FROM chunk_embeddings
                ORDER BY table_name;
                """,
            )

            report["answer_quality"] = fetch_one(
                cur,
                """
                WITH latest_retrieval AS (
                    SELECT DISTINCT ON (request_id) *
                    FROM retrieval_logs
                    ORDER BY request_id, created_at DESC, id DESC
                ),
                joined AS (
                    SELECT
                        q.request_id,
                        q.intent_type,
                        q.question,
                        q.created_at,
                        r.answer_text,
                        r.success AS response_success,
                        r.error_message AS response_error,
                        r.response_time_ms,
                        lr.id AS retrieval_log_id,
                        lr.success AS retrieval_success,
                        lr.retrieved_doc_count,
                        lr.selected_doc_count,
                        lr.fallback_used
                    FROM query_logs q
                    LEFT JOIN response_logs r ON r.request_id = q.request_id
                    LEFT JOIN latest_retrieval lr ON lr.request_id = q.request_id
                )
                SELECT
                    count(*)::int AS total_queries,
                    count(*) FILTER (WHERE intent_type = 'INFO')::int AS info_queries,
                    count(*) FILTER (WHERE intent_type = 'GENERAL')::int AS general_queries,
                    count(*) FILTER (WHERE intent_type = 'PROFANITY')::int AS profanity_queries,
                    count(*) FILTER (WHERE answer_text IS NULL OR btrim(answer_text) = '')::int AS empty_answers,
                    count(*) FILTER (WHERE response_success IS false)::int AS response_failures,
                    count(*) FILTER (WHERE response_error IS NOT NULL)::int AS response_errors,
                    count(*) FILTER (
                        WHERE answer_text ILIKE ANY(ARRAY[
                            '%찾을 수 없%',
                            '%제공된 문서에서%',
                            '%이해하지 못%',
                            '%죄송%',
                            '%문서에 관련 정보%',
                            '%정보가 없습니다%'
                        ])
                    )::int AS non_committal_answers,
                    round(avg(response_time_ms)::numeric, 1) AS avg_response_time_ms,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95_response_time_ms,
                    count(*) FILTER (WHERE intent_type = 'INFO' AND retrieval_log_id IS NULL)::int AS info_without_retrieval_log,
                    count(*) FILTER (WHERE intent_type = 'INFO' AND coalesce(retrieved_doc_count, 0) = 0)::int AS info_zero_retrieved,
                    count(*) FILTER (WHERE intent_type = 'INFO' AND coalesce(selected_doc_count, 0) = 0)::int AS info_zero_selected,
                    count(*) FILTER (WHERE intent_type = 'INFO' AND fallback_used)::int AS info_fallback_used,
                    min(created_at) AS first_query_at,
                    max(created_at) AS last_query_at
                FROM joined;
                """,
            )

            report["rag_pipeline"] = fetch_one(
                cur,
                """
                SELECT
                    count(*)::int AS retrieval_attempts,
                    count(*) FILTER (WHERE success)::int AS successful_attempts,
                    count(*) FILTER (WHERE NOT success)::int AS failed_attempts,
                    count(*) FILTER (WHERE fallback_used)::int AS fallback_attempts,
                    round(avg(retrieved_doc_count)::numeric, 2) AS avg_retrieved_docs,
                    round(avg(reranked_doc_count)::numeric, 2) AS avg_reranked_docs,
                    round(avg(selected_doc_count)::numeric, 2) AS avg_selected_docs,
                    count(*) FILTER (WHERE coalesce(retrieved_doc_count, 0) = 0)::int AS zero_retrieved_attempts,
                    count(*) FILTER (WHERE coalesce(selected_doc_count, 0) = 0)::int AS zero_selected_attempts
                FROM retrieval_logs;
                """,
            )

            report["retrieval_by_strategy"] = fetch_all(
                cur,
                """
                SELECT
                    coalesce(retrieval_strategy::text, 'unknown') AS retrieval_strategy,
                    count(*)::int AS attempts,
                    count(*) FILTER (WHERE success)::int AS successes,
                    count(*) FILTER (WHERE fallback_used)::int AS fallback_attempts,
                    round(avg(retrieved_doc_count)::numeric, 2) AS avg_retrieved,
                    round(avg(selected_doc_count)::numeric, 2) AS avg_selected
                FROM retrieval_logs
                GROUP BY retrieval_strategy
                ORDER BY attempts DESC;
                """,
            )

            report["selected_chunk_integrity"] = fetch_one(
                cur,
                """
                SELECT
                    count(*)::int AS selected_rows,
                    count(*) FILTER (WHERE rsc.raw_chunk_id IS NOT NULL)::int AS raw_chunk_refs,
                    count(*) FILTER (WHERE rsc.content_snapshot IS NOT NULL)::int AS content_snapshots,
                    count(*) FILTER (WHERE rsc.chunk_id IS NULL)::int AS null_chunk_refs,
                    count(*) FILTER (WHERE c.chunk_id IS NULL)::int AS missing_chunk_rows,
                    count(*) FILTER (WHERE d.doc_id IS NULL)::int AS missing_document_rows,
                    round(avg(rsc.score)::numeric, 4) AS avg_score,
                    round(avg(rsc.rerank_score)::numeric, 4) AS avg_rerank_score
                FROM retrieval_selected_chunks rsc
                LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
                LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id);
                """,
            )

            report["source_data"] = fetch_one(
                cur,
                """
                SELECT
                    (SELECT count(*)::int FROM documents) AS documents,
                    (SELECT count(*)::int FROM document_contents) AS document_contents,
                    (SELECT count(*)::int FROM chunks) AS chunks,
                    (SELECT count(*)::int FROM chunk_embeddings) AS chunk_embeddings,
                    (SELECT count(*)::int FROM documents d LEFT JOIN chunks c ON c.doc_id = d.doc_id WHERE c.id IS NULL) AS documents_without_chunks,
                    (SELECT count(*)::int FROM chunks c LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id WHERE e.id IS NULL) AS chunks_without_embeddings,
                    (SELECT count(*)::int FROM documents d LEFT JOIN document_contents dc ON dc.doc_id = d.doc_id WHERE dc.id IS NULL) AS documents_without_contents,
                    (SELECT count(*)::int FROM document_assets a LEFT JOIN document_contents dc ON dc.asset_id = a.id WHERE dc.id IS NULL) AS assets_without_extracted_content,
                    (SELECT count(*)::int FROM chunks WHERE content_length < 120) AS very_short_chunks_lt_120,
                    (SELECT count(*)::int FROM chunks WHERE content_length > 2500) AS very_long_chunks_gt_2500
                ;
                """,
            )

            report["top_source_domains"] = fetch_all(
                cur,
                """
                SELECT
                    coalesce(substring(source_url from 'https?://([^/]+)'), 'unknown') AS domain,
                    count(*)::int AS documents,
                    count(*) FILTER (WHERE source_url ILIKE '%kbeauty.deu.ac.kr%')::int AS kbeauty_documents
                FROM documents
                GROUP BY domain
                ORDER BY documents DESC
                LIMIT 20;
                """,
            )

            report["specific_source_domains"] = fetch_all(
                cur,
                """
                SELECT
                    domain,
                    count(*)::int AS documents,
                    count(c.id)::int AS chunks,
                    count(e.id)::int AS embeddings,
                    min(d.created_at) AS first_document_at,
                    max(d.created_at) AS last_document_at
                FROM (
                    SELECT 'kbeauty.deu.ac.kr' AS domain
                ) target
                LEFT JOIN documents d ON d.source_url ILIKE ('%' || target.domain || '%')
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
                GROUP BY domain
                ORDER BY domain;
                """,
            )

            report["crawl_errors"] = fetch_all(
                cur,
                """
                SELECT
                    coalesce(stage, 'unknown') AS stage,
                    coalesce(error_type, 'unknown') AS error_type,
                    count(*)::int AS errors,
                    max(created_at) AS last_seen_at,
                    left(max(error_message), 240) AS sample_error
                FROM crawl_logs
                WHERE error_type IS NOT NULL OR error_message IS NOT NULL
                GROUP BY stage, error_type
                ORDER BY errors DESC, last_seen_at DESC
                LIMIT 30;
                """,
            )

            report["recent_low_quality_cases"] = fetch_all(
                cur,
                """
                WITH latest_retrieval AS (
                    SELECT DISTINCT ON (request_id) *
                    FROM retrieval_logs
                    ORDER BY request_id, created_at DESC, id DESC
                ),
                selected AS (
                    SELECT
                        retrieval_log_id,
                        jsonb_agg(
                            jsonb_build_object(
                                'rank', rsc.rank,
                                'doc_id', coalesce(c.doc_id, rsc.doc_id),
                                'chunk_id', rsc.chunk_id,
                                'raw_chunk_id', rsc.raw_chunk_id,
                                'title', coalesce(d.title, rsc.title_snapshot),
                                'source_url', coalesce(d.source_url, rsc.source_snapshot),
                                'score', rsc.score,
                                'rerank_score', rsc.rerank_score,
                                'content_preview', left(coalesce(c.content, rsc.content_snapshot), 180)
                            )
                            ORDER BY rsc.rank
                        ) AS chunks
                    FROM retrieval_selected_chunks rsc
                    LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
                    LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
                    GROUP BY retrieval_log_id
                )
                SELECT
                    q.id AS query_id,
                    q.created_at,
                    q.intent_type,
                    q.question,
                    lr.rewritten_query,
                    lr.keywords,
                    lr.category,
                    lr.retrieval_strategy,
                    lr.fallback_used,
                    lr.retrieved_doc_count,
                    lr.selected_doc_count,
                    r.success AS response_success,
                    left(r.answer_text, 360) AS answer_preview,
                    coalesce(s.chunks, '[]'::jsonb) AS selected_chunks
                FROM query_logs q
                LEFT JOIN response_logs r ON r.request_id = q.request_id
                LEFT JOIN latest_retrieval lr ON lr.request_id = q.request_id
                LEFT JOIN selected s ON s.retrieval_log_id = lr.id
                WHERE q.intent_type = 'INFO'
                  AND (
                    lr.id IS NULL
                    OR coalesce(lr.retrieved_doc_count, 0) = 0
                    OR coalesce(lr.selected_doc_count, 0) = 0
                    OR lr.fallback_used
                    OR lr.success = false
                    OR r.success = false
                    OR r.answer_text ILIKE ANY(ARRAY[
                        '%찾을 수 없%',
                        '%제공된 문서에서%',
                        '%이해하지 못%',
                        '%죄송%',
                        '%문서에 관련 정보%',
                        '%정보가 없습니다%'
                    ])
                  )
                ORDER BY q.created_at DESC
                LIMIT 25;
                """,
            )

            report["recent_success_cases"] = fetch_all(
                cur,
                """
                WITH latest_retrieval AS (
                    SELECT DISTINCT ON (request_id) *
                    FROM retrieval_logs
                    ORDER BY request_id, created_at DESC, id DESC
                )
                SELECT
                    q.id AS query_id,
                    q.created_at,
                    q.question,
                    lr.retrieval_strategy,
                    lr.retrieved_doc_count,
                    lr.selected_doc_count,
                    left(r.answer_text, 260) AS answer_preview
                FROM query_logs q
                JOIN response_logs r ON r.request_id = q.request_id
                JOIN latest_retrieval lr ON lr.request_id = q.request_id
                WHERE q.intent_type = 'INFO'
                  AND r.success
                  AND lr.success
                  AND coalesce(lr.selected_doc_count, 0) > 0
                  AND r.answer_text NOT ILIKE ALL(ARRAY[
                        '%찾을 수 없%',
                        '%제공된 문서에서%',
                        '%이해하지 못%',
                        '%죄송%',
                        '%문서에 관련 정보%',
                        '%정보가 없습니다%'
                  ])
                ORDER BY q.created_at DESC
                LIMIT 10;
                """,
            )

            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=True, indent=2))
            print(f"\nWROTE {REPORT_PATH.relative_to(ROOT)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
