# crawler/ingestion/pgvector_loader.py

from __future__ import annotations

import json
import os
from typing import Any

import psycopg2
from psycopg2.extras import Json


class PGVectorLoader:
    def __init__(self):
        database_url = os.getenv("DATABASE_URL")
        
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
        
        self.conn.autocommit = False                                # 자동 커밋 해제
        self._column_cache: dict[tuple[str, str], bool] = {}

    def close(self) ->  None:                                                # DB 연결 종료
        self.conn.close()

    def ensure_tables(self) -> None:
        """
        이미 SQL로 테이블을 만들어둔 경우에도 안전하게 실행 가능.
        단, 실제 테이블 생성은 네가 작성한 전체 SQL 기준으로 하는 것을 권장.
        """
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;")
            cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_index INT;")
            cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_type TEXT;")
            cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_title TEXT;")
            cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_section_type ON chunks(section_type);")
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
                    WHERE table_name = %s
                      AND column_name = %s
                );
                """,
                (table_name, column_name),
            )
            exists = bool(cur.fetchone()[0])

        self._column_cache[key] = exists
        return exists

    def upsert_document(self, doc: dict) -> None:
        has_metadata = self.has_column("documents", "metadata")
        metadata_insert_column = "metadata," if has_metadata else ""
        metadata_insert_value = "%(metadata)s," if has_metadata else ""
        metadata_update = "metadata = EXCLUDED.metadata," if has_metadata else ""

        sql = f"""
        INSERT INTO documents (
            doc_id,
            source_type,
            page_kind,
            department,
            title,
            source_url,
            published_at,
            updated_at,
            raw_text,
            clean_text,
            table_text,
            attachment_text,
            image_text,
            version,
            content_hash,
            collected_at,
            {metadata_insert_column}
            db_updated_at
        )
        VALUES (
            %(doc_id)s,
            %(source_type)s,
            %(page_kind)s,
            %(department)s,
            %(title)s,
            %(source_url)s,
            NULLIF(%(published_at)s, '')::timestamp,
            NULLIF(%(updated_at)s, '')::timestamp,
            %(raw_text)s,
            %(clean_text)s,
            %(table_text)s,
            %(attachment_text)s,
            %(image_text)s,
            %(version)s,
            %(content_hash)s,
            NULLIF(%(collected_at)s, '')::timestamp,
            {metadata_insert_value}
            NOW()
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            source_type = EXCLUDED.source_type,
            page_kind = EXCLUDED.page_kind,
            department = EXCLUDED.department,
            title = EXCLUDED.title,
            source_url = EXCLUDED.source_url,
            published_at = EXCLUDED.published_at,
            updated_at = EXCLUDED.updated_at,
            raw_text = EXCLUDED.raw_text,
            clean_text = EXCLUDED.clean_text,
            table_text = EXCLUDED.table_text,
            attachment_text = EXCLUDED.attachment_text,
            image_text = EXCLUDED.image_text,
            version = EXCLUDED.version,
            content_hash = EXCLUDED.content_hash,
            collected_at = EXCLUDED.collected_at,
            {metadata_update}
            db_updated_at = NOW();
        """

        params = {
            "doc_id": doc.get("doc_id"),
            "source_type": doc.get("source_type"),
            "page_kind": doc.get("page_kind"),
            "department": doc.get("department"),
            "title": doc.get("title") or "",
            "source_url": doc.get("source_url"),
            "published_at": doc.get("published_at"),
            "updated_at": doc.get("updated_at"),
            "raw_text": doc.get("raw_text"),
            "clean_text": doc.get("normalize") or doc.get("clean_text"),
            "table_text": doc.get("table_text"),
            "attachment_text": doc.get("attachment_text"),
            "image_text": doc.get("image_text"),
            "version": doc.get("version", 1),
            "content_hash": doc.get("content_hash"),
            "collected_at": doc.get("collected_at"),
        }
        if has_metadata:
            params["metadata"] = Json(doc.get("metadata", {}))

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
        self.conn.commit()

    def insert_document_version(self, doc: dict, change_type: str) -> None:
        sql = """
        INSERT INTO document_versions (
            doc_id,
            version,
            content_hash,
            change_type,
            snapshot
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (doc_id, version) DO NOTHING;
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    doc["doc_id"],
                    doc.get("version", 1),
                    doc.get("content_hash"),
                    change_type,
                    Json(doc),
                ),
            )
        self.conn.commit()

    def upsert_assets(self, doc: dict) -> None:
        """
        document_assets 테이블에 이미지 / 첨부파일 메타데이터 저장.
        documents가 먼저 저장되어 있어야 FK 오류가 안 남.
        """
        rows = []

        for item in doc.get("downloaded_attachments", []) or []:
            rows.append(
                {
                    "doc_id": doc["doc_id"],
                    "asset_type": "attachment",
                    "asset_index": item.get("attachment_index"),
                    "file_name": item.get("file_name"),
                    "file_url": item.get("file_url"),
                    "file_ext": item.get("file_ext"),
                    "saved_path": item.get("saved_path"),
                    "file_size": item.get("file_size"),
                    "parser_type": item.get("parser_type"),
                    "extracted_text": item.get("attachment_text"),
                    "page_count": item.get("page_count"),
                    "metadata": {
                        "note": item.get("note"),
                        "content_type": item.get("content_type"),
                        "raw_xml_files": item.get("raw_xml_files", []),
                        "pages": item.get("pages", []),
                    },
                }
            )

        for item in doc.get("image_texts", []) or []:
            rows.append(
                {
                    "doc_id": doc["doc_id"],
                    "asset_type": "image",
                    "asset_index": item.get("image_index"),
                    "file_name": None,
                    "file_url": item.get("image_url"),
                    "file_ext": None,
                    "saved_path": None,
                    "file_size": None,
                    "parser_type": "image_ocr",
                    "extracted_text": item.get("image_text"),
                    "page_count": None,
                    "metadata": {},
                }
            )

        if not rows:
            return

        delete_sql = "DELETE FROM document_assets WHERE doc_id = %s;"

        insert_sql = """
        INSERT INTO document_assets (
            doc_id,
            asset_type,
            asset_index,
            file_name,
            file_url,
            file_ext,
            saved_path,
            file_size,
            parser_type,
            extracted_text,
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
            %(parser_type)s,
            %(extracted_text)s,
            %(page_count)s,
            %(metadata)s
        );
        """

        with self.conn.cursor() as cur:
            cur.execute(delete_sql, (doc["doc_id"],))
            for row in rows:
                row["metadata"] = Json(row["metadata"])
                cur.execute(insert_sql, row)

        self.conn.commit()

    def upsert_chunks(self, chunks: list[dict], version: int) -> None:
        if not chunks:
            return

        optional_columns = [
            ("section_index", "section_index"),
            ("section_type", "section_type"),
            ("section_title", "section_title"),
            ("metadata", "metadata"),
        ]
        available_columns = [
            (param_name, column_name)
            for param_name, column_name in optional_columns
            if self.has_column("chunks", column_name)
        ]
        insert_columns = "".join(f"            {column_name},\n" for _, column_name in available_columns)
        insert_values = "".join(f"            %({param_name})s,\n" for param_name, _ in available_columns)
        update_values = "".join(
            f"            {column_name} = EXCLUDED.{column_name},\n"
            for _, column_name in available_columns
        )

        sql = f"""
        INSERT INTO chunks (
            chunk_id,
            doc_id,
            chunk_index,
{insert_columns}\
            content,
            content_length,
            content_hash,
            version,
            updated_at
        )
        VALUES (
            %(chunk_id)s,
            %(doc_id)s,
            %(chunk_index)s,
{insert_values}\
            %(content)s,
            %(content_length)s,
            %(content_hash)s,
            %(version)s,
            NOW()
        )
        ON CONFLICT (chunk_id) DO UPDATE SET
            doc_id = EXCLUDED.doc_id,
            chunk_index = EXCLUDED.chunk_index,
{update_values}\
            content = EXCLUDED.content,
            content_length = EXCLUDED.content_length,
            content_hash = EXCLUDED.content_hash,
            version = EXCLUDED.version,
            updated_at = NOW();
        """

        rows = []
        for chunk in chunks:
            row = {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "content_length": chunk.get("content_length"),
                "content_hash": chunk.get("content_hash"),
                "version": version,
            }
            for param_name, _ in available_columns:
                if param_name == "metadata":
                    row[param_name] = Json(chunk.get("metadata", {}))
                else:
                    row[param_name] = chunk.get(param_name)
            rows.append(row)

        with self.conn.cursor() as cur:
            doc_id = chunks[0]["doc_id"]
            chunk_ids = [chunk["chunk_id"] for chunk in chunks]
            cur.execute(
                "DELETE FROM chunks WHERE doc_id = %s AND NOT (chunk_id = ANY(%s));",
                (doc_id, chunk_ids),
            )
            for row in rows:
                cur.execute(sql, row)

        self.conn.commit()

    def upsert_embeddings(self, embedded_chunks: list[dict]) -> None:
        sql = """
        INSERT INTO chunk_embeddings (
            chunk_id,
            embedding,
            updated_at
        )
        VALUES (%s, %s::vector, NOW())
        ON CONFLICT (chunk_id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            updated_at = NOW();
        """

        rows = [
            (
                item["chunk_id"],
                self._to_pg_vector(item["embedding"]),
            )
            for item in embedded_chunks
        ]

        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)

        self.conn.commit()


    def insert_crawl_job_error(
        self,
        run_type: str,
        stage: str,
        error: Exception,
        source_type: str | None = None,
        doc_id: str | None = None,
        url: str | None = None,
        file_url: str | None = None,
        file_path: str | None = None,
        context: dict | None = None,
    ) -> None:
        import traceback as tb

        sql = """
        INSERT INTO crawl_jobs (
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
        VALUES (
            %s, %s, 'failed',
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        );
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_type,
                    stage,
                    source_type,
                    doc_id,
                    url,
                    file_url,
                    file_path,
                    error.__class__.__name__,
                    str(error),
                    tb.format_exc(),
                    Json(context or {}),
                ),
            )

        self.conn.commit()