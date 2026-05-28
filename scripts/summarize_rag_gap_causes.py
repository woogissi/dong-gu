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


QUERIES = {
    "short_chunks_by_source": """
        SELECT d.source_type,
               count(*) FILTER (WHERE length(c.content) < 120) AS lt_120,
               count(*) FILTER (WHERE length(c.content) < 250) AS lt_250,
               count(*) AS chunks
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        GROUP BY d.source_type
        HAVING count(*) FILTER (WHERE length(c.content) < 120) > 0
            OR count(*) FILTER (WHERE length(c.content) < 250) > 0
        ORDER BY lt_120 DESC, lt_250 DESC
        LIMIT 30;
    """,
    "asset_risks_by_ext": """
        SELECT coalesce(nullif(a.file_ext, ''), '(blank)') AS file_ext,
               coalesce(nullif(a.parser_type, ''), '(blank)') AS parser_type,
               count(*) AS assets_without_content
        FROM document_assets a
        WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.asset_id = a.id)
        GROUP BY 1, 2
        ORDER BY assets_without_content DESC
        LIMIT 30;
    """,
    "crawl_errors_by_stage": """
        SELECT stage, source_type, error_type, count(*) AS errors,
               max(created_at) AS last_seen
        FROM crawl_logs
        GROUP BY stage, source_type, error_type
        ORDER BY errors DESC
        LIMIT 30;
    """,
    "thin_current_notices": """
        SELECT d.source_type, d.department, d.title, d.published_at, d.source_url,
               sum(length(c.content)) AS chars, count(c.chunk_id) AS chunks
        FROM documents d
        JOIN chunks c ON c.doc_id = d.doc_id
        WHERE d.published_at >= now() - interval '120 days'
        GROUP BY d.doc_id, d.source_type, d.department, d.title, d.published_at, d.source_url
        HAVING sum(length(c.content)) < 300
        ORDER BY d.published_at DESC NULLS LAST, chars ASC
        LIMIT 50;
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
