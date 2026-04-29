# crawler/ingestion/pgvector_loader.py

from __future__ import annotations

import json
import os
from typing import Any

import psycopg2
from psycopg2.extras import Json


class PGVectorLoader:
    def __init__(self):
        self.conn = psycopg2.connect(                               # DB 연결 초기화
            host=os.getenv("POSTGRES_HOST", "postgres"),           # DB 호스트
            port=os.getenv("POSTGRES_PORT", "5432"),                # 포트 번호
            dbname=os.getenv("POSTGRES_DB", "chatbot"),             # DB 이름
            user=os.getenv("POSTGRES_USER", "chatbot"),             # DB 사용자명
            password=os.getenv("POSTGRES_PASSWORD", "chatbot"),     # DB 비밀번호
        )
        self.conn.autocommit = False                                # 자동 커밋 해제

    def close(self) ->  None:                                                # DB 연결 종료
        self.conn.close()

    def ensure_tables(self) -> None:
        """
        이미 SQL로 테이블을 만들어둔 경우에도 안전하게 실행 가능.
        단, 실제 테이블 생성은 네가 작성한 전체 SQL 기준으로 하는 것을 권장.
        """
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        self.conn.commit()

    def _to_pg_vector(self, embedding: list[float]) -> str:
        return "[" + ",".join(str(x) for x in embedding) + "]"

    def upsert_document(self, doc: dict) -> None:
        sql = """
        INSERT INTO documents (
            doc_id,
            parent_doc_id,
            source_type,
            page_kind,
            category_lv1,
            category_lv2,
            department,
            title,
            summary,
            source_url,
            published_at,
            updated_at,
            valid_from,
            valid_to,
            target_audience,
            keywords,
            raw_text,
            clean_text,
            table_text,
            attachment_text,
            image_text,
            language,
            status,
            version,
            content_hash,
            collected_at,
            db_updated_at
        )
        VALUES (
            %(doc_id)s,
            %(parent_doc_id)s,
            %(source_type)s,
            %(page_kind)s,
            %(category_lv1)s,
            %(category_lv2)s,
            %(department)s,
            %(title)s,
            %(summary)s,
            %(source_url)s,
            NULLIF(%(published_at)s, '')::timestamp,
            NULLIF(%(updated_at)s, '')::timestamp,
            NULLIF(%(valid_from)s, '')::timestamp,
            NULLIF(%(valid_to)s, '')::timestamp,
            %(target_audience)s,
            %(keywords)s,
            %(raw_text)s,
            %(clean_text)s,
            %(table_text)s,
            %(attachment_text)s,
            %(image_text)s,
            %(language)s,
            %(status)s,
            %(version)s,
            %(content_hash)s,
            NULLIF(%(collected_at)s, '')::timestamp,
            NOW()
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            parent_doc_id = EXCLUDED.parent_doc_id,
            source_type = EXCLUDED.source_type,
            page_kind = EXCLUDED.page_kind,
            category_lv1 = EXCLUDED.category_lv1,
            category_lv2 = EXCLUDED.category_lv2,
            department = EXCLUDED.department,
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            source_url = EXCLUDED.source_url,
            published_at = EXCLUDED.published_at,
            updated_at = EXCLUDED.updated_at,
            valid_from = EXCLUDED.valid_from,
            valid_to = EXCLUDED.valid_to,
            target_audience = EXCLUDED.target_audience,
            keywords = EXCLUDED.keywords,
            raw_text = EXCLUDED.raw_text,
            clean_text = EXCLUDED.clean_text,
            table_text = EXCLUDED.table_text,
            attachment_text = EXCLUDED.attachment_text,
            image_text = EXCLUDED.image_text,
            language = EXCLUDED.language,
            status = EXCLUDED.status,
            version = EXCLUDED.version,
            content_hash = EXCLUDED.content_hash,
            collected_at = EXCLUDED.collected_at,
            db_updated_at = NOW();
        """

        params = {
            "doc_id": doc.get("doc_id"),
            "parent_doc_id": doc.get("parent_doc_id"),
            "source_type": doc.get("source_type"),
            "page_kind": doc.get("page_kind"),
            "category_lv1": doc.get("category_lv1"),
            "category_lv2": doc.get("category_lv2"),
            "department": doc.get("department"),
            "title": doc.get("title") or "",
            "summary": doc.get("summary"),
            "source_url": doc.get("source_url"),
            "published_at": doc.get("published_at"),
            "updated_at": doc.get("updated_at"),
            "valid_from": doc.get("valid_from"),
            "valid_to": doc.get("valid_to"),
            "target_audience": doc.get("target_audience") or [],
            "keywords": doc.get("keywords") or [],
            "raw_text": doc.get("raw_text"),
            "clean_text": doc.get("normalize") or doc.get("clean_text"),
            "table_text": doc.get("table_text"),
            "attachment_text": doc.get("attachment_text"),
            "image_text": doc.get("image_text"),
            "language": doc.get("language", "ko"),
            "status": doc.get("status", "active"),
            "version": doc.get("version", 1),
            "content_hash": doc.get("content_hash"),
            "collected_at": doc.get("collected_at"),
        }

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
                    "content_type": item.get("content_type"),
                    "file_size": item.get("file_size"),
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
                    "content_type": None,
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
            content_type,
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
            %(content_type)s,
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
        sql = """
        INSERT INTO chunks (
            chunk_id,
            doc_id,
            chunk_index,
            content,
            content_length,
            content_hash,
            version,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (chunk_id) DO UPDATE SET
            doc_id = EXCLUDED.doc_id,
            chunk_index = EXCLUDED.chunk_index,
            content = EXCLUDED.content,
            content_length = EXCLUDED.content_length,
            content_hash = EXCLUDED.content_hash,
            version = EXCLUDED.version,
            updated_at = NOW();
        """

        rows = [
            (
                chunk["chunk_id"],
                chunk["doc_id"],
                chunk["chunk_index"],
                chunk["content"],
                chunk.get("content_length"),
                chunk.get("content_hash"),
                version,
            )
            for chunk in chunks
        ]

        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)

        self.conn.commit()

    def upsert_embeddings(self, embedded_chunks: list[dict]) -> None:
        sql = """
        INSERT INTO chunk_embeddings (
            chunk_id,
            embedding,
            model_name,
            updated_at
        )
        VALUES (%s, %s::vector, %s, NOW())
        ON CONFLICT (chunk_id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            model_name = EXCLUDED.model_name,
            updated_at = NOW();
        """

        rows = [
            (
                item["chunk_id"],
                self._to_pg_vector(item["embedding"]),
                item["embedding_model"],
            )
            for item in embedded_chunks
        ]

        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)

        self.conn.commit()
