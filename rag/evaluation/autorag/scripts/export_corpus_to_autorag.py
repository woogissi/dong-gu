"""Export Donggu RAG chunks to an AutoRAG corpus parquet file.

This is an offline evaluation utility. It does not modify production data.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import DictCursor


DEFAULT_OUTPUT_PATH = Path("rag/evaluation/autorag/data/corpus.parquet")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export latest RAG chunks to AutoRAG corpus.parquet.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output parquet path.")
    parser.add_argument(
        "--min-content-length",
        type=int,
        default=1,
        help="Skip chunks shorter than this many characters.",
    )
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="Print selected database source and corpus counts without writing parquet.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.check_connection:
        print_connection_check()
        return

    output_path = Path(args.output)
    rows = fetch_corpus_rows(min_content_length=args.min_content_length)
    write_parquet(rows, output_path)
    print(f"Exported {len(rows)} corpus rows to {output_path}")


def print_connection_check() -> None:
    source = selected_database_source()
    with open_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents;")
            document_count = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM chunks;")
            chunk_count = int(cur.fetchone()[0])

    print(f"database_source={source['source']}")
    print(f"database_host={source['host']}")
    print(f"database_name={source['database']}")
    print(f"documents={document_count}")
    print(f"chunks={chunk_count}")


def fetch_corpus_rows(*, min_content_length: int) -> list[dict[str, Any]]:
    sql = """
    WITH latest_document_versions AS (
        SELECT doc_id, max(version) AS latest_version
        FROM document_versions
        GROUP BY doc_id
    )
    SELECT
        documents.doc_id,
        chunks.chunk_id,
        chunks.content,
        chunks.chunk_index,
        chunks.section_index,
        chunks.section_type,
        chunks.section_title,
        chunks.content_length,
        chunks.content_hash,
        chunks.chunking_strategy,
        chunks.metadata AS chunk_metadata,
        documents.source_type,
        documents.page_kind,
        documents.department,
        documents.title,
        documents.source_url,
        documents.published_at,
        documents.updated_at,
        documents.collected_at,
        documents.metadata AS document_metadata,
        document_versions.version
    FROM chunks
    JOIN documents ON documents.doc_id = chunks.doc_id
    LEFT JOIN document_versions ON document_versions.id = chunks.document_version_id
    LEFT JOIN latest_document_versions
      ON latest_document_versions.doc_id = chunks.doc_id
    WHERE (
        chunks.document_version_id IS NULL
        OR document_versions.version = latest_document_versions.latest_version
    )
      AND char_length(chunks.content) >= %s
    ORDER BY documents.doc_id, chunks.chunk_index, chunks.chunk_id;
    """

    with open_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (min_content_length,))
            db_rows = cur.fetchall()

    return [to_autorag_row(dict(row)) for row in db_rows]


def open_db_connection():
    database_url = normalize_database_url(
        os.getenv("DATABASE_URL")
        or os.getenv("CRAWLER_DATABASE_URL")
        or ""
    )
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
    )


def selected_database_source() -> dict[str, str]:
    for env_name in ("DATABASE_URL", "CRAWLER_DATABASE_URL"):
        database_url = normalize_database_url(os.getenv(env_name) or "")
        if database_url:
            parsed = urlparse(database_url)
            return {
                "source": env_name,
                "host": parsed.hostname or "",
                "database": parsed.path.lstrip("/") or "",
            }

    return {
        "source": "POSTGRES_*",
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "database": os.getenv("POSTGRES_DB", "chatbot"),
    }


def normalize_database_url(database_url: str) -> str:
    normalized = database_url.strip()
    if normalized.startswith("postgresql+psycopg2://"):
        return normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    return normalized


def to_autorag_row(row: dict[str, Any]) -> dict[str, Any]:
    document_metadata = coerce_dict(row.get("document_metadata"))
    chunk_metadata = coerce_dict(row.get("chunk_metadata"))
    published_at = row.get("published_at")
    updated_at = row.get("updated_at")
    collected_at = row.get("collected_at")
    last_modified = updated_at or published_at or collected_at

    metadata = {
        **document_metadata,
        "doc_id": row.get("chunk_id"),
        "original_doc_id": row.get("doc_id"),
        "chunk_id": row.get("chunk_id"),
        "chunk_index": row.get("chunk_index"),
        "section_index": row.get("section_index"),
        "section_type": row.get("section_type"),
        "section_title": row.get("section_title"),
        "content_length": row.get("content_length"),
        "content_hash": row.get("content_hash"),
        "chunking_strategy": row.get("chunking_strategy"),
        "page_kind": row.get("page_kind"),
        "department": row.get("department"),
        "version": row.get("version"),
        "published_at": isoformat_or_none(published_at),
        "updated_at": isoformat_or_none(updated_at),
        "collected_at": isoformat_or_none(collected_at),
        "last_modified_datetime": isoformat_or_none(last_modified),
        "chunk_metadata": chunk_metadata,
    }

    return {
        "doc_id": row.get("chunk_id"),
        "original_doc_id": row.get("doc_id"),
        "chunk_id": row.get("chunk_id"),
        "contents": row.get("content") or "",
        "metadata": metadata,
        "source_type": row.get("source_type"),
        "category": row.get("source_type"),
        "title": row.get("title"),
        "source_url": row.get("source_url"),
        "published_at": published_at,
        "updated_at": updated_at,
        "last_modified_datetime": last_modified,
    }


def coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def write_parquet(rows: list[dict[str, Any]], output_path: Path) -> None:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas and pyarrow are required. Install them in the rag service.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(output_path, index=False)


if __name__ == "__main__":
    main()
