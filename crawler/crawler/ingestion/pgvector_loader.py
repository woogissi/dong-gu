from __future__ import annotations

import math
import os
import traceback as tb
from typing import Any

import psycopg2
from psycopg2.extras import Json

from crawler.utils.text_quality import strip_nul_value, text_quality_report


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
        return strip_nul_value(value)

    def _json(self, value: Any) -> Json:
        return Json(self._strip_nul(value))

    def _quality_gate_metadata(
        self,
        *,
        content: Any,
        content_type: str,
        source: str,
        file_name: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        report = text_quality_report(str(content) if content is not None else None)
        metadata = {
            "quality_status": "ok",
            "quality": report,
        }
        if not report["is_binary_like"]:
            return True, metadata

        note = (
            "content skipped before storage: binary_marker_detected; "
            f"source={source} content_type={content_type}"
        )
        if file_name:
            note += f" file_name={file_name}"
        metadata.update(
            {
                "quality_status": "binary_blocked",
                "note": note,
                "skip_reason": "binary_marker_detected",
            }
        )
        return False, metadata

    def _allow_needs_review_attachment_chunks(self) -> bool:
        return os.getenv("CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def _append_doc_quality_skip(
        self,
        doc: dict[str, Any],
        *,
        content_type: str,
        source: str,
        metadata: dict[str, Any],
        file_name: str | None = None,
        file_url: str | None = None,
    ) -> None:
        doc_metadata = doc.setdefault("metadata", {})
        doc_metadata["quality_status"] = metadata.get("quality_status", "needs_review")
        doc_metadata["note"] = metadata.get("note")
        doc_metadata.setdefault("quality_skips", []).append(
            {
                "source": source,
                "content_type": content_type,
                "file_name": file_name,
                "file_url": file_url,
                "quality_status": metadata.get("quality_status"),
                "reason": metadata.get("skip_reason"),
                "quality": metadata.get("quality"),
            }
        )

    def _insert_quality_gate_log(
        self,
        *,
        doc_id: str,
        source_type: str | None,
        url: str | None,
        file_url: str | None,
        file_path: str | None,
        content_type: str,
        metadata: dict[str, Any],
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s);
                """,
                (
                    "manual",
                    "content_quality_gate",
                    source_type,
                    doc_id,
                    url,
                    file_url,
                    file_path,
                    "binary_marker_detected",
                    metadata.get("note") or f"binary-like {content_type} content skipped",
                    self._json(
                        {
                            "content_type": content_type,
                            "quality_status": metadata.get("quality_status"),
                            "skip_reason": metadata.get("skip_reason"),
                            "quality": metadata.get("quality"),
                        }
                    ),
                ),
            )

    def _update_document_metadata(self, doc: dict[str, Any]) -> None:
        if not (doc.get("metadata") or {}).get("quality_skips"):
            return
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET metadata = %s,
                    db_updated_at = now()
                WHERE doc_id = %s;
                """,
                (self._json(doc.get("metadata", {})), doc["doc_id"]),
            )

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
        skipped: list[dict[str, Any]] = []
        for content_type, content in (
            ("raw", doc.get("raw_text")),
            ("clean", doc.get("normalize") or doc.get("clean_text")),
            ("table", doc.get("table_text")),
            ("html", doc.get("html")),
        ):
            if content and str(content).strip():
                allowed, metadata = self._quality_gate_metadata(
                    content=content,
                    content_type=content_type,
                    source="document",
                )
                if not allowed:
                    self._append_doc_quality_skip(
                        doc,
                        content_type=content_type,
                        source="document",
                        metadata=metadata,
                    )
                    skipped.append(
                        {
                            "doc_id": doc["doc_id"],
                            "source_type": doc.get("source_type"),
                            "url": doc.get("source_url"),
                            "content_type": content_type,
                            "metadata": metadata,
                        }
                    )
                    continue
                rows.append(
                    {
                        "doc_id": doc["doc_id"],
                        "document_version_id": document_version_id,
                        "content_type": content_type,
                        "content": self._strip_nul(content),
                        "metadata": self._json(metadata),
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
            for item in skipped:
                self._insert_quality_gate_log(
                    doc_id=item["doc_id"],
                    source_type=item.get("source_type"),
                    url=item.get("url"),
                    file_url=None,
                    file_path=None,
                    content_type=item["content_type"],
                    metadata=item["metadata"],
                )
        self._update_document_metadata(doc)

        self._commit_if_needed()

    def upsert_assets(self, doc: dict[str, Any], document_version_id: int | None = None) -> None:
        rows: list[dict[str, Any]] = []
        seen_attachment_keys: set[str] = set()

        for fallback_index, item in enumerate(doc.get("downloaded_attachments", []) or []):
            dedupe_key = item.get("file_hash_sha256") or item.get("file_url")
            if dedupe_key and dedupe_key in seen_attachment_keys:
                continue
            if dedupe_key:
                seen_attachment_keys.add(dedupe_key)
            item_quality = item.get("quality") or {}
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
                        "file_hash_sha256": item.get("file_hash_sha256"),
                        "note": item.get("note"),
                        "parser_name": item.get("parser_name") or item.get("parser_type"),
                        "parser_status": item.get("parser_status") or item.get("parse_status"),
                        "parse_status": item.get("parse_status"),
                        "extracted_text_length": item.get("extracted_text_length") or item_quality.get("extracted_text_length"),
                        "page_count": item.get("page_count") or item_quality.get("page_count"),
                        "text_per_page": item.get("text_per_page") or item_quality.get("text_per_page"),
                        "korean_ratio": item.get("korean_ratio") or item_quality.get("korean_ratio"),
                        "digit_ratio": item.get("digit_ratio") or item_quality.get("digit_ratio"),
                        "binary_marker_detected": item.get("binary_marker_detected") or item_quality.get("binary_marker_detected"),
                        "table_detected": item.get("table_detected") or item_quality.get("table_detected"),
                        "quality_status": item.get("quality_status"),
                        "quality_reason": item.get("quality_reason") or item_quality.get("quality_reason"),
                        "quality": item_quality,
                        "extension_source": item.get("extension_source"),
                        "download_filename_source": item.get("download_filename_source"),
                        "inferred_file_name": item.get("inferred_file_name"),
                        "needs_reprocess": bool(
                            item.get("parse_status") in {
                                "parser_empty_text",
                                "parser_unsupported",
                                "parser_failed",
                                "missing_extension",
                                "binary_marker_detected",
                            }
                            or not item.get("attachment_text")
                            or not item.get("file_ext")
                        ),
                        "raw_xml_files": item.get("raw_xml_files", []),
                        "pages": item.get("pages", []),
                        "tables": item.get("attachment_tables", []),
                        "table_count": len(item.get("attachment_tables", []) or []),
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
                extracted_text = row.get("extracted_text")
                content_allowed = False
                content_metadata: dict[str, Any] | None = None
                if row["asset_type"] == "attachment" and not (extracted_text and str(extracted_text).strip()):
                    row["metadata"]["parse_status"] = row["metadata"].get("parse_status") or "parser_empty_text"
                    row["metadata"]["quality_status"] = row["metadata"].get("quality_status") or "needs_review"
                    row["metadata"]["note"] = row["metadata"].get("note") or row["metadata"]["parse_status"]
                    row["metadata"]["needs_reprocess"] = True
                if extracted_text and str(extracted_text).strip():
                    content_allowed, content_metadata = self._quality_gate_metadata(
                        content=extracted_text,
                        content_type=row["asset_type"],
                        source="asset",
                        file_name=row.get("file_name"),
                    )
                    if row["asset_type"] == "attachment":
                        existing_quality_status = row["metadata"].get("quality_status")
                        if existing_quality_status == "parse_failed":
                            content_allowed = False
                            content_metadata = {
                                "quality_status": "parse_failed",
                                "note": row["metadata"].get("note") or "attachment text skipped before storage: parse_failed",
                                "skip_reason": row["metadata"].get("quality_reason") or row["metadata"].get("parse_status") or "parse_failed",
                                "quality": row["metadata"].get("quality") or {},
                            }
                        elif existing_quality_status == "needs_review" and not self._allow_needs_review_attachment_chunks():
                            content_allowed = False
                            content_metadata = {
                                "quality_status": "needs_review",
                                "note": row["metadata"].get("note") or "attachment text skipped before storage: needs_review",
                                "skip_reason": row["metadata"].get("quality_reason") or "needs_review",
                                "quality": row["metadata"].get("quality") or {},
                            }
                    if content_allowed and row["asset_type"] == "attachment":
                        content_metadata.update(
                            {
                                "quality_status": row["metadata"].get("quality_status") or content_metadata.get("quality_status"),
                                "quality_reason": row["metadata"].get("quality_reason"),
                                "quality": row["metadata"].get("quality") or content_metadata.get("quality"),
                            }
                        )
                    if not content_allowed:
                        row["metadata"]["quality_status"] = content_metadata["quality_status"]
                        row["metadata"]["note"] = content_metadata["note"]
                        row["metadata"]["quality"] = content_metadata["quality"]

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
                if extracted_text and str(extracted_text).strip():
                    if not content_allowed:
                        self._append_doc_quality_skip(
                            doc,
                            content_type=row["asset_type"],
                            source="asset",
                            metadata=content_metadata,
                            file_name=row.get("file_name"),
                            file_url=row.get("file_url"),
                        )
                        self._insert_quality_gate_log(
                            doc_id=row["doc_id"],
                            source_type=doc.get("source_type"),
                            url=doc.get("source_url"),
                            file_url=row.get("file_url"),
                            file_path=row.get("saved_path"),
                            content_type=row["asset_type"],
                            metadata=content_metadata,
                        )
                        continue
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
                            self._json(content_metadata),
                        ),
                    )
                elif row["asset_type"] == "attachment":
                    status = row["metadata"].get("parse_status") or "parser_empty_text"
                    row["metadata"]["parse_status"] = status
                    row["metadata"]["needs_reprocess"] = True
                    self._append_doc_quality_skip(
                        doc,
                        content_type=row["asset_type"],
                        source="asset",
                        metadata={
                            "quality_status": row["metadata"].get("quality_status") or "needs_review",
                            "note": row["metadata"].get("note") or status,
                            "skip_reason": status,
                            "quality": {},
                        },
                        file_name=row.get("file_name"),
                        file_url=row.get("file_url"),
                    )
                    self._insert_quality_gate_log(
                        doc_id=row["doc_id"],
                        source_type=doc.get("source_type"),
                        url=doc.get("source_url"),
                        file_url=row.get("file_url"),
                        file_path=row.get("saved_path"),
                        content_type=row["asset_type"],
                        metadata={
                            "quality_status": row["metadata"].get("quality_status") or "needs_review",
                            "note": row["metadata"].get("note") or status,
                            "skip_reason": status,
                            "quality": {
                                "content_type": row.get("content_type"),
                                "file_ext": row.get("file_ext"),
                                "parser_type": row.get("parser_type"),
                            },
                        },
                    )
        self._update_document_metadata(doc)

        self._commit_if_needed()

    def get_document_content_ids(self, doc_id: str, document_version_id: int | None) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dc.content_type::text,
                    dc.id,
                    da.file_name,
                    da.file_url,
                    da.metadata->>'file_hash_sha256' AS file_hash_sha256
                FROM document_contents dc
                LEFT JOIN document_assets da ON da.id = dc.asset_id
                WHERE dc.doc_id = %s
                  AND (dc.document_version_id = %s OR (%s IS NULL AND dc.document_version_id IS NULL))
                  AND dc.content_type IN ('clean', 'table', 'attachment');
                """,
                (doc_id, document_version_id, document_version_id),
            )
            rows = cur.fetchall()

        content_ids: dict[str, int] = {}
        for content_type, content_id, file_name, file_url, file_hash in rows:
            content_id = int(content_id)
            content_type = str(content_type)
            content_ids.setdefault(content_type, content_id)
            if content_type == "attachment":
                if file_name:
                    content_ids[f"attachment_name:{file_name}"] = content_id
                if file_url:
                    content_ids[f"attachment_url:{file_url}"] = content_id
                if file_hash:
                    content_ids[f"attachment_hash:{file_hash}"] = content_id
        return content_ids

    def _content_id_for_chunk(self, chunk: dict[str, Any], content_ids: dict[str, int]) -> int | None:
        section_type = self._normalize_section_type(chunk.get("section_type"))
        if section_type == "table":
            return content_ids.get("table")
        if section_type == "body":
            return content_ids.get("clean")
        if section_type == "attachment":
            metadata = chunk.get("metadata", {}) or {}
            source_metadata = metadata.get("source_section_metadata", {}) or {}
            file_hash = source_metadata.get("file_hash_sha256")
            file_url = source_metadata.get("file_url")
            file_name = chunk.get("section_title")
            if file_hash and content_ids.get(f"attachment_hash:{file_hash}"):
                return content_ids.get(f"attachment_hash:{file_hash}")
            if file_url and content_ids.get(f"attachment_url:{file_url}"):
                return content_ids.get(f"attachment_url:{file_url}")
            if file_name and content_ids.get(f"attachment_name:{file_name}"):
                return content_ids.get(f"attachment_name:{file_name}")
            return content_ids.get("attachment")
        return None

    def _filter_source_duplicate_chunks(self, rows: list[dict[str, Any]], source_type: str | None) -> list[dict[str, Any]]:
        if os.getenv("CRAWLER_BLOCK_SOURCE_DUPLICATE_CHUNKS", "").strip().lower() not in {"1", "true", "yes"}:
            return rows
        hashes = sorted({row.get("content_hash") for row in rows if row.get("content_hash")})
        if not hashes or not source_type:
            return rows

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.content_hash
                FROM chunks c
                JOIN documents d ON d.doc_id = c.doc_id
                WHERE d.source_type = %s
                  AND c.content_hash = ANY(%s)
                  AND c.doc_id <> %s;
                """,
                (source_type, hashes, rows[0]["doc_id"]),
            )
            duplicate_hashes = {row[0] for row in cur.fetchall()}

        seen_in_batch: set[str] = set()
        filtered = []
        skipped = []
        for row in rows:
            content_hash = row.get("content_hash")
            if content_hash and (content_hash in duplicate_hashes or content_hash in seen_in_batch):
                skipped.append(row)
                continue
            if content_hash:
                seen_in_batch.add(content_hash)
            filtered.append(row)

        for row in skipped:
            self._insert_quality_gate_log(
                doc_id=row["doc_id"],
                source_type=source_type,
                url=None,
                file_url=None,
                file_path=None,
                content_type=row.get("section_type") or "chunk",
                metadata={
                    "quality_status": "duplicate_blocked",
                    "note": "chunk skipped before storage: duplicate_content_hash_in_source",
                    "skip_reason": "duplicate_content_hash_in_source",
                    "quality": {
                        "content_hash": row.get("content_hash"),
                        "chunk_id": row.get("chunk_id"),
                        "dedupe_scope": "source_type",
                    },
                },
            )
        return filtered

    def upsert_chunks(self, chunks: list[dict[str, Any]], version: int) -> None:
        if not chunks:
            return

        doc_id = chunks[0]["doc_id"]
        document_version_id = self.get_document_version_id(doc_id, version)
        content_ids = self.get_document_content_ids(doc_id, document_version_id)
        rows = []

        for chunk in chunks:
            chunk_quality = text_quality_report(chunk.get("content"))
            if chunk_quality["is_binary_like"]:
                metadata = chunk.setdefault("metadata", {})
                metadata["quality_status"] = "binary_blocked"
                metadata["note"] = "chunk skipped before storage: binary_marker_detected"
                metadata["quality"] = chunk_quality
                self._insert_quality_gate_log(
                    doc_id=chunk["doc_id"],
                    source_type=chunk.get("source_type"),
                    url=chunk.get("source_url"),
                    file_url=(metadata.get("source_section_metadata") or {}).get("file_url"),
                    file_path=None,
                    content_type=self._normalize_section_type(chunk.get("section_type")),
                    metadata={
                        "quality_status": "binary_blocked",
                        "note": metadata["note"],
                        "skip_reason": "binary_marker_detected",
                        "quality": chunk_quality,
                    },
                )
                continue
            chunk_index = int(chunk["chunk_index"])
            chunk_id = self._versioned_chunk_id(chunk["doc_id"], version, chunk_index)
            chunk["chunk_id"] = chunk_id
            chunk["document_version_id"] = document_version_id
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": chunk["doc_id"],
                    "document_version_id": document_version_id,
                    "content_id": self._content_id_for_chunk(chunk, content_ids),
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

        rows = self._filter_source_duplicate_chunks(rows, chunks[0].get("source_type"))

        if not rows:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM chunks
                    WHERE doc_id = %s
                      AND (document_version_id = %s OR (%s IS NULL AND document_version_id IS NULL));
                    """,
                    (doc_id, document_version_id, document_version_id),
                )
            self._commit_if_needed()
            return

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
                    content_id,
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
                    %(content_id)s,
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
                    content_id = EXCLUDED.content_id,
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
        rows = []
        blocked_statuses = {
            "parse_failed",
            "parser_empty_text",
            "unsupported_attachment",
            "binary_blocked",
            "noise_blocked",
            "duplicate_blocked",
            "short_chunk_blocked",
        }
        for item in embedded_chunks:
            if not item.get("embedding"):
                continue
            metadata = item.get("metadata", {}) or {}
            quality_status = metadata.get("quality_status")
            content_quality = text_quality_report(item.get("content"))
            if quality_status in blocked_statuses or content_quality["is_binary_like"]:
                skip_reason = quality_status or "binary_marker_detected"
                self._insert_quality_gate_log(
                    doc_id=item.get("doc_id"),
                    source_type=item.get("source_type"),
                    url=item.get("source_url"),
                    file_url=(metadata.get("source_section_metadata") or {}).get("file_url"),
                    file_path=None,
                    content_type="embedding",
                    metadata={
                        "quality_status": quality_status or "binary_blocked",
                        "note": "embedding skipped before storage: quality_exclusion",
                        "skip_reason": skip_reason,
                        "quality": content_quality,
                    },
                )
                continue
            rows.append(
                (
                    item["chunk_id"],
                    self._to_pg_vector(item["embedding"]),
                    item.get("embedding_model") or item.get("model_name") or "unknown",
                )
            )
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

    def find_reusable_embedding_chunk_ids(
        self,
        chunks: list[dict[str, Any]],
        model_name: str,
    ) -> set[str]:
        candidates = [
            (chunk.get("chunk_id"), chunk.get("content_hash"))
            for chunk in chunks
            if chunk.get("chunk_id") and chunk.get("content_hash")
        ]
        if not candidates:
            return set()

        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH incoming(chunk_id, content_hash) AS (
                    SELECT *
                    FROM unnest(%s::text[], %s::text[])
                )
                SELECT i.chunk_id
                FROM incoming i
                JOIN chunks c
                  ON c.chunk_id = i.chunk_id
                 AND c.content_hash = i.content_hash
                JOIN chunk_embeddings e
                  ON e.chunk_id = i.chunk_id
                 AND e.model_name = %s;
                """,
                (
                    [chunk_id for chunk_id, _ in candidates],
                    [content_hash for _, content_hash in candidates],
                    model_name,
                ),
            )
            return {row[0] for row in cur.fetchall()}

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
