from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urldefrag

from psycopg2.extras import Json, RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader


STATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawler_documents (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  final_url text,
  status text NOT NULL,
  fetch_status text,
  parse_status text,
  chunk_status text,
  vector_status text,
  seed_status text,
  discovered_from text,
  discovery_depth integer,
  promoted_at timestamptz,
  source_type text,
  page_kind text,
  checksum text,
  retry_count integer NOT NULL DEFAULT 0,
  artifact_paths jsonb NOT NULL DEFAULT '{}'::jsonb,
  extractor_name text,
  extractor_version text,
  last_error text,
  last_error_stage text,
  next_retry_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS fetch_status text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS parse_status text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS chunk_status text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS vector_status text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS seed_status text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS discovered_from text;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS discovery_depth integer;
ALTER TABLE crawler_documents ADD COLUMN IF NOT EXISTS promoted_at timestamptz;
UPDATE crawler_documents
SET fetch_status = COALESCE(fetch_status, CASE WHEN status IN ('CRAWLED', 'PARSED', 'CHUNKED', 'EMBEDDED', 'INDEXED') THEN 'FETCHED' END),
    parse_status = COALESCE(parse_status, CASE WHEN status IN ('PARSED', 'CHUNKED', 'EMBEDDED', 'INDEXED') THEN 'PARSED' END),
    chunk_status = COALESCE(chunk_status, CASE WHEN status IN ('CHUNKED', 'EMBEDDED', 'INDEXED') THEN 'CHUNKED' END),
    vector_status = COALESCE(vector_status, CASE WHEN status IN ('EMBEDDED', 'INDEXED') THEN 'INDEXED' END),
    seed_status = COALESCE(seed_status, CASE WHEN status = 'SEEDED' THEN 'seeded' END);

CREATE INDEX IF NOT EXISTS idx_crawler_documents_status
ON crawler_documents(status);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_seed_status
ON crawler_documents(seed_status);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_vector_status
ON crawler_documents(vector_status);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_updated_at
ON crawler_documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_source_type
ON crawler_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_next_retry_at
ON crawler_documents(next_retry_at);

CREATE TABLE IF NOT EXISTS crawler_dynamic_seeds (
  id bigserial PRIMARY KEY,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  confidence numeric NOT NULL,
  source_type text,
  source_group text,
  page_kind text NOT NULL,
  pattern_reason text,
  discovered_from text,
  status text NOT NULL DEFAULT 'candidate',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_status
ON crawler_dynamic_seeds(status);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_confidence
ON crawler_dynamic_seeds(confidence);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_source_type
ON crawler_dynamic_seeds(source_type);

CREATE TABLE IF NOT EXISTS crawler_retry_queue (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text,
  source_type text,
  page_kind text,
  file_path text,
  stage text NOT NULL,
  task_type text,
  reason text NOT NULL,
  retry_count integer NOT NULL DEFAULT 0,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  next_retry_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  last_attempt_at timestamptz,
  resolved_at timestamptz,
  dead_lettered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS source_type text;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS page_kind text;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS file_path text;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS context jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS task_type text;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS last_error text;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS resolved_at timestamptz;
ALTER TABLE crawler_retry_queue ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;
UPDATE crawler_retry_queue
SET task_type = COALESCE(task_type, stage),
    attempts = GREATEST(attempts, retry_count)
WHERE task_type IS NULL
   OR attempts < retry_count;

CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_status
ON crawler_retry_queue(status);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_next_retry_at
ON crawler_retry_queue(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_stage
ON crawler_retry_queue(stage);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_task_type
ON crawler_retry_queue(task_type);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_source_type
ON crawler_retry_queue(source_type);

ALTER TABLE crawler_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawler_dynamic_seeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawler_retry_queue ENABLE ROW LEVEL SECURITY;
"""


def canonicalize_url(url: str) -> str:
    canonical, _fragment = urldefrag(url.strip())
    return canonical


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def confidence_for_reason(reason: str | None) -> float:
    if reason in {"board_list", "board_detail"}:
        return 0.9
    if reason == "board_mode_hint":
        return 0.85
    if reason == "board_path_hint":
        return 0.75
    if reason == "board_query_hint":
        return 0.6
    return 0.0


def dynamic_seed_row_to_seed(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": f"dynamic_seed_{row['id']}",
        "url": row["url"],
        "source_type": row.get("source_type") or row.get("source_group") or "webpage",
        "source_group": row.get("source_group") or row.get("source_type") or "webpage",
        "page_kind": row["page_kind"],
        "priority": "P1",
        "crawl_enabled": True,
        "discover_board_candidates": False,
        "dynamic_seed_id": row["id"],
        "confidence": float(row["confidence"]),
        "pattern_reason": row.get("pattern_reason"),
    }


def crawler_document_row_to_seed(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": f"crawler_document_{row['id']}",
        "url": row["url"],
        "source_type": row.get("source_type") or "webpage",
        "source_group": row.get("source_type") or "webpage",
        "page_kind": row.get("page_kind") or "static_page",
        "priority": "P1",
        "crawl_enabled": True,
        "discover_board_candidates": True,
        "crawler_document_id": row["id"],
        "discovered_from": row.get("discovered_from"),
        "discovery_depth": row.get("discovery_depth"),
        "status": row.get("status"),
        "fetch_status": row.get("fetch_status"),
        "parse_status": row.get("parse_status"),
        "chunk_status": row.get("chunk_status"),
        "vector_status": row.get("vector_status"),
        "seed_status": row.get("seed_status"),
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


class CrawlerStateStore:
    def __init__(self, loader: PGVectorLoader | None = None):
        self._owns_loader = loader is None
        self.loader = loader or PGVectorLoader(autocommit_writes=False)
        self.conn = self.loader.conn

    def close(self) -> None:
        if self._owns_loader:
            self.loader.close()

    def commit(self) -> None:
        self.loader.commit()

    def rollback(self) -> None:
        self.loader.rollback()

    def ensure_tables(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(STATE_SCHEMA_SQL)
        self.commit()

    def upsert_dynamic_seed(self, candidate: dict[str, Any]) -> dict[str, Any]:
        confidence = candidate.get("confidence")
        if confidence is None:
            confidence = confidence_for_reason(candidate.get("reason"))
        params = {
            "url": candidate["url"],
            "canonical_url": canonicalize_url(candidate["url"]),
            "confidence": confidence,
            "source_type": candidate.get("source_type") or candidate.get("source_type_hint"),
            "source_group": candidate.get("source_group"),
            "page_kind": candidate["page_kind"],
            "pattern_reason": candidate.get("reason") or candidate.get("pattern_reason"),
            "discovered_from": candidate.get("discovered_from"),
        }
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO crawler_dynamic_seeds (
                  url,
                  canonical_url,
                  confidence,
                  source_type,
                  source_group,
                  page_kind,
                  pattern_reason,
                  discovered_from,
                  status,
                  updated_at
                )
                VALUES (
                  %(url)s,
                  %(canonical_url)s,
                  %(confidence)s,
                  %(source_type)s,
                  %(source_group)s,
                  %(page_kind)s,
                  %(pattern_reason)s,
                  %(discovered_from)s,
                  'candidate',
                  now()
                )
                ON CONFLICT (canonical_url) DO UPDATE SET
                  url = EXCLUDED.url,
                  confidence = GREATEST(crawler_dynamic_seeds.confidence, EXCLUDED.confidence),
                  source_type = COALESCE(crawler_dynamic_seeds.source_type, EXCLUDED.source_type),
                  source_group = COALESCE(crawler_dynamic_seeds.source_group, EXCLUDED.source_group),
                  page_kind = EXCLUDED.page_kind,
                  pattern_reason = EXCLUDED.pattern_reason,
                  discovered_from = COALESCE(crawler_dynamic_seeds.discovered_from, EXCLUDED.discovered_from),
                  updated_at = now()
                RETURNING *;
                """,
                params,
            )
            row = dict(cur.fetchone())
        self.commit()
        return row

    def promote_dynamic_seeds(self, min_confidence: float = 0.8) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_dynamic_seeds
                SET status = 'promoted',
                    updated_at = now()
                WHERE status = 'candidate'
                  AND confidence >= %s
                  AND page_kind = 'board_list';
                """,
                (min_confidence,),
            )
            count = cur.rowcount
        self.commit()
        return count

    def promote_static_seed_candidates(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_documents
                SET seed_status = 'promoted',
                    promoted_at = COALESCE(promoted_at, now()),
                    updated_at = now()
                WHERE page_kind = 'static_page'
                  AND COALESCE(seed_status, 'candidate') IN ('candidate', 'seeded')
                  AND status IN ('DISCOVERED', 'FETCHED', 'PARSED', 'CHUNKED', 'INDEXED');
                """
            )
            count = cur.rowcount
        self.commit()
        return count

    def preview_dynamic_seed_promotions(self, min_confidence: float = 0.8, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM crawler_dynamic_seeds
                WHERE status = 'candidate'
                  AND confidence >= %s
                  AND page_kind = 'board_list'
                ORDER BY confidence DESC, updated_at DESC
                LIMIT %s;
                """,
                (min_confidence, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_promoted_dynamic_seeds(self, min_confidence: float = 0.8) -> list[dict[str, Any]]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM crawler_dynamic_seeds
                WHERE status = 'promoted'
                  AND confidence >= %s
                  AND page_kind = 'board_list'
                ORDER BY confidence DESC, updated_at DESC;
                """,
                (min_confidence,),
            )
            return [dynamic_seed_row_to_seed(dict(row)) for row in cur.fetchall()]

    def list_promoted_static_seeds(self, include_already_parsed: bool = False) -> list[dict[str, Any]]:
        parsed_clause = "" if include_already_parsed else "AND COALESCE(parse_status, '') <> 'PARSED'"
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM crawler_documents
                WHERE page_kind = 'static_page'
                  AND seed_status = 'promoted'
                  {parsed_clause}
                ORDER BY updated_at DESC;
                """
            )
            return [crawler_document_row_to_seed(dict(row)) for row in cur.fetchall()]

    def get_document_states_by_urls(self, urls: list[str]) -> dict[str, dict[str, Any]]:
        if not urls:
            return {}
        canonical_urls = [canonicalize_url(url) for url in urls]
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                  canonical_url,
                  url,
                  doc_id,
                  status,
                  fetch_status,
                  parse_status,
                  chunk_status,
                  vector_status,
                  seed_status,
                  updated_at
                FROM crawler_documents
                WHERE canonical_url = ANY(%s);
                """,
                (canonical_urls,),
            )
            return {row["canonical_url"]: dict(row) for row in cur.fetchall()}

    def upsert_discovered_url(
        self,
        *,
        url: str,
        source_type: str | None,
        page_kind: str,
        discovered_from: str | None = None,
        discovery_depth: int | None = None,
        seed_status: str = "candidate",
    ) -> None:
        params = {
            "url": url,
            "canonical_url": canonicalize_url(url),
            "source_type": source_type,
            "page_kind": page_kind,
            "discovered_from": discovered_from,
            "discovery_depth": discovery_depth,
            "seed_status": seed_status,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawler_documents (
                  url,
                  canonical_url,
                  status,
                  source_type,
                  page_kind,
                  seed_status,
                  discovered_from,
                  discovery_depth,
                  updated_at
                )
                VALUES (
                  %(url)s,
                  %(canonical_url)s,
                  'DISCOVERED',
                  %(source_type)s,
                  %(page_kind)s,
                  %(seed_status)s,
                  %(discovered_from)s,
                  %(discovery_depth)s,
                  now()
                )
                ON CONFLICT (canonical_url) DO UPDATE SET
                  url = EXCLUDED.url,
                  source_type = COALESCE(crawler_documents.source_type, EXCLUDED.source_type),
                  page_kind = COALESCE(crawler_documents.page_kind, EXCLUDED.page_kind),
                  seed_status = COALESCE(crawler_documents.seed_status, EXCLUDED.seed_status),
                  discovered_from = COALESCE(crawler_documents.discovered_from, EXCLUDED.discovered_from),
                  discovery_depth = COALESCE(crawler_documents.discovery_depth, EXCLUDED.discovery_depth),
                  status = CASE
                    WHEN crawler_documents.status IN ('PARSED', 'CHUNKED', 'INDEXED') THEN crawler_documents.status
                    ELSE EXCLUDED.status
                  END,
                  updated_at = now();
                """,
                params,
            )
        self.commit()

    def upsert_document_state(
        self,
        *,
        url: str,
        status: str,
        doc_id: str | None = None,
        final_url: str | None = None,
        source_type: str | None = None,
        page_kind: str | None = None,
        checksum: str | None = None,
        artifact_paths: dict[str, Any] | None = None,
        extractor_name: str | None = None,
        extractor_version: str | None = None,
        error: str | None = None,
        error_stage: str | None = None,
        fetch_status: str | None = None,
        parse_status: str | None = None,
        chunk_status: str | None = None,
        vector_status: str | None = None,
        seed_status: str | None = None,
    ) -> None:
        params = {
            "doc_id": doc_id,
            "url": url,
            "canonical_url": canonicalize_url(url),
            "final_url": final_url,
            "status": status,
            "source_type": source_type,
            "page_kind": page_kind,
            "checksum": checksum,
            "artifact_paths": Json(artifact_paths or {}),
            "extractor_name": extractor_name,
            "extractor_version": extractor_version,
            "last_error": error,
            "last_error_stage": error_stage,
            "fetch_status": fetch_status,
            "parse_status": parse_status,
            "chunk_status": chunk_status,
            "vector_status": vector_status,
            "seed_status": seed_status,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawler_documents (
                  doc_id,
                  url,
                  canonical_url,
                  final_url,
                  status,
                  fetch_status,
                  parse_status,
                  chunk_status,
                  vector_status,
                  seed_status,
                  source_type,
                  page_kind,
                  checksum,
                  artifact_paths,
                  extractor_name,
                  extractor_version,
                  last_error,
                  last_error_stage,
                  updated_at
                )
                VALUES (
                  %(doc_id)s,
                  %(url)s,
                  %(canonical_url)s,
                  %(final_url)s,
                  %(status)s,
                  %(fetch_status)s,
                  %(parse_status)s,
                  %(chunk_status)s,
                  %(vector_status)s,
                  %(seed_status)s,
                  %(source_type)s,
                  %(page_kind)s,
                  %(checksum)s,
                  %(artifact_paths)s::jsonb,
                  %(extractor_name)s,
                  %(extractor_version)s,
                  %(last_error)s,
                  %(last_error_stage)s,
                  now()
                )
                ON CONFLICT (canonical_url) DO UPDATE SET
                  doc_id = COALESCE(EXCLUDED.doc_id, crawler_documents.doc_id),
                  url = EXCLUDED.url,
                  final_url = COALESCE(EXCLUDED.final_url, crawler_documents.final_url),
                  status = EXCLUDED.status,
                  fetch_status = COALESCE(EXCLUDED.fetch_status, crawler_documents.fetch_status),
                  parse_status = COALESCE(EXCLUDED.parse_status, crawler_documents.parse_status),
                  chunk_status = COALESCE(EXCLUDED.chunk_status, crawler_documents.chunk_status),
                  vector_status = COALESCE(EXCLUDED.vector_status, crawler_documents.vector_status),
                  seed_status = COALESCE(crawler_documents.seed_status, EXCLUDED.seed_status),
                  source_type = COALESCE(EXCLUDED.source_type, crawler_documents.source_type),
                  page_kind = COALESCE(EXCLUDED.page_kind, crawler_documents.page_kind),
                  checksum = COALESCE(EXCLUDED.checksum, crawler_documents.checksum),
                  artifact_paths = crawler_documents.artifact_paths || EXCLUDED.artifact_paths,
                  extractor_name = COALESCE(EXCLUDED.extractor_name, crawler_documents.extractor_name),
                  extractor_version = COALESCE(EXCLUDED.extractor_version, crawler_documents.extractor_version),
                  last_error = EXCLUDED.last_error,
                  last_error_stage = EXCLUDED.last_error_stage,
                  updated_at = now();
                """,
                params,
            )
        self.commit()

    def enqueue_retry(
        self,
        *,
        stage: str,
        reason: str,
        task_type: str | None = None,
        doc_id: str | None = None,
        url: str | None = None,
        source_type: str | None = None,
        page_kind: str | None = None,
        file_path: str | None = None,
        context: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
        next_retry_at: str | None = None,
    ) -> bool:
        effective_task_type = task_type or stage
        params = {
            "doc_id": doc_id,
            "url": url,
            "source_type": source_type,
            "page_kind": page_kind,
            "file_path": file_path,
            "stage": stage,
            "task_type": effective_task_type,
            "reason": reason,
            "next_retry_at": next_retry_at,
            "context": Json(json_safe(context or {})),
            "payload": Json(json_safe(payload or context or {})),
            "max_attempts": max(1, int(max_attempts)),
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawler_retry_queue (
                  doc_id,
                  url,
                  source_type,
                  page_kind,
                  file_path,
                  stage,
                  task_type,
                  reason,
                  next_retry_at,
                  context,
                  payload,
                  max_attempts,
                  updated_at
                )
                SELECT
                  %(doc_id)s,
                  %(url)s,
                  %(source_type)s,
                  %(page_kind)s,
                  %(file_path)s,
                  %(stage)s,
                  %(task_type)s,
                  %(reason)s,
                  NULLIF(%(next_retry_at)s, '')::timestamptz,
                  %(context)s::jsonb,
                  %(payload)s::jsonb,
                  %(max_attempts)s,
                  now()
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM crawler_retry_queue
                  WHERE status = 'pending'
                    AND stage = %(stage)s
                    AND coalesce(task_type, stage) = %(task_type)s
                    AND reason = %(reason)s
                    AND coalesce(doc_id, '') = coalesce(%(doc_id)s, '')
                    AND coalesce(url, '') = coalesce(%(url)s, '')
                );
                """,
                params,
            )
            inserted = cur.rowcount > 0
        self.commit()
        return inserted

    def list_retry_targets(
        self,
        *,
        stages: list[str],
        limit: int,
        pending_only: bool = True,
    ) -> list[dict[str, Any]]:
        status_clause = "AND status = 'pending'" if pending_only else ""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                  id,
                  stage,
                  COALESCE(task_type, stage) AS task_type,
                  reason,
                  source_type,
                  page_kind,
                  doc_id,
                  url,
                  file_path,
                  retry_count,
                  attempts,
                  max_attempts,
                  last_error,
                  context,
                  payload
                FROM crawler_retry_queue
                WHERE COALESCE(task_type, stage) = ANY(%s)
                  {status_clause}
                  AND (next_retry_at IS NULL OR next_retry_at <= now())
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (stages, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def mark_retry_done(self, retry_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_retry_queue
                SET status = 'succeeded',
                    resolved_at = now(),
                    updated_at = now()
                WHERE id = %s;
                """,
                (retry_id,),
            )
        self.commit()

    def mark_retry_failed(self, retry_id: int, error: Exception) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_retry_queue
                SET attempts = attempts + 1,
                    retry_count = retry_count + 1,
                    status = CASE
                      WHEN attempts + 1 >= max_attempts THEN 'dead_letter'
                      ELSE 'pending'
                    END,
                    last_error = %s,
                    last_attempt_at = now(),
                    dead_lettered_at = CASE
                      WHEN attempts + 1 >= max_attempts THEN now()
                      ELSE dead_lettered_at
                    END,
                    context = context || jsonb_build_object('last_error', %s),
                    updated_at = now()
                WHERE id = %s;
                """,
                (str(error), str(error), retry_id),
            )
        self.commit()

    def mark_unknown_task_type(self, retry_id: int, task_type: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_retry_queue
                SET status = 'failed_unknown_task_type',
                    last_error = %s,
                    last_attempt_at = now(),
                    updated_at = now()
                WHERE id = %s;
                """,
                (f"unknown task_type: {task_type}", retry_id),
            )
        self.commit()
