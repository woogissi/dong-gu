"""Suggest ground-truth chunk candidates from the current corpus.

This helper reads the configured PostgreSQL/Supabase database and prints
candidate documents/chunks for manual QA labeling. It is offline-only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor


DEFAULT_TERMS = [
    "수강신청",
    "수강정정",
    "장학금",
    "기숙사",
    "도서관",
    "통학버스",
    "졸업요건",
    "학사일정",
    "등록금",
    "휴학",
    "복학",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Suggest AutoRAG retrieval_gt candidates from corpus.")
    parser.add_argument("--terms", nargs="*", default=DEFAULT_TERMS, help="Korean search terms.")
    parser.add_argument("--limit", type=int, default=5, help="Candidates per term.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    suggestions = {term: fetch_candidates(term, args.limit) for term in args.terms}
    payload = json.dumps(suggestions, ensure_ascii=False, indent=2, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote suggestions to {output_path}")
    else:
        print(payload)


def fetch_candidates(term: str, limit: int) -> list[dict[str, Any]]:
    sql = """
    SELECT
        d.doc_id,
        c.chunk_id,
        d.title,
        d.source_type,
        d.source_url,
        d.published_at,
        c.chunk_index,
        left(c.content, 500) AS content_preview
    FROM chunks c
    JOIN documents d ON d.doc_id = c.doc_id
    WHERE d.title ILIKE %(pattern)s
       OR c.content ILIKE %(pattern)s
       OR d.source_url ILIKE %(pattern)s
       OR d.metadata::text ILIKE %(pattern)s
       OR c.metadata::text ILIKE %(pattern)s
    ORDER BY d.published_at DESC NULLS LAST, c.chunk_index ASC, c.chunk_id ASC
    LIMIT %(limit)s;
    """
    with open_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, {"pattern": f"%{term}%", "limit": limit})
            return [dict(row) for row in cur.fetchall()]


def open_db_connection():
    database_url = normalize_database_url(os.getenv("DATABASE_URL") or os.getenv("CRAWLER_DATABASE_URL") or "")
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
    )


def normalize_database_url(database_url: str) -> str:
    normalized = database_url.strip()
    if normalized.startswith("postgresql+psycopg2://"):
        return normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    return normalized


if __name__ == "__main__":
    main()
