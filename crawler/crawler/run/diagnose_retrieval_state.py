from __future__ import annotations

import json
from typing import Any

from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader


QUERIES: dict[str, str] = {
    "table_columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('documents', 'chunks', 'chunk_embeddings')
        ORDER BY table_name, ordinal_position;
    """,
    "indexes": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename IN ('documents', 'chunks', 'chunk_embeddings')
        ORDER BY tablename, indexname;
    """,
    "search_functions": """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS args
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND (p.proname ILIKE '%match%' OR p.proname ILIKE '%search%')
        ORDER BY p.proname;
    """,
    "quality_summary": """
        SELECT
            (SELECT count(*) FROM chunks WHERE btrim(content) = '') AS empty_chunks,
            (SELECT count(*) FROM chunks WHERE content IS NULL) AS null_chunks,
            (
                SELECT count(*)
                FROM (
                    SELECT content_hash
                    FROM chunks
                    WHERE content_hash IS NOT NULL
                    GROUP BY content_hash
                    HAVING count(*) > 1
                ) duplicate_hashes
            ) AS duplicate_hash_groups,
            (
                SELECT count(*)
                FROM (
                    SELECT doc_id, content_hash
                    FROM chunks
                    WHERE content_hash IS NOT NULL
                    GROUP BY doc_id, content_hash
                    HAVING count(*) > 1
                ) duplicate_hashes
            ) AS duplicate_hash_groups_same_doc,
            (SELECT count(*) FROM chunks WHERE length(content) < 80) AS chunks_lt_80,
            (SELECT count(*) FROM chunks WHERE length(content) < 120) AS chunks_lt_120,
            (
                SELECT count(*)
                FROM chunks
                WHERE content ILIKE '%404 Client Error%'
                   OR content ILIKE '%500 Server Error%'
                   OR content ILIKE '%non-html static response%'
            ) AS chunks_with_error_text;
    """,
    "embedding_models": """
        SELECT model_name, count(*) AS chunks
        FROM chunk_embeddings
        GROUP BY model_name
        ORDER BY chunks DESC;
    """,
    "content_length_distribution": """
        SELECT
            min(length(content)) AS min_len,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY length(content)) AS p25,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY length(content)) AS p50,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY length(content)) AS p75,
            max(length(content)) AS max_len,
            round(avg(length(content))::numeric, 1) AS avg_len
        FROM chunks;
    """,
    "duplicate_samples": """
        SELECT
            content_hash,
            count(*) AS duplicates,
            min(doc_id) AS sample_doc_id,
            min(left(content, 160)) AS sample_content
        FROM chunks
        WHERE content_hash IS NOT NULL
        GROUP BY content_hash
        HAVING count(*) > 1
        ORDER BY duplicates DESC
        LIMIT 10;
    """,
}


def main() -> None:
    loader = PGVectorLoader()
    result: dict[str, list[dict[str, Any]]] = {}
    try:
        with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name, sql in QUERIES.items():
                cur.execute(sql)
                result[name] = [dict(row) for row in cur.fetchall()]
    finally:
        loader.close()

    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
