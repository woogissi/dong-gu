from __future__ import annotations

import math
import os
import traceback as tb
from typing import Any
import traceback as tb
import psycopg2
from psycopg2.extras import Json


class PGVectorLoader:
    def __init__(self, autocommit_writes: bool = True):
        database_url = self._database_url()

        if database_url:
            self.conn = psycopg2.connect(database_url)
        else:
            self.conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                dbname=os.getenv("POSTGRES_DB", "chatbot"),
                user=os.getenv("POSTGRES_USER", "chatbot"),
                password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
            )

        self.conn.autocommit = False
        self._column_cache: dict[tuple[str, str], bool] = {}
        self.autocommit_writes = autocommit_writes

    def _database_url(self) -> str:
        database_url = (
            os.getenv("CRAWLER_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or ""
        ).strip()
        if database_url.startswith("postgresql+psycopg2://"):
            return database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return database_url

    @classmethod
    def _strip_nul(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("\x00", "")
        if isinstance(value, dict):
            return {cls._strip_nul(key): cls._strip_nul(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._strip_nul(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._strip_nul(item) for item in value)
        return value

    def _json(self, value: Any) -> Json:
        return Json(self._strip_nul(value))

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def _commit_if_needed(self) -> None:
        if self.autocommit_writes:
            self.conn.commit()

    def ensure_tables(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        self.conn.commit()
        self._column_cache.clear()

    def _to_pg_vector(self, embedding: list[float]) -> str:
        return "[" + ",".join(str(x) for x in embedding) + "]"

    def has_column(self, table_name: str, column_name: str) -> bool:
        key = (table_name, column_name)
        if key in self._column_cache:
            return self._column_cache[key]

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                      AND column_name = %s
                );
                """,
                (table_name, column_name),
            )
            exists = bool(cur.fetchone()[0])

        self._column_cache[key] = exists
        return exists

    def upsert_document(self, doc: dict[str, Any]) -> None:
        sql = """
        INSERT INTO documents (
            doc_id,
            source_type,
            page_kind,
            department,
            title,
            source_url,
            published_at,
            updated_at,
            content_hash,
            collected_at,
            metadata,
            db_updated_at
        )
        VALUES (
            %(doc_id)s,
            %(source_type)s,
            %(page_kind)s,
            %(department)s,
            %(title)s,
            %(source_url)s,
            NULLIF(%(published_at)s, '')::timestamptz,
            NULLIF(%(updated_at)s, '')::timestamptz,
            %(content_hash)s,
            NULLIF(%(collected_at)s, '')::timestamptz,
            %(metadata)s,
            now()
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            source_type = EXCLUDED.source_type,
            page_kind = EXCLUDED.page_kind,
            department = EXCLUDED.department,
            title = EXCLUDED.title,
            source_url = EXCLUDED.source_url,
            published_at = EXCLUDED.published_at,
            updated_at = EXCLUDED.updated_at,
            content_hash = EXCLUDED.content_hash,
            collected_at = EXCLUDED.collected_at,
            metadata = EXCLUDED.metadata,
            db_updated_at = now();
        """

        params = {
            "doc_id": self._strip_nul(doc.get("doc_id")),
            "source_type": self._strip_nul(doc.get("source_type")),
            "page_kind": self._strip_nul(doc.get("page_kind")),
            "department": self._strip_nul(doc.get("department")),
            "title": self._strip_nul(doc.get("title") or ""),
            "source_url": self._strip_nul(doc.get("source_url")),
            "published_at": self._strip_nul(doc.get("published_at")),
            "updated_at": self._strip_nul(doc.get("updated_at")),
            "content_hash": self._strip_nul(doc.get("content_hash")),
            "collected_at": self._strip_nul(doc.get("collected_at")),
            "metadata": self._json(doc.get("metadata", {})),
        }

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
        self._commit_if_needed()

    def insert_document_version(self, doc: dict[str, Any], change_type: str | None) -> int:
        sql = """
        INSERT INTO document_versions (
            doc_id,
            version,
            content_hash,
            change_type,
            snapshot
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (doc_id, version) DO UPDATE SET
            content_hash = EXCLUDED.content_hash,
            change_type = EXCLUDED.change_type,
            snapshot = EXCLUDED.snapshot
        RETURNING id;
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    doc["doc_id"],
                    int(doc.get("version", 1)),
                    self._strip_nul(doc.get("content_hash")),
                    self._strip_nul(self._normalize_change_type(change_type)),
                    self._json(doc),
                ),
            )
            version_id = int(cur.fetchone()[0])

        self._commit_if_needed()
        return version_id

    def get_document_version_id(self, doc_id: str, version: int) -> int | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM document_versions
                WHERE doc_id = %s AND version = %s;
                """,
                (doc_id, int(version)),
            )
            row = cur.fetchone()
        return int(row[0]) if row else None

    def upsert_document_contents(self, doc: dict[str, Any], document_version_id: int | None) -> None:
        rows = []
        for content_type, content in (
            ("raw", doc.get("raw_text")),
            ("clean", doc.get("normalize") or doc.get("clean_text")),
            ("table", doc.get("table_text")),
            ("html", doc.get("html")),
        ):
            if content and str(content).strip():
                rows.append(
                    {
                        "doc_id": doc["doc_id"],
                        "document_version_id": document_version_id,
                        "content_type": content_type,
                        "content": self._strip_nul(content),
                        "metadata": self._json({}),
                    }
                )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM document_contents
                WHERE doc_id = %s
                  AND (document_version_id = %s OR (%s IS NULL AND document_version_id IS NULL))
                  AND content_type IN ('raw', 'clean', 'table', 'html');
                """,
                (doc["doc_id"], document_version_id, document_version_id),
            )
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO document_contents (
                        doc_id,
                        document_version_id,
                        content_type,
                        content,
                        language,
                        metadata
                    )
                    VALUES (
                        %(doc_id)s,
                        %(document_version_id)s,
                        %(content_type)s,
                        %(content)s,
                        'ko',
                        %(metadata)s
                    );
                    """,
                    self._strip_nul(row),
                )

        self._commit_if_needed()

    def upsert_assets(self, doc: dict[str, Any], document_version_id: int | None = None) -> None:
        rows: list[dict[str, Any]] = []

        for fallback_index, item in enumerate(doc.get("downloaded_attachments", []) or []):
            rows.append(
                {
                    "doc_id": doc["doc_id"],
                    "asset_type": "attachment",
                    "asset_index": self._index_value(item.get("attachment_index"), fallback=fallback_index),
                    "file_name": item.get("file_name"),
                    "file_url": item.get("file_url"),
                    "file_ext": item.get("file_ext"),
                    "saved_path": item.get("saved_path"),
                    "file_size": item.get("file_size"),
                    "content_type": item.get("content_type"),
                    "parser_type": item.get("parser_type"),
                    "extracted_text": item.get("attachment_text"),
                    "page_count": item.get("page_count"),
                    "metadata": {
                        "note": item.get("note"),
                        "raw_xml_files": item.get("raw_xml_files", []),
                        "pages": item.get("pages", []),
                    },
                }
            )

        for fallback_index, item in enumerate(doc.get("image_texts", []) or []):
            rows.append(
                {
                    "doc_id": doc["doc_id"],
                    "asset_type": "image",
                    "asset_index": self._index_value(item.get("image_index"), fallback=fallback_index),
                    "file_name": None,
                    "file_url": item.get("image_url"),
                    "file_ext": None,
                    "saved_path": None,
                    "file_size": None,
                    "content_type": None,
                    "parser_type": "image_ocr",
                    "extracted_text": item.get("image_text"),
                    "page_count": None,
                    "metadata": {},
                }
            )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM document_contents
                WHERE doc_id = %s
                  AND content_type IN ('attachment', 'image')
                  AND (document_version_id = %s OR (%s IS NULL AND document_version_id IS NULL));
                """,
                (doc["doc_id"], document_version_id, document_version_id),
            )
            cur.execute("DELETE FROM document_assets WHERE doc_id = %s;", (doc["doc_id"],))

            for row in rows:
                cur.execute(
                    """
                    INSERT INTO document_assets (
                        doc_id,
                        asset_type,
                        asset_index,
                        file_name,
                        file_url,
                        file_ext,
                        saved_path,
                        file_size,
                        content_type,
                        parser_type,
                        page_count,
                        metadata
                    )
                    VALUES (
                        %(doc_id)s,
                        %(asset_type)s,
                        %(asset_index)s,
                        %(file_name)s,
                        %(file_url)s,
                        %(file_ext)s,
                        %(saved_path)s,
                        %(file_size)s,
                        %(content_type)s,
                        %(parser_type)s,
                        %(page_count)s,
                        %(metadata)s
                    )
                    RETURNING id;
                    """,
                    {**self._strip_nul(row), "metadata": self._json(row["metadata"])},
                )
                asset_id = int(cur.fetchone()[0])
                extracted_text = row.get("extracted_text")
                if extracted_text and str(extracted_text).strip():
                    cur.execute(
                        """
                        INSERT INTO document_contents (
                            doc_id,
                            asset_id,
                            document_version_id,
                            content_type,
                            content,
                            parser_type,
                            language,
                            metadata
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'ko', %s);
                        """,
                        (
                            row["doc_id"],
                            asset_id,
                            document_version_id,
                            row["asset_type"],
                            self._strip_nul(extracted_text),
                            self._strip_nul(row.get("parser_type")),
                            self._json({}),
                        ),
                    )

        self._commit_if_needed()

    def upsert_chunks(self, chunks: list[dict[str, Any]], version: int) -> None:
        if not chunks:
            return

        doc_id = chunks[0]["doc_id"]
        document_version_id = self.get_document_version_id(doc_id, version)
        rows = []

        for chunk in chunks:
            chunk_index = int(chunk["chunk_index"])
            chunk_id = self._versioned_chunk_id(chunk["doc_id"], version, chunk_index)
            chunk["chunk_id"] = chunk_id
            chunk["document_version_id"] = document_version_id
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": chunk["doc_id"],
                    "document_version_id": document_version_id,
                    "chunk_index": chunk_index,
                    "section_index": chunk.get("section_index"),
                    "section_type": self._normalize_section_type(chunk.get("section_type")),
                    "section_title": chunk.get("section_title"),
                    "content": self._strip_nul(chunk["content"]),
                    "content_length": chunk.get("content_length"),
                    "content_hash": self._strip_nul(chunk.get("content_hash")),
                    "chunking_strategy": self._strip_nul(chunk.get("chunking_strategy")),
                    "metadata": self._json(chunk.get("metadata", {})),
                }
            )

        chunk_ids = [row["chunk_id"] for row in rows]
        with self.conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM chunks
                WHERE doc_id = %s
                  AND (document_version_id = %s OR (%s IS NULL AND document_version_id IS NULL))
                  AND NOT (chunk_id = ANY(%s));
                """,
                (doc_id, document_version_id, document_version_id, chunk_ids),
            )
            cur.executemany(
                """
                INSERT INTO chunks (
                    chunk_id,
                    doc_id,
                    document_version_id,
                    chunk_index,
                    section_index,
                    section_type,
                    section_title,
                    content,
                    content_length,
                    content_hash,
                    chunking_strategy,
                    metadata,
                    updated_at
                )
                VALUES (
                    %(chunk_id)s,
                    %(doc_id)s,
                    %(document_version_id)s,
                    %(chunk_index)s,
                    %(section_index)s,
                    %(section_type)s,
                    %(section_title)s,
                    %(content)s,
                    %(content_length)s,
                    %(content_hash)s,
                    %(chunking_strategy)s,
                    %(metadata)s,
                    now()
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    document_version_id = EXCLUDED.document_version_id,
                    chunk_index = EXCLUDED.chunk_index,
                    section_index = EXCLUDED.section_index,
                    section_type = EXCLUDED.section_type,
                    section_title = EXCLUDED.section_title,
                    content = EXCLUDED.content,
                    content_length = EXCLUDED.content_length,
                    content_hash = EXCLUDED.content_hash,
                    chunking_strategy = EXCLUDED.chunking_strategy,
                    metadata = EXCLUDED.metadata,
                    updated_at = now();
                """,
                rows,
            )

        self._commit_if_needed()

    def upsert_embeddings(self, embedded_chunks: list[dict[str, Any]]) -> None:
        rows = [
            (
                item["chunk_id"],
                self._to_pg_vector(item["embedding"]),
                item.get("embedding_model") or item.get("model_name") or "unknown",
            )
            for item in embedded_chunks
            if item.get("embedding")
        ]
        if not rows:
            return

        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunk_embeddings (
                    chunk_id,
                    embedding,
                    model_name,
                    updated_at
                )
                VALUES (%s, %s::vector, %s, now())
                ON CONFLICT (chunk_id, model_name) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    updated_at = now();
                """,
                rows,
            )

        self._commit_if_needed()

    def insert_crawl_job_error(
        self,
        run_type: str = "manual",
        stage: str | None = None,
        error: Exception | None = None,
        source_type: str | None = None,
        doc_id: str | None = None,
        url: str | None = None,
        file_url: str | None = None,
        file_path: str | None = None,
        context: dict | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawl_logs (
                    run_type,
                    stage,
                    source_type,
                    doc_id,
                    url,
                    file_url,
                    file_path,
                    error_type,
                    error_message,
                    traceback,
                    context
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    self._normalize_run_type(run_type),
                    stage,
                    source_type,
                    doc_id,
                    url,
                    file_url,
                    file_path,
                    error.__class__.__name__,
                    self._strip_nul(str(error)),
                    self._strip_nul(tb.format_exc()),
                    self._json(context or {}),
                ),
            )

        self._commit_if_needed()

    def _normalize_change_type(self, change_type: str | None) -> str:
        if change_type in ("created", "new"):
            return "created"
        if change_type in ("updated", "update"):
            return "updated"
        if change_type == "deleted":
            return "deleted"
        return "updated"

    def _normalize_run_type(self, run_type: str | None) -> str:
        return run_type if run_type in {"scheduled", "manual", "retry", "backfill"} else "manual"

    def _normalize_section_type(self, section_type: Any) -> str:
        return section_type if section_type in {"title", "body", "table", "attachment", "image", "html"} else "other"

    def _versioned_chunk_id(self, doc_id: str, version: int, chunk_index: int) -> str:
        return f"{doc_id}_v{int(version):03d}_chunk_{int(chunk_index):03d}"

    def _index_value(self, value: Any, fallback: int = 0) -> int:
        try:
            parsed = int(value)
            return parsed if math.isfinite(parsed) else fallback
        except (TypeError, ValueError):
            return fallback
