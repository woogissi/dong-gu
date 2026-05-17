from __future__ import annotations

import json
import os
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


def open_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
    )


QUERIES: dict[str, str] = {
    "overview": """
        SELECT
          (SELECT count(*) FROM documents) AS documents,
          (SELECT count(*) FROM document_versions) AS versions,
          (SELECT count(*) FROM document_contents) AS contents,
          (SELECT count(*) FROM document_assets) AS assets,
          (SELECT count(*) FROM chunks) AS chunks,
          (SELECT count(*) FROM chunk_embeddings) AS embeddings,
          (SELECT count(*) FROM query_logs) AS query_logs,
          (SELECT count(*) FROM retrieval_logs) AS retrieval_logs;
    """,
    "by_source_type": """
        SELECT d.source_type,
               count(DISTINCT d.doc_id) AS docs,
               count(c.chunk_id) AS chunks,
               round(avg(length(c.content))::numeric, 1) AS avg_chunk_len,
               min(d.published_at) AS min_published_at,
               max(d.published_at) AS max_published_at
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        GROUP BY d.source_type
        ORDER BY docs DESC;
    """,
    "by_department": """
        SELECT coalesce(nullif(d.department, ''), '(blank)') AS department,
               count(DISTINCT d.doc_id) AS docs,
               count(c.chunk_id) AS chunks,
               round(avg(length(c.content))::numeric, 1) AS avg_chunk_len
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        GROUP BY 1
        ORDER BY docs DESC
        LIMIT 30;
    """,
    "coverage_gaps": """
        SELECT 'docs_without_chunks' AS gap, count(*) AS count
        FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.doc_id = d.doc_id)
        UNION ALL
        SELECT 'chunks_without_embeddings', count(*)
        FROM chunks c
        WHERE NOT EXISTS (SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.chunk_id)
        UNION ALL
        SELECT 'docs_without_contents', count(*)
        FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.doc_id = d.doc_id)
        UNION ALL
        SELECT 'assets_without_extracted_content', count(*)
        FROM document_assets a
        WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.asset_id = a.id)
        UNION ALL
        SELECT 'very_short_chunks_lt_120', count(*)
        FROM chunks
        WHERE length(content) < 120
        UNION ALL
        SELECT 'blank_departments', count(*)
        FROM documents
        WHERE department IS NULL OR btrim(department) = '';
    """,
    "short_or_missing_samples": """
        SELECT d.doc_id, d.source_type, d.department, d.title, d.source_url,
               count(c.chunk_id) AS chunks,
               coalesce(min(length(c.content)), 0) AS min_len,
               coalesce(max(length(c.content)), 0) AS max_len
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        GROUP BY d.doc_id, d.source_type, d.department, d.title, d.source_url
        HAVING count(c.chunk_id) = 0 OR coalesce(max(length(c.content)), 0) < 200
        ORDER BY chunks ASC, max_len ASC, d.doc_id ASC
        LIMIT 40;
    """,
    "attachment_risks": """
        SELECT d.doc_id, d.title, d.source_type, d.department,
               a.file_name, a.file_ext, a.parser_type, a.page_count, a.file_url
        FROM document_assets a
        JOIN documents d ON d.doc_id = a.doc_id
        WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.asset_id = a.id)
        ORDER BY d.db_updated_at DESC
        LIMIT 40;
    """,
    "recent_crawl_errors": """
        SELECT created_at, stage, source_type, doc_id,
               left(coalesce(url, file_url, file_path, ''), 160) AS target,
               error_type, left(error_message, 220) AS error_message
        FROM crawl_logs
        ORDER BY created_at DESC
        LIMIT 30;
    """,
    "retrieval_zero_or_fail": """
        SELECT rl.created_at, q.question, rl.category, rl.keywords, rl.filters,
               rl.retrieved_doc_count, rl.selected_doc_count,
               rl.fallback_used, rl.success,
               left(coalesce(rl.error_message, ''), 180) AS error_message
        FROM retrieval_logs rl
        LEFT JOIN query_logs q ON q.request_id = rl.request_id
        WHERE coalesce(rl.retrieved_doc_count, 0) = 0
           OR coalesce(rl.selected_doc_count, 0) = 0
           OR rl.success = false
        ORDER BY rl.created_at DESC
        LIMIT 50;
    """,
    "top_titles": """
        SELECT d.source_type, d.department, d.title, d.published_at, d.source_url,
               count(c.chunk_id) AS chunks,
               sum(length(c.content)) AS chars,
               max(d.db_updated_at) AS db_updated_at
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        GROUP BY d.doc_id, d.source_type, d.department, d.title, d.published_at, d.source_url
        ORDER BY d.published_at DESC NULLS LAST, db_updated_at DESC
        LIMIT 30;
    """,
}


def main() -> None:
    result: dict[str, list[dict[str, Any]]] = {}
    with open_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name, sql in QUERIES.items():
                cur.execute(sql)
                result[name] = [dict(row) for row in cur.fetchall()]

    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
